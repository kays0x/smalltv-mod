# SmallTV agent dashboard fork

This fork keeps upstream firmware intact and adds a reproducible host bridge
and two theme clocks in the first revision:

- **CodexBar Usage**: large Clawdmeter-style cards, Claude first, then Codex's
  weekly allowance. Source: `examples/themes/codexbar-usage`.
- **Agent Work**: observed local Claude/Codex session activity, active count,
  elapsed time, project basename, and last event category. Source:
  `examples/themes/agent-work`.
- **Standalone bridge**: `daemon/codexbar_bridge`. Configuration, runtime state,
  real device captures, and credentials remain outside the repository.

See [bridge setup and limitations](daemon/codexbar_bridge/README.md). Its current
activity reader uses bounded transcript adapters; it does not claim to know
approval-wait states or completion percentages. Tests cover lifecycle transitions
and sanitized display payloads. Both themes use the firmware's own validator
and work with smalltv-mod 2.16.0. No firmware rebuild is necessary for them.

The working branch is `feat/agent-dashboard`. Keep `main` tracking upstream and
keep host-local configuration out of commits.

Possible next additions are a dedicated Agents display mode, the Pro's tap
button for switching views, supported lifecycle-hook input, and a sanitized VPS
exporter. Those are not implemented by this revision.
