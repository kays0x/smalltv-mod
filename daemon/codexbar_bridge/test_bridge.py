import datetime as dt
import json
import unittest
from unittest.mock import patch

from bridge import Bridge, agents_document, native_payload, project, reset_text, select_window
from remote_activity import unavailable, PROVIDERS


class QuotaMappingTests(unittest.TestCase):
    def test_missing_codex_session_stays_unavailable(self):
        snapshot = {'fetched': 1000, 'session': None, 'weekly': {'used': 3, 'reset': 86500}}
        result = project(snapshot, 1000, 300)
        self.assertEqual(result['sessionText'], 'n/a')
        self.assertEqual(result['weeklyText'], '3%')
        self.assertIsNone(native_payload(snapshot, 1000, 300))

    def test_actual_zero_usage_is_distinct_from_missing(self):
        window = select_window({'primary': {'windowMinutes': 300, 'usedPercent': 0}}, 300)
        result = project({'fetched': 1000, 'session': window}, 1000, 300)
        self.assertEqual(result['sessionText'], '0%')
        self.assertEqual(result['sessionReset'], '--')

    def test_unexpected_window_is_not_mislabeled_as_five_hours(self):
        self.assertIsNone(select_window({'primary': {'windowMinutes': 60, 'usedPercent': 80}}, 300))

    def test_stale_data_does_not_look_like_current_quota(self):
        result = project({'fetched': 1000, 'session': {'used': 80, 'reset': None}}, 1400, 300)
        self.assertEqual(result['sessionText'], 'n/a')
        self.assertTrue(result['state'].startswith('STALE'))

    def test_mapping_uses_used_percentage_without_inverting_it(self):
        result = project({'fetched': 1000, 'session': {'used': 73, 'reset': 4600}}, 1000, 300)
        self.assertEqual(result['sessionText'], '73%')
        self.assertEqual(result['sessionBar'], 73)
        self.assertEqual(result['sessionReset'], '1h 0m')

    def test_identity_and_tokens_do_not_enter_display_payload(self):
        snapshot = {'fetched': 1000, 'accountEmail': 'private@example.test', 'token': 'secret'}
        serialized = json.dumps(project(snapshot, 1000, 300))
        self.assertNotIn('private', serialized)
        self.assertNotIn('secret', serialized)

    def test_nonfinite_or_boolean_percentage_is_rejected(self):
        for percent in (float('nan'), float('inf'), True):
            self.assertIsNone(select_window({'primary': {'windowMinutes': 300, 'usedPercent': percent}}, 300))

    def test_reset_countdown_cannot_go_negative(self):
        self.assertEqual(reset_text(900, 1000), '0m')


class NativeAgentsTests(unittest.TestCase):
    def setUp(self):
        self.local = {p: dict(unavailable(), status='IDLE') for p in ('claude', 'codex')}
        self.remote = {p: dict(unavailable(), status='IDLE') for p in PROVIDERS}
        self.quotas = {
            'claude': {'fetched': 1000, 'session': {'used': 25, 'reset': 4000},
                       'weekly': {'used': 5, 'reset': 9000}},
            'codex': {'fetched': 1000, 'session': None, 'weekly': {'used': 2, 'reset': 9000}}}

    def document(self, now=1000, remote=True):
        return agents_document(self.local, self.remote if remote else None, self.quotas, now, 360)

    def test_all_pages_are_stable_and_have_controlled_provider_names(self):
        first, later = self.document(), self.document(1040)
        self.assertEqual(first['pages'], later['pages'])
        self.assertEqual((first['sampled'], later['sampled']), (1000, 1040))
        self.assertEqual([p['id'] for p in first['pages']], ['mac', 'vps-codex', 'vps-pi', 'usage'])
        self.assertEqual([[r['title'] for r in p['rows']] for p in first['pages']],
                         [['CLAUDE', 'CODEX'], ['CLAUDE', 'CODEX'], ['CLAUDE', 'PI'],
                          ['CLAUDE', 'CLAUDE', 'CODEX']])
        self.assertEqual([r['label'] for r in first['pages'][-1]['rows']], ['5h', '7d', '7d'])

    def test_without_remote_keeps_mac_and_usage_pages(self):
        self.assertEqual([p['id'] for p in self.document(remote=False)['pages']], ['mac', 'usage'])

    def test_waiting_row_retains_state_and_rebuilds_counts(self):
        self.remote['claude'].update(status='WAITING', waiting=1, active=2,
                                     detail='Answer needed', count='secret question', tone=0)
        row = self.document()['pages'][1]['rows'][0]
        self.assertEqual((row['status'], row['count'], row['tone']), ('WAITING', '1 waiting', 2))
        self.assertEqual((row['active'], row['waiting'], row['detail']), (2, 1, 'Answer needed'))

    def test_public_rows_whitelist_fields_and_sanitize_strings(self):
        self.local['claude'].update(title='SECRET', prompt='SECRET', credentials='SECRET',
                                    project='name\nwith\x1bcontrol', elapsed={'token': 'SECRET'})
        self.remote['pi']['toolArguments'] = {'token': 'SECRET'}
        self.local['openclaw'] = {'secret': 'SECRET'}
        self.remote['openclaw'] = {'secret': 'SECRET'}
        self.quotas['claude'].update(accountEmail='SECRET', token='SECRET')
        result = self.document()
        serialized = json.dumps(result)
        self.assertNotIn('SECRET', serialized)
        self.assertNotIn('openclaw', serialized)
        self.assertNotIn('Reset', serialized)
        self.assertNotIn('USED', serialized)
        self.assertNotIn('sessionReset', serialized)
        row = result['pages'][0]['rows'][0]
        self.assertEqual(row['project'], 'namewithcontrol')
        self.assertEqual(row['elapsed'], '')
        self.assertEqual(set(row), {'title', 'status', 'count', 'elapsed', 'project', 'detail',
                                    'active', 'waiting', 'tone'})
        self.assertEqual(set(result['pages'][-1]['rows'][0]), {'title', 'label', 'text', 'bar'})

    def test_missing_stale_and_real_zero_quota_remain_distinct(self):
        self.quotas['claude']['session'] = {'used': 0, 'reset': None}
        self.quotas['claude']['weekly'] = None
        rows = self.document()['pages'][-1]['rows']
        self.assertEqual([(r['text'], r['bar']) for r in rows], [('0%', 0), ('n/a', 0), ('2%', 2)])
        self.assertEqual([r['text'] for r in self.document(1400)['pages'][-1]['rows']], ['n/a'] * 3)
        self.quotas = {}
        self.assertEqual([r['text'] for r in self.document()['pages'][-1]['rows']], ['n/a'] * 3)

    def test_invalid_quota_and_agent_values_are_not_forwarded(self):
        for value in (True, float('nan'), float('inf'), 'SECRET', {'token': 'SECRET'}):
            self.quotas['claude']['session'] = {'used': value}
            self.assertEqual(self.document()['pages'][-1]['rows'][0]['text'], 'n/a')
        for field, value in (('active', True), ('waiting', 33), ('status', ['SECRET']),
                             ('status', 'WORKING')):
            self.local['claude'] = dict(unavailable(), status='IDLE')
            self.local['claude'][field] = value
            row = self.document()['pages'][0]['rows'][0]
            self.assertEqual(row['status'], 'OFFLINE')
            self.assertNotIn('SECRET', json.dumps(row))

    def test_http_snapshot_expires_remote_and_counts_actual_device_poll(self):
        bridge = Bridge({'providers': {}, 'max_age_seconds': 360,
                         'remote_activity': {'max_age_seconds': 45}})
        bridge.remote_agents = self.remote
        bridge.remote_agents['claude'].update(status='WORKING', active=1)
        bridge.remote_sampled = 1000
        with patch('bridge.time.time', return_value=1045), patch.object(bridge, 'save_status'):
            self.assertEqual(bridge.agents_payload()['pages'][1]['rows'][0]['status'], 'WORKING')
        with patch('bridge.time.time', return_value=1046), patch.object(bridge, 'save_status'):
            payload = bridge.agents_payload(from_device=True)
        self.assertEqual(payload['sampled'], 1046)
        for page in payload['pages'][1:3]:
            self.assertEqual([r['status'] for r in page['rows']], ['OFFLINE', 'OFFLINE'])
        self.assertEqual(bridge.last_device_request['agents'], 1046)
        self.assertEqual(bridge.requests['agents'], 2)


if __name__ == '__main__':
    unittest.main()
