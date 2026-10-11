import json
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess, TimeoutExpired
from remote_activity import RemoteActivity, dashboard_pages, sanitize, unavailable, PROVIDERS
from bridge import Bridge


def sample(now=100):
    return {'sampled': now, 'agents': {p: dict(unavailable(), status='IDLE',
             prompt='SECRET', token='SECRET', extra={'raw': 'SECRET'}) for p in PROVIDERS}}


class RemoteTests(unittest.TestCase):
    def test_remote_fields_are_whitelisted_and_control_characters_removed(self):
        document = sample()
        document['agents']['claude']['project'] = 'project\nname'
        result = sanitize(document, 100, 45)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(result['claude']['project'], 'projectname')

    def test_stale_or_future_or_nonfinite_snapshots_are_rejected(self):
        for when in (0, 200, float('nan'), True):
            with self.assertRaises(ValueError):
                sanitize(sample(when), 100, 45)

    def test_invalid_count_or_state_is_rejected(self):
        for key, value in (('active', 33), ('active', True), ('status', 'SUCCESS')):
            document = sample()
            document['agents']['pi'][key] = value
            with self.assertRaises(ValueError):
                sanitize(document, 100, 45)

    def test_working_state_requires_a_positive_count(self):
        document = sample()
        document['agents']['codex']['status'] = 'WORKING'
        with self.assertRaises(ValueError):
            sanitize(document, 100, 45)
        document['agents']['codex']['active'] = 2
        self.assertEqual(sanitize(document, 100, 45)['codex']['count'], '2 active')

    def test_question_wait_is_sanitized_and_can_coexist_with_work(self):
        document = sample()
        document['agents']['claude'].update(status='WAITING', waiting=1, active=1,
                                           detail='Answer needed', count='SECRET')
        result = sanitize(document, 100, 45)['claude']
        self.assertEqual((result['status'], result['count'], result['tone']), ('WAITING', '1 waiting', 2))
        self.assertEqual((result['active'], result['waiting']), (1, 1))
        self.assertNotIn('SECRET', json.dumps(result))

    def test_waiting_state_and_count_must_agree(self):
        for status, waiting in [('WAITING', 0), ('IDLE', 1), ('WAITING', True), ('WAITING', 33)]:
            document = sample()
            document['agents']['claude'].update(status=status, waiting=waiting)
            with self.assertRaises(ValueError):
                sanitize(document, 100, 45)

    def test_all_three_pages_include_host_and_provider_names(self):
        idle = unavailable()
        local = {'claude': idle, 'codex': idle}
        remote = {p: idle for p in PROVIDERS}
        expected = [('MAC', 'CLAUDE', 'CODEX'), ('VPS', 'CLAUDE', 'CODEX'),
                    ('VPS', 'CLAUDE', 'PI')]
        for now, (host, top, bottom) in zip((0, 20, 40), expected):
            page = dashboard_pages(local, remote, now)
            self.assertEqual((page['top']['host'], page['top']['title'], page['bottom']['title']),
                             (host, top, bottom))
        self.assertEqual(dashboard_pages(local, None, 40)['top']['host'], 'MAC')
        self.assertNotIn('title', idle)

    def test_ssh_failure_and_timeout_cannot_be_valid_data(self):
        reader = RemoteActivity({'ssh_host': 'example-host', 'exporter': '/path/export_activity.py'})
        with patch('remote_activity.subprocess.run', return_value=CompletedProcess([], 255, '', 'failure')):
            with self.assertRaises(RuntimeError):
                reader.snapshot()
        with patch('remote_activity.subprocess.run', side_effect=TimeoutExpired('ssh', 12)):
            with self.assertRaises(TimeoutExpired):
                reader.snapshot()

    def test_ssh_uses_existing_auth_and_quotes_remote_path(self):
        reader = RemoteActivity({'ssh_host': 'example-host', 'exporter': '/path with spaces/export.py'})
        with patch('remote_activity.subprocess.run', return_value=CompletedProcess([], 0, json.dumps(sample()), '')) as run:
            with patch('remote_activity.time.time', return_value=100):
                sampled, agents = reader.snapshot()
            self.assertEqual(sampled, 100)
            self.assertEqual(set(agents), set(PROVIDERS))
            command = run.call_args[0][0]
            self.assertIn('BatchMode=yes', command)
            self.assertEqual(command[-1], "/usr/bin/python3 '/path with spaces/export.py'")

    def test_bridge_expires_remote_data_and_records_actual_device_poll(self):
        bridge = Bridge({'providers': {}, 'remote_activity': {'max_age_seconds': 45},
                         'activity_page_seconds': 20})
        bridge.remote_agents = sanitize(sample(0), 0, 45)
        bridge.remote_sampled = 0
        with patch('bridge.time.time', return_value=100), patch.object(bridge, 'save_status'):
            payload = bridge.dashboard_payload('bottom', from_device=True)
        self.assertEqual(payload['title'], 'PI')
        self.assertEqual(payload['status'], 'OFFLINE')
        self.assertEqual(bridge.last_device_request['agent-bottom'], 100)
        self.assertEqual(bridge.requests['agent-bottom'], 1)


if __name__ == '__main__':
    unittest.main()
