#!/usr/bin/env python3
"""Run on the remote host; stdout contains only sanitized activity snapshots."""
import json
import time
from activity import Activity


def main():
    reader = Activity({'claude': '~/.claude/projects', 'codex': '~/.codex/sessions',
                       'pi': '~/.pi/agent/sessions'})
    print(json.dumps({'sampled': time.time(),
                      'agents': {p: reader.snapshot(p) for p in reader.roots}}))


if __name__ == '__main__':
    main()
