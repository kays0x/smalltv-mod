# SmallTV agent dashboard fork

This fork adds a native **Agents** display mode, Pro hardware tap controls, and a
standalone companion bridge. It keeps upstream's ticker, usage meter, radar,
Home Assistant, notification, theme-clock, and Wi-Fi update features.

- **Agents mode**: native cached pages show Mac Claude/Codex, optional VPS
  Claude/Codex, optional VPS Claude/Pi, then Claude-first usage. The device owns
  page switching and rotation; the bridge supplies sanitized data over the LAN.
- **Pro tap controls**: single tap advances a page, double tap switches between
  Agents and an installed clock, and hold pauses or resumes rotation. Sensor
  diagnostics and calibration are available in the Agents tab. Gestures are off
  by default until enabled in settings. Other boards use the same web controls.
- **Standalone bridge**: `daemon/codexbar_bridge`. Configuration, runtime state,
  real device captures, and credentials remain outside the repository. Optional
  SSH export adds VPS activity without opening a server port on the VPS.
- **Optional legacy themes**: `examples/themes/codexbar-usage` provides large
  Clawdmeter-style cards; `examples/themes/agent-work` provides the original
  activity theme. Both remain compatible with upstream smalltv-mod 2.16.0 and
  need no firmware rebuild. Native Agents and touch controls require this fork's
  firmware.

See [Agents setup](docs/src/content/docs/features/agents.md) and
[bridge setup and limitations](daemon/codexbar_bridge/README.md).
The activity reader uses bounded transcript adapters. An unanswered Claude
`AskUserQuestion` is reported as waiting until its matching answer or turn end;
other approval waits and completion percentages are not inferred. There is no
OpenClaw collector. Tests cover lifecycle transitions and sanitized payloads.

The working branch is `feat/agent-dashboard`. Keep `main` tracking upstream and
keep host-local configuration out of commits. `FW_VERSION` stays unchanged;
the maintainer bumps it at release time.
