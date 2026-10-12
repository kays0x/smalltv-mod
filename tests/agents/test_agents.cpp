#include "AgentsData.h"
#include "TouchGesture.h"
#include <cassert>
#include <fstream>
#include <iterator>
#include <iostream>
#include <string>

static uint32_t ticks = 0;
static TouchGesture::Event sample(TouchGesture& touch, uint32_t raw, unsigned count) {
  auto result = TouchGesture::None;
  for (unsigned i = 0; i < count; ++i) {
    auto event = touch.update(raw, ticks); ticks += 20;
    if (event != TouchGesture::None) result = event;
  }
  return result;
}
int main(int argc, char** argv) {
  TouchGesture touch;
  assert(sample(touch, 100, 50) == TouchGesture::None);
  assert(touch.calibrated && touch.baseline == 100);
  assert(sample(touch, 70, 1) == TouchGesture::None);
  assert(sample(touch, 100, 4) == TouchGesture::None && !touch.pressed);
  assert(sample(touch, 50, 7) == TouchGesture::None && touch.pressed);
  assert(sample(touch, 80, 4) == TouchGesture::None && touch.pressed);
  assert(sample(touch, 100, 4) == TouchGesture::None);
  assert(sample(touch, 100, 19) == TouchGesture::Single);
  // A 40ms contact is a tap; a single 20ms spike above was rejected.
  assert(sample(touch, 50, 2) == TouchGesture::None);
  assert(sample(touch, 100, 2) == TouchGesture::None);
  assert(sample(touch, 100, 19) == TouchGesture::Single);
  sample(touch, 50, 7); sample(touch, 100, 5);
  sample(touch, 50, 7); assert(sample(touch, 100, 4) == TouchGesture::Double);
  assert(sample(touch, 100, 20) == TouchGesture::None);
  sample(touch, 50, 10); sample(touch, 100, 10);
  sample(touch, 50, 10); assert(sample(touch, 100, 4) == TouchGesture::Double);
  assert(sample(touch, 100, 20) == TouchGesture::None);
  assert(sample(touch, 50, 51) == TouchGesture::Hold);
  assert(sample(touch, 50, 60) == TouchGesture::None);
  assert(sample(touch, 100, 24) == TouchGesture::None);
  touch.calibrate(); assert(!touch.calibrated);
  sample(touch, 0, 60); assert(!touch.calibrated);
  sample(touch, 100, 50); ticks = UINT32_MAX - 100;
  sample(touch, 50, 7); sample(touch, 100, 4);
  assert(sample(touch, 100, 20) == TouchGesture::Single);

  assert(smalltv::validAgentsUrl(""));
  assert(smalltv::validAgentsUrl("http://192.0.2.10:9879/agents.json"));
  assert(!smalltv::validAgentsUrl("https://host/agents.json"));
  assert(!smalltv::validAgentsUrl("http://user:secret@host/agents.json"));
  assert(!smalltv::validAgentsUrl("http://host/agents.json?secret=x"));
  assert(!smalltv::validAgentsUrl("http://host/#x"));
  assert(!smalltv::validAgentsUrl("http:///"));
  assert(!smalltv::validAgentsUrl("http://host/\n"));
  TouchGesture drift;
  sample(drift, 100, 50); sample(drift, 108, 500);
  assert(drift.baseline > 100 && drift.baseline <= 108);
  TouchGesture light;
  sample(light, 100, 50);
  assert(light.thresholdPercent() == 88 && light.releasePercent() == 94);
  sample(light, 84, 2); sample(light, 100, 2);
  assert(sample(light, 100, 19) == TouchGesture::Single);
  sample(light, 84, 1); assert(sample(light, 100, 20) == TouchGesture::None);
  light.setThreshold(95); assert(light.releasePercent() == 99);
  light.setThreshold(1); assert(light.thresholdPercent() == 75);
  light.setThreshold(100); assert(light.thresholdPercent() == 95);
  TouchGesture sensor;
  sample(sensor, 1620, 50);
  for (int i = 0; i < 100; ++i) {
    assert(sample(sensor, i % 2 ? 1610 : 1635, 1) == TouchGesture::None);
    assert(!sensor.pressed);
  }
  sample(sensor, 1230, 2); sample(sensor, 1620, 2);
  assert(sample(sensor, 1620, 19) == TouchGesture::Single);
  std::string payload = R"({"sampled":1791760627,"pages":[{"id":"mac","title":"MAC","kind":"agents","rows":[{"title":"CLAUDE","status":"WAITING","count":"1 waiting","detail":"Answer needed","project":"smalltv-mod","elapsed":"","tone":2}]},{"id":"usage","title":"USAGE","kind":"usage","rows":[{"title":"CLAUDE","label":"5h","text":"25%","bar":25}]}]})";
  smalltv::AgentsData data;
  assert(smalltv::parseAgents(payload.c_str(), payload.size(), data));
  assert(data.pageCount == 2 && data.pages[1].usage && data.pages[1].rows[0].bar == 25);
  auto visible = smalltv::agentVisiblePage(data.pages[0]);
  auto altered = data.pages[0];
  strcpy(altered.rows[0].project, "new-project");
  strcpy(altered.rows[0].detail, "Different invisible metadata");
  strcpy(altered.rows[0].elapsed, "2m");
  assert(!smalltv::agentVisibleChanges(visible, smalltv::agentVisiblePage(altered)).any());
  strcpy(altered.rows[0].count, "2 waiting");
  auto diff = smalltv::agentVisibleChanges(visible, smalltv::agentVisiblePage(altered));
  assert(!diff.layout && !diff.header && diff.rows == 1);
  altered = data.pages[0]; strcpy(altered.rows[0].status, "WORKING");
  assert(smalltv::agentVisibleChanges(visible, smalltv::agentVisiblePage(altered)).rows == 1);
  altered = data.pages[0]; altered.rows[0].tone = 1;
  assert(smalltv::agentVisibleChanges(visible, smalltv::agentVisiblePage(altered)).rows == 1);
  altered = data.pages[0]; strcpy(altered.title, "VPS");
  diff = smalltv::agentVisibleChanges(visible, smalltv::agentVisiblePage(altered));
  assert(!diff.layout && diff.header && !diff.rows);
  altered = data.pages[0]; strcpy(altered.id, "vps");
  assert(smalltv::agentVisibleChanges(visible, smalltv::agentVisiblePage(altered)).layout);
  auto usage = smalltv::agentVisiblePage(data.pages[1]);
  altered = data.pages[1]; altered.rows[0].bar = 26;
  assert(smalltv::agentVisibleChanges(usage, smalltv::agentVisiblePage(altered)).rows == 1);
  altered = data.pages[1]; strcpy(altered.rows[0].text, "26%");
  assert(smalltv::agentVisibleChanges(usage, smalltv::agentVisiblePage(altered)).rows == 1);
  altered = data.pages[1]; strcpy(altered.rows[0].label, "7d");
  assert(smalltv::agentVisibleChanges(usage, smalltv::agentVisiblePage(altered)).rows == 1);
  assert(smalltv::agentVisibleChanges(visible, smalltv::agentVisiblePage(data.pages[0], true)).rows == 1);
  auto invalid = payload; invalid.replace(invalid.find("WAITING"), 7, "INVALID");
  assert(!smalltv::parseAgents(invalid.c_str(), invalid.size(), data));
  assert(!strcmp(data.pages[0].rows[0].status, "WAITING"));
  invalid = payload; invalid.replace(invalid.find("25}"), 2, "101");
  assert(!smalltv::parseAgents(invalid.c_str(), invalid.size(), data));
  invalid = payload; invalid.replace(invalid.find("Answer needed"), 13, "No recent lifecycle signal");
  assert(smalltv::parseAgents(invalid.c_str(), invalid.size(), data));
  invalid = payload; invalid.replace(invalid.find("Answer needed"), 13, std::string(48, 'x'));
  assert(smalltv::parseAgents(invalid.c_str(), invalid.size(), data));
  invalid = payload; invalid.replace(invalid.find("Answer needed"), 13, std::string(49, 'x'));
  assert(!smalltv::parseAgents(invalid.c_str(), invalid.size(), data));
  assert(!smalltv::parseAgents("{}", 2, data));
  assert(!smalltv::parseAgents(payload.c_str(), smalltv::AgentsMaxBody + 1, data));
  if (argc > 1) {
    std::ifstream file(argv[1]);
    std::string fixture((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    assert(smalltv::parseAgents(fixture.c_str(), fixture.size(), data));
    assert(data.pageCount == 4);
  }
  std::cout << "Agents feed bounds, URL validation, touch hysteresis/debounce/gestures/rollover passed\n";
}
