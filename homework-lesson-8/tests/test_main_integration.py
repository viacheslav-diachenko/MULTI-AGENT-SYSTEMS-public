"""Integration-style tests for main.py interrupt handling."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import main


class MainInterruptIntegrationTests(TestCase):
    @patch('main._resume_supervisor')
    @patch(
        'builtins.input',
        side_effect=['edit', 'updated.md', '## Updated report', 'END'],
    )
    def test_handle_interrupt_direct_edit_updates_tool_args(self, _mock_input, mock_resume_supervisor):
        interrupt = SimpleNamespace(value={
            'action_requests': [
                {
                    'action': 'save_report',
                    'args': {'filename': 'original.md', 'content': '# Original'},
                }
            ]
        })

        main.handle_interrupt(interrupt)

        resume_payload = mock_resume_supervisor.call_args.args[0]
        decision = resume_payload['decisions'][0]
        self.assertEqual(decision['type'], 'edit')
        self.assertEqual(decision['editedAction']['name'], 'save_report')
        self.assertEqual(decision['editedAction']['args']['filename'], 'updated.md')
        self.assertEqual(decision['editedAction']['args']['content'], '## Updated report')

    @patch('main._resume_supervisor')
    @patch('builtins.input', side_effect=['revise', 'Please add citations'])
    def test_handle_interrupt_revise_sends_feedback_back_to_supervisor(self, _mock_input, mock_resume_supervisor):
        interrupt = SimpleNamespace(value={
            'action_requests': [
                {
                    'action': 'save_report',
                    'args': {'filename': 'original.md', 'content': '# Original'},
                }
            ]
        })

        main.handle_interrupt(interrupt)

        resume_payload = mock_resume_supervisor.call_args.args[0]
        decision = resume_payload['decisions'][0]
        self.assertEqual(decision['type'], 'reject')
        self.assertIn('Please add citations', decision['message'])
