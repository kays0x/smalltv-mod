#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
AGENTS_JSON_INCLUDE=${AGENTS_JSON_INCLUDE:-.pio/libdeps/smalltv_esp32_8mb/ArduinoJson/src}
c++ -std=c++11 -Wall -Wextra -Werror -Isrc -Isrc/features/agents -I"$AGENTS_JSON_INCLUDE" tests/agents/test_agents.cpp -o /tmp/smalltv-agents-tests
/tmp/smalltv-agents-tests "${1:-tests/agents/feed.json}"
c++ -std=c++11 -Wall -Wextra -Werror -Isrc/features/agents tests/agents/test_render_plan.cpp -o /tmp/smalltv-agents-render-tests
/tmp/smalltv-agents-render-tests
