#include "Touch.h"
#include "config.h"
#include <algorithm>
#if defined(SMALLTV_ESP32_PRO)
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
static portMUX_TYPE touchMux = portMUX_INITIALIZER_UNLOCKED;
#define TOUCH_LOCK() portENTER_CRITICAL(&touchMux)
#define TOUCH_UNLOCK() portEXIT_CRITICAL(&touchMux)
#else
#define TOUCH_LOCK()
#define TOUCH_UNLOCK()
#endif

static TouchGesture gesture;
static uint32_t lastRead = 0, reads = 0, minimum = UINT32_MAX, maximum = 0;
static uint32_t singles = 0, doubles = 0, holds = 0;
static TouchGesture::Event lastGesture = TouchGesture::None;
static TouchGesture::Event pending[8];
static uint8_t pendingCount = 0, sensitivity = 88;
static bool actionsEnabled = false, samplerRunning = false;

#if defined(SMALLTV_ESP32_PRO)
static void sampleTouch(void*) {
  TickType_t next = xTaskGetTickCount();
  for (;;) {
    // Driver calls may wait; keep them outside the short shared-state lock.
    // A dedicated task keeps sensing even while a clock frame draws over SPI.
    uint32_t raw = touchRead(TOUCH_PIN);
    uint32_t now = millis();
    TOUCH_LOCK();
    lastRead = now; ++reads;
    minimum = std::min(minimum, raw); maximum = std::max(maximum, raw);
    gesture.setThreshold(sensitivity);
    auto event = gesture.update(raw, now);
    if (event == TouchGesture::Single) ++singles;
    else if (event == TouchGesture::Double) ++doubles;
    else if (event == TouchGesture::Hold) ++holds;
    if (event != TouchGesture::None) {
      lastGesture = event;
      if (actionsEnabled && pendingCount < 8) pending[pendingCount++] = event;
    }
    TOUCH_UNLOCK();
    vTaskDelayUntil(&next, pdMS_TO_TICKS(20));
  }
}
#endif

void touchCalibrate() {
  TOUCH_LOCK();
  gesture.calibrate(); minimum = UINT32_MAX; maximum = 0; pendingCount = 0;
  TOUCH_UNLOCK();
}
void touchService(const Settings& s) {
  TOUCH_LOCK();
  if (actionsEnabled != s.agents.touchEnabled) pendingCount = 0;
  actionsEnabled = s.agents.touchEnabled;
  sensitivity = s.agents.touchSensitivity;
  gesture.setThreshold(sensitivity);
  TOUCH_UNLOCK();
#if defined(SMALLTV_ESP32_PRO)
  if (!samplerRunning)
    samplerRunning = xTaskCreate(sampleTouch, "touch-sample", 4096, nullptr, 1, nullptr) == pdPASS;
#endif
}
TouchGesture::Event touchTake() {
  TOUCH_LOCK();
  auto result = pendingCount ? pending[0] : TouchGesture::None;
  if (pendingCount) {
    --pendingCount;
    for (uint8_t i = 0; i < pendingCount; ++i) pending[i] = pending[i + 1];
  }
  TOUCH_UNLOCK();
  return result;
}
void touchStatus(JsonObject o, const Settings& s) {
  // Copy first, then allocate JSON outside the lock so the sampler can continue.
  TOUCH_LOCK();
  const uint32_t raw = gesture.raw, baseline = gesture.baseline;
  const uint32_t low = minimum == UINT32_MAX ? 0 : minimum, high = maximum;
  const uint32_t single = singles, twice = doubles, hold = holds, count = reads, sampled = lastRead;
  const bool pressed = gesture.pressed, calibrated = gesture.calibrated;
  const auto event = lastGesture;
  const uint8_t queued = pendingCount, threshold = gesture.thresholdPercent(), release = gesture.releasePercent();
  const uint32_t pressRaw = gesture.pressThreshold(), releaseRaw = gesture.releaseThreshold();
  TOUCH_UNLOCK();
#if defined(SMALLTV_ESP32_PRO)
  o["supported"] = true;
#else
  o["supported"] = false;
#endif
  o["enabled"] = s.agents.touchEnabled; o["raw"] = raw; o["baseline"] = baseline;
  o["min"] = low; o["max"] = high;
  o["pressed"] = pressed; o["calibrated"] = calibrated;
  o["single"] = single; o["double"] = twice; o["hold"] = hold;
  o["lastGesture"] = event == TouchGesture::Single ? "single" : event == TouchGesture::Double ? "double"
      : event == TouchGesture::Hold ? "hold" : "none";
  o["samplerRunning"] = samplerRunning; o["samples"] = count;
  o["sampleAgeMs"] = count ? uint32_t(millis() - sampled) : 0;
  o["queued"] = queued;
  o["thresholdPercent"] = threshold; o["releasePercent"] = release;
  o["pressThreshold"] = pressRaw; o["releaseThreshold"] = releaseRaw;
}
