#pragma once
#include <stdint.h>

// Debounce and gesture timing use elapsed unsigned arithmetic across millis wrap.
class TouchGesture {
 public:
  enum Event { None, Single, Double, Hold };
  static constexpr uint32_t DoubleWindowMs = 250;
  bool pressed = false, calibrated = false;
  uint32_t baseline = 0, raw = 0;
  void setThreshold(uint8_t percent) { thresholdPercent_ = percent < 75 ? 75 : percent > 95 ? 95 : percent; }
  uint8_t thresholdPercent() const { return thresholdPercent_; }
  uint8_t releasePercent() const { return thresholdPercent_ + 6 > 99 ? 99 : thresholdPercent_ + 6; }
  uint32_t pressThreshold() const { return baseline * thresholdPercent() / 100; }
  uint32_t releaseThreshold() const { return baseline * releasePercent() / 100; }
  void calibrate() {
    baseline = 0; calibrated = false; samples_ = 0; sum_ = 0; baselineScaled_ = 0;
    pressed = candidate_ = held_ = pending_ = doubleCandidate_ = false;
  }
  Event update(uint32_t value, uint32_t now) {
    raw = value;
    if (!calibrated) {
      if (!value) return None;
      sum_ += value;
      if (++samples_ == 50) {
        baseline = sum_ / samples_; baselineScaled_ = baseline * 64; calibrated = baseline > 0;
      }
      return None;
    }
    // Classic ESP32 touchRead falls when touched. Release above the hysteresis
    // band; slowly follow temperature drift only while fully released.
    bool next = value < (pressed ? releaseThreshold() : pressThreshold());
    if (next != candidate_) { candidate_ = next; candidateAt_ = now; }
    Event result = None;
    if (candidate_ != pressed && uint32_t(now - candidateAt_) >= 20) {
      pressed = candidate_;
      if (pressed) {
        downAt_ = now; held_ = false;
        // Debounce must not shorten the user's interval for the second press.
        doubleCandidate_ = pending_ && uint32_t(candidateAt_ - releasedAt_) <= DoubleWindowMs;
      }
      else if (!held_ && uint32_t(now - downAt_) >= 20) {
        if (doubleCandidate_) {
          pending_ = false; result = Double;
        } else {
          if (pending_) result = Single;
          pending_ = true; releasedAt_ = now;
        }
      }
    }
    if (pressed && !held_ && uint32_t(now - downAt_) >= 900) {
      held_ = true; pending_ = false; result = Hold;
    }
    const bool awaitingSecondPress = candidate_ && uint32_t(candidateAt_ - releasedAt_) <= DoubleWindowMs;
    if (pending_ && !pressed && !awaitingSecondPress && uint32_t(now - releasedAt_) > DoubleWindowMs) {
      pending_ = false; result = Single;
    }
    if (!pressed && !candidate_ && value >= baseline * 90 / 100 && value <= baseline * 110 / 100)
      {
        // Keep fractional counts so a small temperature drift can accumulate.
        baselineScaled_ = baselineScaled_ - baselineScaled_ / 64 + value;
        baseline = baselineScaled_ / 64;
      }
    return result;
  }
 private:
  bool candidate_ = false, held_ = false, pending_ = false, doubleCandidate_ = false;
  uint32_t candidateAt_ = 0, downAt_ = 0, releasedAt_ = 0, sum_ = 0, baselineScaled_ = 0;
  uint8_t samples_ = 0, thresholdPercent_ = 88;
};
