#include "AgentsMode.h"
#if WITH_AGENTS
#include "Platform.h"
#include "Gfx.h"
#include <Arduino_GFX_Library.h>
#include <new>
#include <algorithm>
#include <time.h>
#if !defined(SMALLTV_ESP8266)
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#endif

AgentsMode g_agentsMode;
namespace {
constexpr uint32_t TimeoutMs = 3000;
class AgentsTransport : public WiFiClient {
 public:
  explicit AgentsTransport(AgentsFetch& request) : request_(request), started_(millis()) {}
  using WiFiClient::connect;
#if defined(SMALLTV_ESP8266)
  int connect(const char* host, uint16_t port) override {
    if (!allowed()) return 0;
    int result = WiFiClient::connect(host, port);
    return allowed() ? result : 0;
  }
#else
  int connect(const char* host, uint16_t port, int32_t timeout) override {
    if (!allowed()) return 0;
    int result = WiFiClient::connect(host, port, timeout);
    return allowed() ? result : 0;
  }
#endif
  int available() override { return allowed() ? WiFiClient::available() : 0; }
  uint8_t connected() override { return allowed() ? WiFiClient::connected() : 0; }
  int read() override { return allowed() ? WiFiClient::read() : -1; }
  int read(uint8_t* buffer, size_t n) override { return allowed() ? WiFiClient::read(buffer, n) : -1; }
  size_t write(uint8_t byte) override { return write(&byte, 1); }
  size_t write(const uint8_t* buffer, size_t n) override { return allowed() ? WiFiClient::write(buffer, n) : 0; }
  bool allowed() {
    if (!request_.cancelled.load() && uint32_t(millis() - started_) < TimeoutMs) return true;
    WiFiClient::stop(); setTimeout(1); return false;
  }
 private:
  AgentsFetch& request_;
  uint32_t started_;
};
bool fetchAgents(AgentsFetch& request) {
  if (!smalltv::validAgentsUrl(request.url.c_str()) || !request.url.length()) return false;
  AgentsTransport client(request);
  HTTPClient http;
#if !defined(SMALLTV_ESP8266)
  client.setConnectionTimeout(TimeoutMs);
  http.setConnectTimeout(TimeoutMs);
#endif
  http.setTimeout(TimeoutMs); http.setReuse(false); http.useHTTP10(true);
  if (!http.begin(client, request.url)) return false;
  http.addHeader("Accept", "application/json");
  if (http.GET() != HTTP_CODE_OK || !client.allowed()) { http.end(); return false; }
  int length = http.getSize();
  if (length <= 0 || length > static_cast<int>(smalltv::AgentsMaxBody)) { http.end(); return false; }
  std::unique_ptr<char[]> body(new(std::nothrow) char[length + 1]);
  if (!body) { http.end(); return false; }
  Stream& stream = http.getStream();
  size_t got = 0;
  while (got < static_cast<size_t>(length) && client.allowed()) {
    int available = stream.available();
    if (available > 0) {
      size_t count = std::min(static_cast<size_t>(available), static_cast<size_t>(length) - got);
      int read = stream.readBytes(body.get() + got, count);
      if (read > 0) got += read;
    } else if (!client.connected()) break;
    else delay(1);
  }
  http.end();
  if (got != static_cast<size_t>(length) || request.cancelled.load()) return false;
  body[got] = 0;
  return smalltv::parseAgents(body.get(), got, request.data);
}
#if !defined(SMALLTV_ESP8266)
void runAgentsFetch(void* context) {
  {
    std::unique_ptr<std::shared_ptr<AgentsFetch>> owner(static_cast<std::shared_ptr<AgentsFetch>*>(context));
    auto request = *owner; owner.reset();
    request->ok = fetchAgents(*request);
    request->done.store(true, std::memory_order_release);
  }
  vTaskDelete(nullptr);
}
#endif
bool startFetch(const std::shared_ptr<AgentsFetch>& request) {
#if defined(SMALLTV_ESP8266)
  request->ok = fetchAgents(*request);
  request->done.store(true, std::memory_order_release);
  return true;
#else
  constexpr size_t StackBytes = 8192;
  if (ESP.getFreeHeap() < StackBytes + 16000) return false;
  auto context = new(std::nothrow) std::shared_ptr<AgentsFetch>(request);
  if (!context) return false;
  if (xTaskCreate(runAgentsFetch, "agents-json", StackBytes, context, 1, nullptr) != pdPASS) {
    delete context; return false;
  }
  return true;
#endif
}
void text(Arduino_GFX* gfx, const char* value, int x, int y, int width, uint8_t size, uint16_t color) {
  uint8_t fit = std::max<uint8_t>(2, gfxFitSize(value, width, size));
  char clipped[49];
  size_t count = std::min(strlen(value), std::min(sizeof(clipped) - 1, static_cast<size_t>(width / (6 * fit))));
  memcpy(clipped, value, count); clipped[count] = 0;
  if (strlen(value) > count && count >= 3) memcpy(clipped + count - 3, "...", 3);
  gfx->setTextSize(fit);
  gfx->setTextColor(color); gfx->setCursor(x, y); gfx->print(clipped);
}
}
void AgentsMode::begin(const Settings& s) { invalidate(s); }
void AgentsMode::invalidate(const Settings& s) {
  if (fetch_) fetch_->cancelled.store(true);
  data_.reset(); page_ = 0; lastOk_ = 0;
  rotate_ = s.agents.autoRotate; dirty_ = true; error_ = false; wasFresh_ = false;
  forceFull_ = true; paintedValid_ = false;
  nextPoll_ = millis(); lastPage_ = millis();
}
bool AgentsMode::fresh() const {
  if (!data_ || uint32_t(millis() - lastOk_) > smalltv::AgentsStaleMs) return false;
  time_t now = time(nullptr);
  // An unsynced clock still expires cached data by monotonic receive time.
  if (now > 1700000000) {
    if (now < data_->sampled) return uint64_t(data_->sampled - now) <= 5;
    return uint64_t(now - data_->sampled) <= 45;
  }
  return true;
}
void AgentsMode::next() {
  if (data_ && data_->pageCount) {
    uint8_t nextPage = (page_ + 1) % data_->pageCount;
    if (nextPage != page_) forceFull_ = true;
    page_ = nextPage;
  }
  lastPage_ = millis(); dirty_ = true;
}
void AgentsMode::toggleRotation() { rotate_ = !rotate_; lastPage_ = millis(); dirty_ = true; }
void AgentsMode::status(JsonObject o) const {
  o["valid"] = bool(data_); o["fresh"] = fresh(); o["error"] = error_;
  o["ageSec"] = data_ ? uint32_t(millis() - lastOk_) / 1000 : 0;
  o["pages"] = data_ ? data_->pageCount : 0; o["page"] = page_;
  o["title"] = data_ ? data_->pages[page_].title : "";
  o["autoRotate"] = rotate_; o["fetching"] = bool(fetch_);
  o["fullPaints"] = fullPaints_; o["cardPaints"] = cardPaints_;
}
void AgentsMode::service(const Settings& s) {
  if (fetch_ && fetch_->done.load(std::memory_order_acquire)) {
    if (!fetch_->cancelled.load()) {
      error_ = !fetch_->ok;
      if (fetch_->ok) {
        if (!data_) data_.reset(new(std::nothrow) smalltv::AgentsData);
        if (data_) {
          bool changed = data_->pageCount != fetch_->data.pageCount;
          if (data_->pageCount) {
            auto before = smalltv::agentVisiblePage(data_->pages[page_]);
            auto after = smalltv::agentVisiblePage(fetch_->data.pages[page_ % fetch_->data.pageCount]);
            changed = changed || smalltv::agentVisibleChanges(before, after).any();
          }
          if (!data_->sampled || fetch_->data.sampled > data_->sampled) lastOk_ = millis();
          *data_ = fetch_->data; page_ %= data_->pageCount;
          dirty_ = dirty_ || changed;
        }
        else error_ = true;
      }
      if (error_) dirty_ = true;
    }
    fetch_.reset();
  }
  if (!fetch_ && s.agents.url.length() && int32_t(millis() - nextPoll_) >= 0) {
    nextPoll_ = millis() + uint32_t(s.agents.refreshSec) * 1000;
    if (ESP.getFreeHeap() > 16000) {
      fetch_ = std::make_shared<AgentsFetch>(); fetch_->url = s.agents.url;
      if (!startFetch(fetch_)) { fetch_.reset(); error_ = true; dirty_ = true; }
    }
  }
  bool currentFresh = fresh();
  if (currentFresh != wasFresh_) { dirty_ = true; wasFresh_ = currentFresh; }
  if (rotate_ && uint32_t(millis() - lastPage_) >= uint32_t(s.agents.pageSec) * 1000) next();
  if (dirty_) { draw(); dirty_ = false; }
}
void AgentsMode::draw() {
  Arduino_GFX* gfx = gfxDev(); if (!gfx) return;
  const uint16_t ink = gfxTint(0x0862), panel = gfxTint(0x18C4), edge = gfxTint(0x2946);
  const uint16_t paper = gfxTint(0xFF9B), muted = gfxTint(0x9492);
  const uint16_t mint = gfxTint(0x8F56), amber = gfxTint(0xFE09);
  if (!data_) {
    if (forceFull_ || paintedValid_) { gfx->fillScreen(ink); ++fullPaints_; }
    forceFull_ = false; paintedValid_ = false;
    gfx->fillRoundRect(8, 62, 224, 114, 12, panel);
    gfxDrawCentered("AGENTS", 79, 4, paper);
    gfxDrawCentered(error_ ? "FEED OFFLINE" : "CONNECTING", 137, 2, amber);
    return;
  }
  auto page = smalltv::agentVisiblePage(data_->pages[page_], !fresh());
  auto changes = smalltv::agentVisibleChanges(painted_, page);
  const bool full = forceFull_ || !paintedValid_ || changes.layout;
  if (full) { gfx->fillScreen(ink); ++fullPaints_; }
  if (full || changes.header) {
    if (!full) gfx->fillRect(0, 0, 198, 35, ink);
    text(gfx, page.title, 12, 7, 174, 3, paper);
  }
  // Rotation is an icon, so every word on the physical display stays readable.
  if (full || rotate_ != paintedRotate_) {
    gfx->fillRect(203, 3, 33, 33, ink);
    gfx->fillCircle(218, 19, 13, edge);
    if (rotate_) gfx->fillTriangle(215, 12, 215, 26, 224, 19, mint);
    else { gfx->fillRect(213, 12, 4, 14, amber); gfx->fillRect(220, 12, 4, 14, amber); }
  }
  for (uint8_t i = 0; i < page.rowCount; ++i) {
    if (!full && !(changes.rows & (1 << i))) continue;
    ++cardPaints_;
    const auto& row = page.rows[i];
    const uint16_t provider = gfxTint(!strcmp(row.title, "CLAUDE") ? 0xF4AE
        : !strcmp(row.title, "CODEX") ? 0x4E9E : 0xB4BF);
    const int top = 39 + i * (page.usage ? 61 : 94);
    const int height = page.usage ? 56 : 88;
    gfx->fillRoundRect(6, top, 228, height, 10, panel);
    gfx->drawRoundRect(6, top, 228, height, 10, edge);
    gfx->fillRoundRect(8, top + 11, 4, height - 22, 2, provider);
    if (page.usage) {
      text(gfx, row.title, 18, top + 4, 100, 2, provider);
      text(gfx, row.label, 18, top + 22, 100, 2, muted);
      text(gfx, row.text, 130, top + 4, 96, 4, paper);
      gfx->fillRoundRect(18, top + 42, 208, 8, 4, edge);
      const int fill = 208 * row.bar / 100;
      if (fill) {
        const uint16_t bar = row.bar >= 90 ? amber : provider;
        if (fill >= 8) gfx->fillRoundRect(18, top + 42, fill, 8, 4, bar);
        else gfx->fillRect(18, top + 42, fill, 8, bar);
      }
    } else {
      const char* status = row.status;
      const bool waiting = !strcmp(status, "WAITING"), working = !strcmp(status, "WORKING");
      const uint16_t statusColor = waiting ? amber : working ? mint : muted;
      const uint16_t statusFill = gfxTint(waiting ? 0x3A44 : working ? 0x1945 : 0x2946);
      text(gfx, row.title, 18, top + 7, 190, 3, provider);
      gfx->fillCircle(216, top + 17, 4, statusColor);
      const int chipWidth = std::min(208, 18 + static_cast<int>(strlen(status)) * 18);
      gfx->fillRoundRect(18, top + 34, chipWidth, 29, 6, statusFill);
      text(gfx, status, 27, top + 37, 190, 3, statusColor);
      text(gfx, row.count, 18, top + 68, 208, 2, paper);
    }
  }
  if (full || paintedPages_ != data_->pageCount) {
    if (!full) gfx->fillRect(0, 226, 240, 14, ink);
    for (uint8_t i = 0; i < data_->pageCount; ++i) {
      const int x = 120 + int(i) * 16 - int(data_->pageCount - 1) * 8;
      gfx->fillCircle(x, 233, i == page_ ? 4 : 3, i == page_ ? paper : edge);
    }
  }
  painted_ = page; paintedPages_ = data_->pageCount;
  paintedRotate_ = rotate_; paintedValid_ = true; forceFull_ = false;
}
#endif
