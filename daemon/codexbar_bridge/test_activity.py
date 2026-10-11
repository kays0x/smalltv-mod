import json
from pathlib import Path
import tempfile
import unittest

from activity import Activity, Session, Transcript, timestamp

T0 = '2026-10-11T06:00:00Z'
T1 = '2026-10-11T06:01:00Z'


def codex(event, when=T0, turn='one'):
    return {'type': 'event_msg', 'timestamp': when, 'payload': {'type': event, 'turn_id': turn}}


class ActivityTests(unittest.TestCase):
    def test_valid_json_with_wrong_shape_is_ignored(self):
        s = Session('codex')
        for value in ([], None, 42, 'text'):
            s.apply(value)
        self.assertEqual(s.state, 'unknown')

    def test_codex_completion_and_interrupt_end_turn(self):
        for ending in ('task_complete', 'turn_aborted', 'task_failed'):
            s = Session('codex')
            s.apply(codex('task_started'))
            self.assertEqual(s.state, 'working')
            s.apply(codex(ending, T1))
            self.assertEqual(s.state, 'idle')

    def test_late_completion_cannot_end_a_newer_turn(self):
        s = Session('codex')
        s.apply(codex('task_started', turn='new'))
        s.apply(codex('task_complete', T1, turn='old'))
        self.assertEqual(s.state, 'working')

    def test_claude_metadata_write_does_not_create_work(self):
        s = Session('claude')
        s.apply({'type': 'cost-state', 'timestamp': T0, 'token': 'secret'})
        self.assertEqual(s.updated, 0)

    def test_claude_tool_results_do_not_restart_elapsed_time(self):
        s = Session('claude')
        s.apply({'type': 'user', 'timestamp': T0, 'message': {'content': 'private prompt'}})
        started = s.started
        s.apply({'type': 'user', 'timestamp': T1, 'message': {'content': [{'type': 'tool_result'}]}})
        self.assertEqual(s.started, started)
        s.apply({'type': 'assistant', 'timestamp': T1, 'message': {'stop_reason': 'end_turn'}})
        self.assertEqual(s.state, 'idle')

    def test_claude_meta_turn_duration_is_still_a_completion_signal(self):
        s = Session('claude')
        s.apply({'type': 'user', 'timestamp': T0, 'message': {'content': 'task'}})
        s.apply({'type': 'system', 'subtype': 'turn_duration', 'isMeta': True, 'timestamp': T1})
        self.assertEqual(s.state, 'idle')

    def test_missing_source_is_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            result = Activity({'claude': Path(folder) / 'missing'}).snapshot('claude')
            self.assertEqual(result['status'], 'OFFLINE')

    def test_partial_record_is_processed_only_after_newline(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'session.jsonl'
            raw = json.dumps(codex('task_started')).encode()
            p.write_bytes(raw[:30])
            reader = Transcript(p, 'codex')
            reader.update()
            self.assertEqual(reader.session.state, 'unknown')
            with p.open('ab') as file:
                file.write(raw[30:] + b'\n')
            reader.update()
            self.assertEqual(reader.session.state, 'working')

    def test_old_unfinished_turn_is_unknown_not_idle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            day = root / '2026/10/11'
            day.mkdir(parents=True)
            (day / 'session.jsonl').write_text(json.dumps(codex('task_started')) + '\n')
            result = Activity({'codex': root}).snapshot('codex', timestamp(T0) + 1000)
            self.assertEqual(result['status'], 'UNKNOWN')
            self.assertEqual(result['active'], 0)

    def test_display_payload_excludes_prompt_and_tool_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / 'project'
            project.mkdir()
            row = {'type': 'user', 'timestamp': T0, 'cwd': '/some/project',
                   'message': {'content': 'SECRET PROMPT'}, 'tool_input': {'token': 'SECRET TOKEN'}}
            (project / 'session.jsonl').write_text(json.dumps(row) + '\n')
            result = Activity({'claude': root}).snapshot('claude', timestamp(T0) + 30)
            self.assertEqual(result['status'], 'WORKING')
            self.assertNotIn('SECRET', json.dumps(result))
            self.assertEqual(result['project'], 'project')


if __name__ == '__main__':
    unittest.main()
