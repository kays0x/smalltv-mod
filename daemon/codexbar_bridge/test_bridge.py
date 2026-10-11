import datetime as dt
import json
import unittest

from bridge import native_payload, project, reset_text, select_window


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


if __name__ == '__main__':
    unittest.main()
