#include "AgentsRender.h"
#include <cassert>
#include <iostream>
#include <memory>

int main() {
  auto full = smalltv::agentsPaintPlan(true, true, true, 7, 3, true, true);
  assert(full.count == 1 && full.regions[0].width == 240 && full.regions[0].height == 240);
  assert(full.regions[0].offset() == 0 && full.regions[0].skip() == 0);
  auto none = smalltv::agentsPaintPlan(false, false, false, 0, 3, true, false);
  assert(none.count == 0);
  auto card = smalltv::agentsPaintPlan(false, false, false, 2, 2, false, false);
  assert(card.count == 1);
  const auto& r = card.regions[0];
  assert(r.x == 6 && r.y == 133 && r.width == 228 && r.height == 88);
  assert(r.offset() == 133 * 240 + 6 && r.skip() == 12);
  assert(r.offset() + (r.height - 1) * (r.width + r.skip()) + r.width <= smalltv::AgentsCanvasBytes);
  auto usage = smalltv::agentsPaintPlan(false, true, true, 7, 3, true, true);
  assert(usage.count == 6);
  assert(usage.regions[4].y == 161 && usage.regions[4].height == 56);
  assert(usage.regions[5].y == 226 && usage.regions[5].height == 14);
  for (uint8_t i = 0; i < usage.count; ++i) {
    const auto& area = usage.regions[i];
    assert(area.width + area.skip() == 240);
    assert(area.offset() + (area.height - 1) * 240 + area.width <= smalltv::AgentsCanvasBytes);
  }
  smalltv::AgentsPaintPlan invalid;
  invalid.add(-1, 0, 240, 240); invalid.add(0, 239, 240, 2);
  assert(invalid.count == 0);
  std::unique_ptr<uint8_t[]> frame(new uint8_t[smalltv::AgentsCanvasBytes]);
  uint16_t palette[256] = {};
  palette[1] = 0xF800; palette[2] = 0x07E0; palette[3] = 0x001F; palette[4] = 0x1234;
  for (int y = 0; y < 240; ++y)
    for (int x = 0; x < 240; ++x) frame[y * 240 + x] = (x + y) % 4 + 1;
  uint16_t stripe[smalltv::AgentsStripePixels];
  for (auto& value : stripe) value = 0xDEAD;
  smalltv::AgentsPaintRegion crop;
  crop.x = 6; crop.y = 133; crop.width = 228; crop.height = 10;
  assert(smalltv::agentsConvertStripe(frame.get(), palette, crop, 0, stripe, smalltv::AgentsStripePixels) == 8);
  for (int y = 0; y < 8; ++y)
    for (int x = 0; x < 228; ++x)
      assert(stripe[y * 228 + x] == palette[frame[(133 + y) * 240 + 6 + x]]);
  for (auto& value : stripe) value = 0xDEAD;
  assert(smalltv::agentsConvertStripe(frame.get(), palette, crop, 8, stripe, smalltv::AgentsStripePixels) == 2);
  assert(stripe[0] == palette[frame[141 * 240 + 6]]);
  assert(stripe[455] == palette[frame[142 * 240 + 233]]);
  assert(stripe[456] == 0xDEAD);
  assert(smalltv::agentsConvertStripe(frame.get(), palette, crop, 10, stripe, smalltv::AgentsStripePixels) == 0);
  assert(smalltv::agentsConvertStripe(frame.get(), palette, crop, 0, stripe, 227) == 0);
  assert(smalltv::agentsConvertStripe(frame.get(), palette, full.regions[0], 0, stripe, smalltv::AgentsStripePixels) == 8);
  assert(stripe[0] == 0xF800 && stripe[1] == 0x07E0 && stripe[2] == 0x001F && stripe[3] == 0x1234);
  std::cout << "Agents buffered paint regions, bounds, RGB565 palette, stride and stripe tail passed\n";
}
