# CodexBar and agent activity bridge

A standalone, read-only bridge for SmallTV theme clocks and the native Agents
mode in this fork. It does not modify
CodexBar, Codex, Claude Code, their logins, or their hook configuration.

The usage theme puts Claude first with five-hour and weekly allowances, then
Codex with its weekly allowance. Values are **used percentages**. A missing
window is `n/a`; an actual zero remains `0%`. The original Claude-only
Clawdmeter also receives native usage pushes.

The Agent Work theme shows each provider's observed state, active root/session
count, elapsed turn time, project basename, and last activity category. It never
exports prompts, replies, tool arguments, credentials, full paths, or transcript
files. No captures or live configuration belong in this repository.

With the optional remote collector enabled, the legacy theme rotates every 20 seconds
between Mac Claude/Codex, VPS Claude/Codex, and VPS Claude/Pi. Each page has a
MAC or VPS timestamp label. Without a remote collector it stays on the Mac page.

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
`/agent-codex.json`, plus `/agent-top.json` and `/agent-bottom.json` for the rotating
dashboard. Responses contain only small display fields. `status.json`
records sanitized values and the last request from the configured device, so
testing a local endpoint is distinguishable from actual SmallTV polling.

## Native Agents mode feed

The native firmware mode consumes `http://<bridge-lan-address>:9879/agents.json`.
Unlike the theme's rotating top/bottom feeds, every request returns all pages in
the same order. The device owns page selection, automatic rotation and touch
gestures; polling the bridge never advances the selected page. The older quota
and theme endpoints continue to work.

The response is a compact JSON object with `sampled` (the current host Unix
timestamp in seconds) and `pages`. There are at most four pages:

| ID | Title | Kind | Rows |
| --- | --- | --- | --- |
| `mac` | `MAC` | `agents` | Claude, Codex |
| `vps-codex` | `VPS` | `agents` | Claude, Codex |
| `vps-pi` | `VPS` | `agents` | Claude, Pi |
| `usage` | `USAGE` | `usage` | Claude 5h, Claude 7d, Codex 7d |

The two VPS pages are omitted when the remote collector is not configured. The
Mac and usage pages are always present, including while sources are unavailable.
Each page has only `id`, `title`, `kind`, and `rows`; rows are bounded to two for
agents and three for usage. An example agent row is:

```json
{
  "title": "CLAUDE",
  "status": "WAITING",
  "count": "1 waiting",
  "elapsed": "",
  "project": "example-project",
  "detail": "Answer needed",
  "active": 0,
  "waiting": 1,
  "tone": 2
}
```

Agent states are `WORKING`, `WAITING`, `IDLE`, `UNKNOWN`, and `OFFLINE`. Counts
are bounded to 32 sessions. `tone` is 0 for idle, 1 for work, and 2 for waiting,
unknown or offline. Waiting and active counts can coexist; waiting takes display
priority. Display strings contain at most 48 printable ASCII characters.
Provider titles and count text are rebuilt by the bridge, not accepted from
transcript fields. Every public row is explicitly whitelisted.

Usage rows have only `title`, `label`, `text`, and `bar`, for example:

```json
{"title":"CLAUDE","label":"5h","text":"25%","bar":25}
```

Bars represent used percentages from 0 through 100. Unavailable or stale
windows use `text: "n/a"` and `bar: 0`; actual zero usage uses `text: "0%"`.
The Codex five-hour window is omitted. There are no reset-countdown fields,
account identities, prompts, credentials or raw transcript content.

`sampled` measures host response freshness, not the age of a remote observation.
Expired remote observations become OFFLINE on every request after the configured
remote maximum age, even if the last SSH poll succeeded. Failed SSH polls also
become OFFLINE immediately. The firmware must independently indicate stale data
when it can no longer fetch the bridge; receiving a complete document updates
its cached pages. Responses have `Cache-Control: no-store`. The existing LAN
source-address restriction applies to this endpoint too.

`status.json` tracks total native feed requests under `http_requests.agents` and
the last confirmed device poll under `device_requests.agents`. These counters
are independent of the legacy theme's `agent-top` and `agent-bottom` requests.

## Optional VPS collector

Install `activity.py` and `export_activity.py` together in a private directory on
the VPS. The exporter reads that host's session directories locally and emits
only sanitized display fields. Verify it with Python 3.9+ on that host.

Add this block to the Mac's private configuration, using an existing SSH host
and the absolute exporter path:

```json
"remote_activity": {
  "ssh_host": "my-vps",
  "exporter": "/path/to/private/export_activity.py",
  "refresh_seconds": 15,
  "max_age_seconds": 45
}
```

Restart the bridge. SSH uses existing authentication with `BatchMode=yes`, a
five-second connection timeout and a twelve-second command timeout. It opens no
VPS HTTP port, copies no credentials or transcripts, and does not install hooks
or a remote service. Failed polls immediately show OFFLINE; successful snapshots
also expire after 45 seconds. The Mac must remain awake to collect and serve.

## Activity semantics and limits

- Codex `task_started` begins work; `task_complete`, `turn_aborted`, and
  `task_failed` end the matching turn. Turn end is **not proof of task success**.
- Claude user prompts begin work; tool-result records do not restart elapsed
  time. Assistant `end_turn` and system `turn_duration` records end a turn.
  An unanswered `AskUserQuestion` shows `WAITING` and `Answer needed`, including
  after the 15-minute work cutoff. A matching tool result resumes work; a new
  user prompt or turn end clears the wait. Waiting sessions take display
  priority over working sessions. Question text and choices are never exported.
- Pi user messages begin work. Assistant `toolUse` and tool-result records retain
  work; `stop`, `error`, and `aborted` end the turn. Trace files are excluded so
  they do not duplicate native session records.
- Cost metadata and file modification times never establish active work.
- An unfinished turn with no recent event for 15 minutes becomes `UNKNOWN`,
  not `IDLE`. Missing roots are `OFFLINE`. This conservative cutoff can also
  mark a legitimate long, quiet operation unknown.
- The adapter reads at most 32 recent files per provider, over a 48-hour lookback,
  and a bounded 4 MiB tail per newly discovered file. Claude nested subagent
  files and sidechain records are not included in this first version.
- Transcript formats can change. They are not a stable public interface.
  Lifecycle hooks or app-server events are a future replacement for this
  adapter. Generic permission waits and true completion percentages are not inferred.
- VPS agents are not connected by default. Enable the collector above to include
  them. Remote adapters have the same bounded lookback and lifecycle limitations.
- The host must remain awake. If it becomes unreachable, theme firmware retains
  its last fetched values. Check the update timestamp. Address changes require
  rebuilding the theme and restarting the listener with the new bind address.

## Validation

```sh
cd daemon/codexbar_bridge
python3 -m unittest -v test_bridge.py test_activity.py test_remote_activity.py
```

Tests cover matching turn transitions, interrupted turns, late completion,
partial JSONL writes, metadata-only updates, unavailable/stale quota windows,
percentage direction, and omission of transcript text from display payloads.
Tests also cover complete native page order, question waits, quota freshness,
remote expiry, device poll accounting, and strict public field whitelisting.
Theme packing and previews use the shared firmware renderer. The bridge and
legacy themes still work with upstream 2.16.0; the native Agents mode requires
this fork's firmware build.
