---
title: Agent activity and tap controls
description: Native Mac and VPS agent pages, Claude-first usage, and hardware tap controls on the SmallTV Pro.
---

**Agents** is a native display mode in this fork. It fetches a small companion
feed, keeps the pages on the device, and switches immediately using that cache.
It does not require an Agent Work theme package. The original activity and
CodexBar usage themes remain available for upstream firmware.

## Set up the feed

1. Run the companion bridge from `daemon/codexbar_bridge` on a computer that
   stays reachable on your LAN. See its README for provider and optional SSH
   exporter configuration.
2. Open the device's **Agents** tab. Set **Companion feed URL** to the bridge's
   LAN URL, for example `http://bridge.local:9879/agents.json`. The device must be
   able to resolve and reach that address; `localhost` would address the device
   itself.
3. Choose **Agents** under **Display → Mode**, then **Save settings**.

The companion supplies four pages: Mac Claude/Codex, VPS Claude/Codex,
VPS Claude/Pi, then usage. VPS pages require the optional SSH exporter. Claude
comes first on usage pages; unavailable Codex five-hour usage is omitted.
OpenClaw is not collected. Credentials, full paths, prompts, question text,
and transcripts stay on the host; the screen receives sanitized display fields.

**Refresh data** defaults to 5 seconds (2–300). **Show each page** defaults to
20 seconds (5–3600). Disable **Automatically rotate pages** to leave switching
manual. A lost feed shows stale or unavailable status instead of pretending its
cached activity is current. The Agents tab shows fetch status, age, page, and
errors, and its web buttons work on boards without a touch sensor.

The physical display uses coloured provider cards, 24-pixel headings and status,
and 32-pixel usage percentages. Text never shrinks below 16 pixels. Project,
event-detail, and elapsed-time subtitles are omitted from the physical cards.
When data changes on the current page, only its cards repaint; the header and
page indicators stay in place. A page switch redraws the new page.

The overall Display carousel also has an **Agents** checkbox. This controls
rotation between modes; the Agents page interval controls rotation within this
mode.

## Set up the Pro's touch sensor

The Pro has a capacitive touch sensor. Other display boards support Agents mode
and the web controls, but show that hardware touch is unavailable.

Gestures are **off by default**. The sensor's live raw value, baseline, pressed
state, and gesture counters are still readable while gestures are disabled.
The Pro samples the sensor in an independent 20-millisecond task, including
while an animated clock is drawing. Short noise spikes are rejected.

1. Open **Agents → Hardware tap** and leave the device untouched.
2. Press **Calibrate untouched sensor**.
3. Touch and release the top of the Pro. Check that the raw reading changes and
   the pressed state responds. Keep your hand off it when recalibrating.
4. Enable **the Pro's touch sensor** and **Save settings**.

**Touch sensitivity** defaults to 88% of the untouched baseline and accepts
75–95%. A higher percentage detects lighter contact; reduce it if gestures fire
without touching the device. Raise it if a deliberate tap changes the raw value
but never crosses the displayed press threshold. Saving applies the threshold
and starts a fresh calibration, so keep your hand off the top while saving.
The live diagnostics show raw and baseline values, minimum and maximum readings,
press and release thresholds, and recognized gesture counts. Separate press and
release thresholds reduce repeated triggers from a noisy reading.

| Gesture | Action |
| --- | --- |
| Single tap | Next cached page, including usage |
| Double tap | Switch between Agents and the selected clock |
| Hold | Pause or resume automatic page rotation |
| Tap while dimmed | Wake first, without advancing a page |

Install a clock package in **Display → Theme clocks**, then choose it under
**Agents → Clock for double tap** and save. This choice does not activate the
clock immediately. The **Switch clock / agents** web button exercises the same
switching path; without a selected clock it reports an error. The clock uses the
normal timezone and resumes notifications as usual.

Use the live gesture counters to distinguish recognized taps from screen data
changes. The web controls verify mode behavior; they do not prove a physical
sensor works on a particular unit.

## Activity accuracy

The bridge reads bounded lifecycle records from Claude Code, Codex, and Pi.
An unanswered Claude `AskUserQuestion` reports **WAITING** until its matching
answer arrives or the turn ends. Other states reflect observed lifecycle events,
not guessed progress percentages. The collector is a fallback for terminals or
agent versions that do not report supported program-status events.

## HTTP API

Routes follow the device's optional digest authentication. Failed requests
return JSON with an `error` field.

| Method and route | Request or result |
| --- | --- |
| `GET /api/agents/status` | `valid`, `fresh`, `error`, `ageSec`, `pages`, zero-based `page`, `title`, `autoRotate`, `fetching`, `clockActive`, `fullPaints`, `cardPaints` |
| `POST /api/agents/control` | JSON `{ "action": "next" }`, `toggleRotation`, or `toggleClock`; returns current status |
| `GET /api/touch` | `supported`, `enabled`, `raw`, `baseline`, `min`, `max`, `pressed`, `calibrated`, `pressThreshold`, `releaseThreshold`, `thresholdPercent`, `releasePercent`, `single`, `double`, `hold`, `lastGesture`, `samplerRunning`, `samples`, `sampleAgeMs`, `queued` |
| `POST /api/touch/calibrate` | JSON `{}`; calibrates an untouched sensor and returns its status |

Settings backup and restore include the root `agents` object:

```json
{
  "mode": "agents",
  "carouselAgents": false,
  "agents": {
    "url": "http://bridge.local:9879/agents.json",
    "refreshSec": 5,
    "pageSec": 20,
    "autoRotate": true,
    "clockThemeId": "",
    "touchEnabled": false,
    "touchSensitivity": 88
  }
}
```

This feature requires a firmware build from this fork. Use the normal OTA app
image for your exact board in **System → Manual update**; factory images are for
cable installation and recovery. Installing a theme alone cannot add hardware
input handling.

## Build this fork

The ESP32 platform URL is pinned to 55.03.311 rather than the rolling stable
asset. Pin both PlatformIO cores too; the ESP32 builder uses its own environment.
From the repository root, with PlatformIO 6.1.19 installed:

```sh
export PIP_CONSTRAINT="$PWD/tools/pio-constraints.txt"
export UV_CONSTRAINT="$PWD/tools/pio-constraints.txt"
pio run -e smalltv_esp32_8mb
```

For the Pro, upload `.pio/build/smalltv_esp32_8mb/firmware.bin` over Wi-Fi.
Do not upload `firmware.factory.bin` or a partition image through OTA. Run board
builds sequentially; package installation can move shared tool paths.
For a multi-chip build matrix, give each board its own `PLATFORMIO_BUILD_DIR`
(for example, `$PWD/.pio/build-pro` for the Pro). Shared library objects can
otherwise survive a C2-to-classic-ESP32 switch with the wrong architecture.
