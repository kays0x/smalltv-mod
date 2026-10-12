#pragma once
#include <ArduinoJson.h>
#include <stdint.h>
#include <memory>
#include <new>
#include <string.h>

namespace smalltv {
constexpr size_t AgentsMaxBody = 6144;
constexpr uint32_t AgentsStaleMs = 45000;
struct AgentRow {
  char title[13] = {}, status[9] = {}, count[22] = {}, detail[49] = {};
  char project[49] = {}, elapsed[49] = {}, label[4] = {}, text[9] = {};
  uint8_t tone = 0, bar = 0;
};
struct AgentPage {
  char id[25] = {}, title[13] = {};
  bool usage = false;
  uint8_t rowCount = 0;
  AgentRow rows[3];
};
struct AgentsData {
  uint32_t sampled = 0;
  uint8_t pageCount = 0;
  AgentPage pages[4];
};
// Only physical-screen content belongs in the repaint cache. Hidden project,
// elapsed and detail metadata must never trigger a display clear.
struct VisibleAgentRow {
  char title[13] = {}, status[9] = {}, count[22] = {}, label[4] = {}, text[9] = {};
  uint8_t tone = 0, bar = 0;
};
struct VisibleAgentPage {
  char id[25] = {}, title[13] = {};
  bool usage = false;
  uint8_t rowCount = 0;
  VisibleAgentRow rows[3];
};
inline VisibleAgentPage agentVisiblePage(const AgentPage& page, bool offline = false) {
  VisibleAgentPage visible;
  strcpy(visible.id, page.id); strcpy(visible.title, page.title);
  visible.usage = page.usage; visible.rowCount = page.rowCount;
  for (uint8_t i = 0; i < page.rowCount; ++i) {
    const auto& row = page.rows[i]; auto& out = visible.rows[i];
    strcpy(out.title, row.title);
    if (page.usage) {
      strcpy(out.label, row.label); strcpy(out.text, offline ? "--" : row.text);
      out.bar = offline ? 0 : row.bar;
    } else {
      strcpy(out.status, offline ? "OFFLINE" : row.status);
      strcpy(out.count, offline ? "BRIDGE OFFLINE" : row.count); out.tone = offline ? 2 : row.tone;
    }
  }
  return visible;
}
struct AgentVisibleChanges {
  bool layout = false, header = false;
  uint8_t rows = 0;
  bool any() const { return layout || header || rows; }
};
inline AgentVisibleChanges agentVisibleChanges(const VisibleAgentPage& before, const VisibleAgentPage& after) {
  AgentVisibleChanges diff;
  diff.layout = strcmp(before.id, after.id) || before.usage != after.usage || before.rowCount != after.rowCount;
  diff.header = strcmp(before.title, after.title) != 0;
  for (uint8_t i = 0; i < after.rowCount; ++i) {
    const auto& a = before.rows[i]; const auto& b = after.rows[i];
    bool changed = strcmp(a.title, b.title) != 0;
    if (after.usage) changed = changed || strcmp(a.label, b.label) || strcmp(a.text, b.text) || a.bar != b.bar;
    else changed = changed || strcmp(a.status, b.status) || strcmp(a.count, b.count) || a.tone != b.tone;
    if (changed) diff.rows |= 1 << i;
  }
  return diff;
}
template<size_t N> bool agentText(JsonVariantConst value, char (&out)[N], bool required = false) {
  if (value.isNull()) return !required;
  if (!value.is<const char*>()) return false;
  const char* text = value.as<const char*>();
  size_t length = strlen(text);
  if (length >= N || (required && !length)) return false;
  for (size_t i = 0; i < length; ++i) if (text[i] < 32 || text[i] > 126) return false;
  memcpy(out, text, length + 1);
  return true;
}
inline bool parseAgents(const char* body, size_t length, AgentsData& output) {
  if (!length || length > AgentsMaxBody) return false;
  JsonDocument doc;
  if (deserializeJson(doc, body, length, DeserializationOption::NestingLimit(6))) return false;
  if (!doc["sampled"].is<uint32_t>() || !doc["pages"].is<JsonArray>()) return false;
  JsonArrayConst pages = doc["pages"].as<JsonArrayConst>();
  if (!pages.size() || pages.size() > 4) return false;
  std::unique_ptr<AgentsData> storage(new(std::nothrow) AgentsData);
  if (!storage) return false;
  AgentsData& data = *storage;
  data.sampled = doc["sampled"].as<uint32_t>();
  if (!data.sampled) return false;
  for (JsonObjectConst p : pages) {
    AgentPage& page = data.pages[data.pageCount++];
    if (!agentText(p["id"], page.id, true) || !agentText(p["title"], page.title, true)) return false;
    for (uint8_t i = 0; i + 1 < data.pageCount; ++i)
      if (!strcmp(data.pages[i].id, page.id)) return false;
    const char* kind = p["kind"] | "";
    page.usage = strcmp(kind, "usage") == 0;
    if (!page.usage && strcmp(kind, "agents") != 0) return false;
    if (!p["rows"].is<JsonArrayConst>()) return false;
    JsonArrayConst rows = p["rows"].as<JsonArrayConst>();
    if (!rows.size() || rows.size() > (page.usage ? 3 : 2)) return false;
    for (JsonObjectConst r : rows) {
      AgentRow& row = page.rows[page.rowCount++];
      if (!agentText(r["title"], row.title, true)) return false;
      if (page.usage) {
        if (!agentText(r["label"], row.label, true) || !agentText(r["text"], row.text, true)) return false;
        if (!r["bar"].is<int>() || r["bar"].as<int>() < 0 || r["bar"].as<int>() > 100) return false;
        row.bar = r["bar"].as<int>();
      } else {
        if (!agentText(r["status"], row.status, true) || !agentText(r["count"], row.count)
            || !agentText(r["detail"], row.detail) || !agentText(r["project"], row.project)
            || !agentText(r["elapsed"], row.elapsed)) return false;
        if (strcmp(row.status, "WORKING") && strcmp(row.status, "WAITING") && strcmp(row.status, "IDLE")
            && strcmp(row.status, "UNKNOWN") && strcmp(row.status, "OFFLINE")) return false;
        if (!r["tone"].is<int>() || r["tone"].as<int>() < 0 || r["tone"].as<int>() > 3) return false;
        row.tone = r["tone"].as<int>();
      }
    }
  }
  output = data;
  return true;
}
inline bool validAgentsUrl(const char* url) {
  size_t n = strlen(url);
  if (!n) return true;
  if (n > 255 || strncmp(url, "http://", 7)) return false;
  const char* host = url + 7;
  if (!*host || *host == '/' || *host == ':') return false;
  for (size_t i = 7; i < n; ++i) {
    unsigned char c = url[i];
    if (c <= 32 || c >= 127 || c == '@' || c == '?' || c == '#' || c == '\\') return false;
  }
  return true;
}
}
