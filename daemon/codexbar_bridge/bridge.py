#!/usr/bin/env python3
"""Expose sanitized quota windows and local agent activity to a SmallTV on the LAN."""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request
from zoneinfo import ZoneInfo
from activity import Activity
from remote_activity import RemoteActivity, dashboard_pages, unavailable, PROVIDERS

ROOT = Path(__file__).resolve().parent
TZ = ZoneInfo('America/Toronto')


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except ValueError:
        return None


def select_window(usage, minutes):
    # A missing window is not zero usage, and a different window is not a 5h/7d quota.
    for name in ('primary', 'secondary', 'tertiary'):
        window = usage.get(name)
        if isinstance(window, dict) and window.get('windowMinutes') == minutes:
            percent = window.get('usedPercent')
            if isinstance(percent, (int, float)) and not isinstance(percent, bool) and math.isfinite(percent):
                return {'used': max(0, min(100, percent)), 'reset': parse_time(window.get('resetsAt'))}
    return None


def reset_text(reset, now):
    if reset is None:
        return '--'
    minutes = max(0, math.ceil((reset - now) / 60))
    days, remainder = divmod(minutes, 1440)
    hours, mins = divmod(remainder, 60)
    if days:
        return f'{days}d {hours}h'
    if hours:
        return f'{hours}h {mins}m'
    return f'{mins}m'


def project_window(window, now):
    if window is None:
        return 'n/a', 0, '--'
    return f"{window['used']:g}%", window['used'], reset_text(window['reset'], now)


def project(snapshot, now, max_age):
    fetched = snapshot.get('fetched', 0)
    stale = not fetched or now - fetched > max_age
    session = None if stale else snapshot.get('session')
    weekly = None if stale else snapshot.get('weekly')
    session_text, session_bar, session_reset = project_window(session, now)
    weekly_text, weekly_bar, weekly_reset = project_window(weekly, now)
    stamp = dt.datetime.fromtimestamp(fetched, TZ).strftime('%H:%M') if fetched else '--:--'
    status = 'WAIT' if not fetched else ('STALE' if stale else ('RETRY' if snapshot.get('error') else 'UPD'))
    return {'sessionText': session_text, 'sessionBar': session_bar, 'sessionReset': session_reset,
            'weeklyText': weekly_text, 'weeklyBar': weekly_bar, 'weeklyReset': weekly_reset,
            'state': f'{status} {stamp}'}


def native_payload(snapshot, now, max_age):
    if not snapshot.get('fetched') or now - snapshot['fetched'] > max_age:
        return None
    short, week = snapshot.get('session'), snapshot.get('weekly')
    if short is None or week is None:
        return None
    return {'s': short['used'], 'sr': max(0, math.ceil((short['reset'] - now) / 60)) if short['reset'] else 0,
            'w': week['used'], 'wr': max(0, math.ceil((week['reset'] - now) / 60)) if week['reset'] else 0,
            'st': 'normal', 'ok': True}


class Bridge:
    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.snapshots = {provider: {} for provider in config['providers']}
        self.requests = {provider: 0 for provider in config['providers']}
        self.activity = Activity(config.get('activity_roots', {}))
        self.agent_snapshots = {}
        self.requests.update({f'agent-{provider}': 0 for provider in self.activity.roots})
        self.remote_activity = RemoteActivity(config['remote_activity']) if config.get('remote_activity') else None
        self.remote_agents = {p: unavailable('Connecting to VPS') for p in PROVIDERS} if self.remote_activity else None
        self.remote_sampled = 0
        self.requests.update({'agent-top': 0, 'agent-bottom': 0})
        self.last_device_request = {}
        self.native_pushes = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def collect(self, provider, source):
        command = [self.config['cli'], 'usage', '--provider', provider, '--source', source,
                   '--format', 'json', '--no-credits']
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            if result.returncode:
                raise RuntimeError(f'CodexBar exited {result.returncode}')
            entries = json.loads(result.stdout)
            item = next(entry for entry in entries if entry.get('provider') == provider)
            usage = item.get('usage')
            if not isinstance(usage, dict):
                raise RuntimeError('CodexBar returned no usage object')
            snapshot = {'fetched': parse_time(usage.get('updatedAt')) or time.time(),
                        'session': select_window(usage, 300), 'weekly': select_window(usage, 10080),
                        'source': item.get('source'), 'error': False}
            if snapshot['session'] is None and snapshot['weekly'] is None:
                raise RuntimeError('CodexBar returned no supported quota windows')
            with self.lock:
                self.snapshots[provider] = snapshot
            print(f'{provider}: refreshed quota windows via {source}', flush=True)
        except (OSError, ValueError, KeyError, StopIteration, RuntimeError, subprocess.TimeoutExpired) as error:
            # CodexBar stdout can include account identity; keep it out of logs and HTTP responses.
            with self.lock:
                self.snapshots[provider]['error'] = True
            message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
            print(f'{provider}: refresh failed: {message}', flush=True)
        self.save_status()

    def poll(self):
        while not self.stop.is_set():
            for provider, source in self.config['providers'].items():
                if self.stop.is_set():
                    return
                self.collect(provider, source)
            self.stop.wait(self.config['refresh_seconds'])

    def push_native(self):
        # The stock Clawdmeter title says CLAUDE, so only Claude goes to this endpoint.
        while not self.stop.is_set():
            with self.lock:
                payload = native_payload(dict(self.snapshots.get('claude', {})), time.time(), self.config['max_age_seconds'])
            if payload is not None:
                try:
                    request = urllib.request.Request(
                        f"http://{self.config['device_ip']}/api/usage", data=json.dumps(payload).encode(),
                        headers={'Content-Type': 'application/json'})
                    with self.opener.open(request, timeout=3) as response:
                        if not json.load(response).get('ok'):
                            raise RuntimeError('Device rejected usage')
                    with self.lock:
                        self.native_pushes += 1
                    self.save_status()
                except (OSError, ValueError, RuntimeError):
                    print('SmallTV: native usage push unavailable; retrying next cycle', flush=True)
            self.stop.wait(30)

    def poll_activity(self):
        while not self.stop.is_set():
            for provider in self.activity.roots:
                try:
                    payload = self.activity.snapshot(provider)
                    payload['stamp'] = dt.datetime.now(TZ).strftime('UPD %H:%M')
                    with self.lock:
                        self.agent_snapshots[provider] = payload
                except (OSError, ValueError, TypeError):
                    with self.lock:
                        self.agent_snapshots[provider] = {'status': 'OFFLINE', 'count': '--',
                            'elapsed': '', 'project': '--', 'detail': 'Activity reader unavailable',
                            'active': 0, 'tone': 2, 'stamp': dt.datetime.now(TZ).strftime('UPD %H:%M')}
                    print(f'{provider}: activity adapter unavailable; retrying', flush=True)
            self.save_status()
            self.stop.wait(self.config.get('activity_refresh_seconds', 5))

    def poll_remote_activity(self):
        if not self.remote_activity:
            return
        while not self.stop.is_set():
            try:
                sampled, agents = self.remote_activity.snapshot()
                with self.lock:
                    self.remote_agents, self.remote_sampled = agents, sampled
            except (OSError, ValueError, TypeError, RuntimeError, subprocess.TimeoutExpired) as error:
                with self.lock:
                    self.remote_agents = {p: unavailable() for p in PROVIDERS}
                    self.remote_sampled = 0
                print(f'VPS activity unavailable: {type(error).__name__}: {error}', flush=True)
            self.save_status()
            self.stop.wait(self.config['remote_activity'].get('refresh_seconds', 15))

    def dashboard_payload(self, position, from_device=False):
        with self.lock:
            now = time.time()
            remote = self.remote_agents
            if remote is not None and now - self.remote_sampled > self.config['remote_activity'].get('max_age_seconds', 45):
                remote = {p: unavailable() for p in PROVIDERS}
            value = dashboard_pages(self.agent_snapshots, remote, now,
                                    self.config.get('activity_page_seconds', 20))[position]
            value['stamp'] = value.pop('host') + dt.datetime.fromtimestamp(now, TZ).strftime(' %H:%M')
            key = f'agent-{position}'
            self.requests[key] += 1
            if from_device:
                self.last_device_request[key] = now
        self.save_status()
        return value

    def agent_payload(self, provider, from_device=False):
        with self.lock:
            key = f'agent-{provider}'
            self.requests[key] += 1
            if from_device:
                self.last_device_request[key] = time.time()
            value = dict(self.agent_snapshots.get(provider, {'status': 'STARTING', 'count': '--',
                         'elapsed': '', 'project': '--', 'detail': 'Reading lifecycle events',
                         'active': 0, 'tone': 2, 'stamp': '--:--'}))
        self.save_status()
        return value

    def payload(self, provider, from_device=False):
        with self.lock:
            self.requests[provider] += 1
            if from_device:
                self.last_device_request[provider] = time.time()
            value = project(self.snapshots[provider], time.time(), self.config['max_age_seconds'])
        self.save_status()
        return value

    def save_status(self):
        with self.lock:
            state = {'updated_at': dt.datetime.now(TZ).isoformat(),
                     'providers': {p: project(s, time.time(), self.config['max_age_seconds'])
                                   for p, s in self.snapshots.items()},
                     'http_requests': dict(self.requests), 'device_requests': dict(self.last_device_request),
                     'native_claude_pushes': self.native_pushes, 'agents': dict(self.agent_snapshots),
                     'remote_agents': self.remote_agents, 'remote_sampled': self.remote_sampled}
            # Use a unique temporary name because the fetch and HTTP threads both save status.
            path = ROOT / f'.status-{threading.get_ident()}.tmp'
            path.write_text(json.dumps(state, indent=2))
            os.chmod(path, 0o600)
            path.replace(ROOT / 'status.json')


def run(config):
    bridge = Bridge(config)
    allowed = {config['device_ip'], config['bind_ip'], '127.0.0.1'}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            provider = self.path.removesuffix('.json').removeprefix('/')
            if self.client_address[0] not in allowed:
                self.send_error(403)
                return
            if self.path != f'/{provider}.json' or provider not in bridge.requests:
                self.send_error(404)
                return
            from_device = self.client_address[0] == config['device_ip']
            if provider in ('agent-top', 'agent-bottom'):
                payload = bridge.dashboard_payload(provider[6:], from_device)
            elif provider.startswith('agent-'):
                payload = bridge.agent_payload(provider[6:], from_device)
            else:
                payload = bridge.payload(provider, from_device)
            body = json.dumps(payload, separators=(',', ':')).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer((config['bind_ip'], config['port']), Handler)
    server.timeout = 1
    for operation in (bridge.poll, bridge.push_native, bridge.poll_activity, bridge.poll_remote_activity):
        threading.Thread(target=operation, daemon=True).start()

    def stop(*_):
        bridge.stop.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"Serving SmallTV-only quota feeds on {config['bind_ip']}:{config['port']}", flush=True)
    try:
        while not bridge.stop.is_set():
            server.handle_request()
    finally:
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    args = parser.parse_args()
    run(json.loads(args.config.read_text()))
