"""Collect display fields over existing SSH authentication, with bounded freshness."""
import json
import math
import shlex
import subprocess
import time
from activity import display_text

PROVIDERS = ('claude', 'codex', 'pi')
STATUSES = {'WORKING', 'WAITING', 'IDLE', 'UNKNOWN', 'OFFLINE'}


def unavailable(detail='VPS unreachable'):
    return {'status': 'OFFLINE', 'count': '--', 'elapsed': '', 'project': '--',
            'detail': detail, 'active': 0, 'tone': 2}


def sanitize(document, now, max_age):
    sampled = document.get('sampled')
    if (not isinstance(sampled, (int, float)) or isinstance(sampled, bool)
            or not math.isfinite(sampled) or not -10 <= now - sampled <= max_age):
        raise ValueError('Remote snapshot is stale or has an invalid timestamp')
    agents = document.get('agents')
    if not isinstance(agents, dict):
        raise ValueError('Remote snapshot has no agent map')
    result = {}
    for provider in PROVIDERS:
        row = agents.get(provider)
        if not isinstance(row, dict) or row.get('status') not in STATUSES:
            raise ValueError('Remote snapshot has an invalid state')
        active = row.get('active')
        if not isinstance(active, int) or isinstance(active, bool) or not 0 <= active <= 32:
            raise ValueError('Remote snapshot has an invalid count')
        waiting = row.get('waiting', 0)
        if (not isinstance(waiting, int) or isinstance(waiting, bool) or not 0 <= waiting <= 32
                or active + waiting > 32):
            raise ValueError('Remote snapshot has an invalid waiting count')
        if (row['status'] == 'WAITING') != (waiting > 0):
            raise ValueError('Remote state and waiting count disagree')
        if row['status'] != 'WAITING' and (row['status'] == 'WORKING') != (active > 0):
            raise ValueError('Remote state and active count disagree')
        result[provider] = {key: display_text(row.get(key, '')) for key in ('elapsed', 'project', 'detail')}
        result[provider].update(status=row['status'], active=active, waiting=waiting,
                                count=f'{waiting} waiting' if waiting else f'{active} active',
                                tone=2 if waiting or row['status'] in ('UNKNOWN', 'OFFLINE') else (1 if active else 0))
    return result


class RemoteActivity:
    def __init__(self, config):
        self.config = config

    def snapshot(self):
        # SSH handles authentication; there is no new listener or copied credential.
        remote_command = '/usr/bin/python3 ' + shlex.quote(self.config['exporter'])
        command = ['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
                   self.config['ssh_host'], remote_command]
        result = subprocess.run(command, capture_output=True, text=True, timeout=12)
        if result.returncode:
            raise RuntimeError(f'SSH exporter exited {result.returncode}')
        if len(result.stdout) > 32768:
            raise ValueError('Remote snapshot exceeds display payload limit')
        document = json.loads(result.stdout)
        if not isinstance(document, dict):
            raise ValueError('Remote snapshot is not an object')
        agents = sanitize(document, time.time(), self.config.get('max_age_seconds', 45))
        return document['sampled'], agents


def dashboard_pages(local, remote, now, page_seconds=20):
    pages = [('MAC', [('CLAUDE', local.get('claude')), ('CODEX', local.get('codex'))])]
    if remote is not None:
        pages += [('VPS', [('CLAUDE', remote.get('claude')), ('CODEX', remote.get('codex'))]),
                  ('VPS', [('CLAUDE', remote.get('claude')), ('PI', remote.get('pi'))])]
    host, rows = pages[int(now // page_seconds) % len(pages)]
    result = {}
    for position, (title, row) in zip(('top', 'bottom'), rows):
        value = dict(row or unavailable('Reading activity'))
        value['title'] = title
        value['host'] = host
        result[position] = value
    return result
