#pragma once
#include "Mode.h"
#include "AgentsData.h"
#include <atomic>
#include <memory>

struct AgentsFetch {
  String url;
  smalltv::AgentsData data;
  bool ok = false;
  std::atomic<bool> done{false}, cancelled{false};
};
class AgentsMode : public DisplayMode {
 public:
  const char* id() const override { return "agents"; }
  uint8_t modeConst() const override { return MODE_AGENTS; }
  void begin(const Settings& s) override;
  void service(const Settings& s) override;
  void invalidate(const Settings& s) override;
  void wake(const Settings&) override { dirty_ = true; forceFull_ = true; }
  void next();
  void toggleRotation();
  void status(JsonObject o) const;
 private:
  std::unique_ptr<smalltv::AgentsData> data_;
  std::shared_ptr<AgentsFetch> fetch_;
  uint32_t nextPoll_ = 0, lastOk_ = 0, lastPage_ = 0;
  uint32_t fullPaints_ = 0, cardPaints_ = 0;
  uint32_t bufferedPaints_ = 0, fallbackPaints_ = 0, lastPaintMs_ = 0;
  bool lastPaintBuffered_ = false, waitingPainted_ = false, waitingError_ = false;
  uint8_t page_ = 0, paintedPages_ = 0;
  smalltv::VisibleAgentPage painted_;
  bool paintedValid_ = false, paintedRotate_ = false, forceFull_ = true;
  bool rotate_ = true, dirty_ = true, error_ = false, wasFresh_ = false;
  bool fresh() const;
  void draw();
};
extern AgentsMode g_agentsMode;
