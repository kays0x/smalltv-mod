# CodexBar and agent activity bridge

A standalone, read-only bridge for SmallTV theme clocks. It does not modify
CodexBar, Codex, Claude Code, their logins, or their hook configuration.

The usage theme puts Claude first with five-hour and weekly allowances, then
Codex with its weekly allowance. Values are **used percentages**. A missing
window is `n/a`; an actual zero remains `0%`. The original Claude-only
Clawdmeter also receives native usage pushes.

The Agent Work theme shows each provider's observed state, active root/session
count, elapsed turn time, project basename, and last activity category. It never
exports prompts, replies, tool arguments, credentials, full paths, or transcript
files. No captures or live configuration belong in this repository.

## Setup

1. Install the official CodexBar CLI and verify `codexbar usage --format json`
   works for the intended current account. Account selection is outside this
   bridge. `claude: auto` and `codex: oauth` are example source choices.
2. Copy `config.example.json` to a private `config.json`, replacing the example
   addresses and CLI path. `activity_roots` selects local transcript directories.
3. Run `python3 bridge.py --config config.json`. Python 3.9+ is sufficient for
   serving; choose a runtime with the necessary local-network permissions.
   The HTTP listener binds to the configured LAN IP and accepts only the device,
   that Mac, and loopback source addresses. No public listener is needed.
4. Build the packages with the repository's theme dependencies installed:

   ```sh
   python3 daemon/codexbar_bridge/prepare_theme.py \
     --config /path/to/private/config.json --kind agents \
     --theme-id agent-work-v1 --output /tmp/agent-work.stheme
   ```

   Use `--kind usage` to build the usage screen. See the upstream theme guide for
   Pillow, C++ and ArduinoJson/GFX dependencies, including the two include-path
   environment variables. The packer runs the actual firmware validator.
5. Install the package under Display → Theme clocks and select Use theme.
   Both screens run on smalltv-mod 2.16.0; no firmware replacement is needed.
   A new installed revision needs a fresh theme ID; keep earlier layouts until
   the replacement works.

Endpoints are `/claude.json`, `/codex.json`, `/agent-claude.json`, and
`/agent-codex.json`. Responses contain only small display fields. `status.json`
records sanitized values and the last request from the configured device, so
testing a local endpoint is distinguishable from actual SmallTV polling.

## Activity semantics and limits

- Codex `task_started` begins work; `task_complete`, `turn_aborted`, and
  `task_failed` end the matching turn. Turn end is **not proof of task success**.
- Claude user prompts begin work; tool-result records do not restart elapsed
  time. Assistant `end_turn` and system `turn_duration` records end a turn.
- Cost metadata and file modification times never establish active work.
- An unfinished turn with no recent event for 15 minutes becomes `UNKNOWN`,
  not `IDLE`. Missing roots are `OFFLINE`. This conservative cutoff can also
  mark a legitimate long, quiet operation unknown.
- The adapter reads at most 32 recent files per provider, over a 48-hour lookback,
  and a bounded 4 MiB tail per newly discovered file. Claude nested subagent
  files and sidechain records are not included in this first version.
- Transcript formats can change. They are not a stable public interface.
  Lifecycle hooks or app-server events are a future replacement for this
  adapter. Approval-wait state and true completion percentages are not inferred.
- VPS agents are not connected by default. Add a separate sanitized exporter
  on that host; do not copy raw transcripts to this bridge.
- The host must remain awake. If it becomes unreachable, theme firmware retains
  its last fetched values. Check the update timestamp. Address changes require
  rebuilding the theme and restarting the listener with the new bind address.

## Validation

```sh
cd daemon/codexbar_bridge
python3 -m unittest -v test_bridge.py test_activity.py
```

Tests cover matching turn transitions, interrupted turns, late completion,
partial JSONL writes, metadata-only updates, unavailable/stale quota windows,
percentage direction, and omission of transcript text from display payloads.
Theme packing and previews use the shared firmware renderer. This addition
changes host tools and theme data, not the device's firmware or partition layout.
