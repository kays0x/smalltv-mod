#pragma once
#include <stdint.h>
#include <stddef.h>

namespace smalltv {
constexpr int AgentsRenderWidth = 240;
constexpr int AgentsRenderHeight = 240;
constexpr size_t AgentsCanvasBytes = AgentsRenderWidth * AgentsRenderHeight;
constexpr int AgentsStripeRows = 8;
constexpr size_t AgentsStripePixels = AgentsRenderWidth * AgentsStripeRows;
constexpr size_t AgentsStripeBytes = AgentsStripePixels * sizeof(uint16_t);
struct AgentsPaintRegion {
  int16_t x = 0, y = 0, width = 0, height = 0;
  size_t offset() const { return size_t(y) * AgentsRenderWidth + x; }
  int16_t skip() const { return AgentsRenderWidth - width; }
};
struct AgentsPaintPlan {
  AgentsPaintRegion regions[6];
  uint8_t count = 0;
  void add(int16_t x, int16_t y, int16_t width, int16_t height) {
    if (count >= 6 || x < 0 || y < 0 || width <= 0 || height <= 0
        || x + width > AgentsRenderWidth || y + height > AgentsRenderHeight) return;
    auto& region = regions[count++];
    region.x = x; region.y = y; region.width = width; region.height = height;
  }
};
inline AgentsPaintPlan agentsPaintPlan(bool full, bool header, bool rotation,
                                      uint8_t rowMask, uint8_t rowCount, bool usage, bool dots) {
  AgentsPaintPlan plan;
  if (full) { plan.add(0, 0, 240, 240); return plan; }
  if (header) plan.add(0, 0, 198, 35);
  if (rotation) plan.add(203, 3, 33, 33);
  for (uint8_t i = 0; i < rowCount && i < 3; ++i)
    if (rowMask & (1 << i)) plan.add(6, 39 + i * (usage ? 61 : 94), 228, usage ? 56 : 88);
  if (dots) plan.add(0, 226, 240, 14);
  return plan;
}
// The RAM bitmap overload takes native RGB565 words. The SPI driver performs
// MSB-first conversion itself; swapping palette entries here would swap colours.
inline uint8_t agentsConvertStripe(const uint8_t* frame, const uint16_t* palette,
                                  const AgentsPaintRegion& region, int16_t startRow,
                                  uint16_t* output, size_t capacity) {
  if (!frame || !palette || !output || region.x < 0 || region.y < 0 || region.width <= 0 || region.height <= 0
      || region.x + region.width > AgentsRenderWidth || region.y + region.height > AgentsRenderHeight
      || startRow < 0 || startRow >= region.height || capacity < static_cast<size_t>(region.width)) return 0;
  uint8_t rows = region.height - startRow < AgentsStripeRows ? region.height - startRow : AgentsStripeRows;
  if (size_t(rows) * region.width > capacity) rows = capacity / region.width;
  for (uint8_t y = 0; y < rows; ++y) {
    const uint8_t* source = frame + size_t(region.y + startRow + y) * AgentsRenderWidth + region.x;
    for (int16_t x = 0; x < region.width; ++x) output[size_t(y) * region.width + x] = palette[source[x]];
  }
  return rows;
}

}
