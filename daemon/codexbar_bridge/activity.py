"""Read local lifecycle events without exporting prompts, replies, or tool arguments.

Transcript schemas are an adapter boundary, not a supported public API. Unknown
or incomplete turns stay unknown; timestamps alone never establish activity.
"""
import datetime as dt
import json
from pathlib import Path
import time

MAX_TAIL = 4 * 1024 * 1024
LOOKBACK = 48 * 60 * 60
ACTIVE_GRACE = 15 * 60


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except ValueError:
        return None


def display_text(value, length=48):
    return ''.join(c for c in str(value) if 32 <= ord(c) < 127)[:length]


def elapsed_text(seconds):
    minutes = max(0, int(seconds) // 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}h {minutes:02d}m' if hours else f'{minutes}m'


class Session:
    def __init__(self, provider):
        self.provider = provider
        self.state = 'unknown'
        self.turn_id = None
        self.started = None
        self.updated = 0
        self.project = '--'
        self.activity = 'No lifecycle event'

    def apply(self, row):
        if not isinstance(row, dict):
            return
        provider = self.provider
        kind = row.get('type')
        payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
        when = timestamp(row.get('timestamp'))
        cwd = payload.get('cwd') if kind == 'session_meta' else row.get('cwd')
        if isinstance(cwd, str):
            self.project = display_text(Path(cwd).name) or '--'
        if when is None:
            return
        if provider == 'codex':
            if kind == 'event_msg':
                event = payload.get('type')
                if event == 'task_started':
                    self.state, self.started = 'working', when
                    self.turn_id = payload.get('turn_id')
                    self.activity = 'Turn started'
                elif event in ('task_complete', 'turn_aborted', 'task_failed'):
                    turn_id = payload.get('turn_id')
                    # A late completion from a prior turn must not end a newer turn.
                    if self.turn_id and turn_id and self.turn_id != turn_id:
                        return
                    self.state = 'idle'
                    self.activity = {'task_complete': 'Turn ended', 'turn_aborted': 'Interrupted',
                                     'task_failed': 'Turn failed'}[event]
                elif event == 'item_completed':
                    item = payload.get('item', {})
                    item_type = item.get('type', '') if isinstance(item, dict) else ''
                    self.activity = 'Last: tool' if 'tool' in item_type or 'call' in item_type else 'Last: activity'
                elif event != 'token_count':
                    return
                self.updated = max(self.updated, when)
            elif kind == 'response_item' and self.state == 'working':
                if payload.get('type') in ('function_call', 'custom_tool_call'):
                    self.activity = 'Last: tool'
                self.updated = max(self.updated, when)
        elif provider == 'claude':
            if row.get('isSidechain') or (row.get('isMeta') and kind != 'system'):
                return
            message = row.get('message', {})
            content = message.get('content', []) if isinstance(message, dict) else []
            blocks = content if isinstance(content, list) else []
            if kind == 'user':
                is_result = any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in blocks)
                if not is_result:
                    self.state, self.started = 'working', when
                    self.activity = 'Turn started'
                elif self.state == 'working':
                    self.activity = 'Last: tool result'
                self.updated = max(self.updated, when)
            elif kind == 'assistant' and isinstance(message, dict):
                if message.get('stop_reason') == 'end_turn':
                    self.state, self.activity = 'idle', 'Turn ended'
                elif any(isinstance(b, dict) and b.get('type') == 'tool_use' for b in blocks):
                    self.activity = 'Last: tool'
                self.updated = max(self.updated, when)
            elif kind == 'system' and row.get('subtype') == 'turn_duration':
                self.state, self.activity = 'idle', 'Turn ended'
                self.updated = max(self.updated, when)


class Transcript:
    def __init__(self, path, provider):
        self.path = path
        self.session = Session(provider)
        self.offset = 0
        self.pending = b''
        self.identity = None

    def update(self):
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if self.identity != identity or stat.st_size < self.offset:
            self.session = Session(self.session.provider)
            self.offset = max(0, stat.st_size - MAX_TAIL)
            self.pending = b''
            self.identity = identity
            # Metadata can precede the bounded tail of a long conversation.
            with self.path.open('rb') as source:
                first = source.readline(128 * 1024)
            try:
                self.session.apply(json.loads(first))
            except (ValueError, TypeError):
                pass
        with self.path.open('rb') as source:
            source.seek(self.offset)
            block = source.read(MAX_TAIL)
            self.offset += len(block)
        lines = (self.pending + block).split(b'\n')
        self.pending = lines.pop()
        if len(self.pending) > MAX_TAIL:
            self.pending = b''
        for line in lines:
            try:
                self.session.apply(json.loads(line))
            except (ValueError, TypeError):
                continue


class Activity:
    def __init__(self, roots):
        self.roots = {p: Path(root).expanduser() for p, root in roots.items()}
        self.cache = {}

    def snapshot(self, provider, now=None):
        now = time.time() if now is None else now
        root = self.roots[provider]
        pattern = '*/*/*/*.jsonl' if provider == 'codex' else '*/*.jsonl'
        candidates = []
        if root.is_dir():
            for path in root.glob(pattern):
                try:
                    modified = path.stat().st_mtime
                    if modified >= now - LOOKBACK and not path.parent.name.startswith('codexbar-'):
                        candidates.append((modified, path))
                except OSError:
                    continue
        sessions = []
        for _, path in sorted(candidates, reverse=True)[:32]:
            key = (provider, path)
            transcript = self.cache.setdefault(key, Transcript(path, provider))
            try:
                transcript.update()
                if transcript.session.updated >= now - LOOKBACK:
                    sessions.append(transcript.session)
            except OSError:
                continue
        # Drop cached files that no longer participate; memory stays bounded.
        retained = {(provider, path) for _, path in sorted(candidates, reverse=True)[:32]}
        self.cache = {key: value for key, value in self.cache.items()
                      if key[0] != provider or key in retained}
        working = [s for s in sessions if s.state == 'working' and now - s.updated <= ACTIVE_GRACE]
        uncertain = [s for s in sessions if s.state == 'unknown'
                     or (s.state == 'working' and now - s.updated > ACTIVE_GRACE)]
        pool = working or uncertain or sessions
        latest = max(pool, key=lambda s: s.updated) if pool else None
        status = 'WORKING' if working else ('UNKNOWN' if uncertain else ('IDLE' if root.is_dir() else 'OFFLINE'))
        detail = latest.activity if latest else ('No recent activity' if root.is_dir() else 'Source unavailable')
        if uncertain and not working:
            detail = 'No recent lifecycle signal'
        return {'status': status, 'count': f'{len(working)} active',
                'elapsed': elapsed_text(now - latest.started) if working and latest.started else '',
                'project': latest.project if latest else '--', 'detail': display_text(detail),
                'active': len(working), 'tone': 1 if working else (2 if uncertain else 0)}
