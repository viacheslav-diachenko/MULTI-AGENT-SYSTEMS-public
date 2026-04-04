"""Integration-style tests for supervisor tool wrappers."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

import supervisor


class SupervisorIntegrationTests(TestCase):
    def setUp(self):
        supervisor.reset_revision_counter('thread-a')
        supervisor.reset_revision_counter('thread-b')
        supervisor.reset_revision_counter('thread-limit')

    @patch('supervisor.build_research_agent')
    def test_research_uses_thread_id_from_runtime_config(self, mock_build_research_agent):
        agent = MagicMock()
        agent.invoke.return_value = {'messages': [AIMessage(content='Findings')]} 
        mock_build_research_agent.return_value = agent

        runtime_a = SimpleNamespace(config={'configurable': {'thread_id': 'thread-a'}})
        runtime_b = SimpleNamespace(config={'configurable': {'thread_id': 'thread-b'}})

        self.assertEqual(supervisor.research.func('query A', runtime=runtime_a), 'Findings')
        self.assertEqual(supervisor.research.func('query B', runtime=runtime_b), 'Findings')
        self.assertEqual(supervisor._get_revision_count('thread-a'), 1)
        self.assertEqual(supervisor._get_revision_count('thread-b'), 1)

    @patch('supervisor.build_research_agent')
    def test_research_enforces_revision_limit_per_thread(self, mock_build_research_agent):
        agent = MagicMock()
        agent.invoke.return_value = {'messages': [AIMessage(content='Findings')]} 
        mock_build_research_agent.return_value = agent

        runtime = SimpleNamespace(config={'configurable': {'thread_id': 'thread-limit'}})

        supervisor.research.func('initial', runtime=runtime)
        supervisor.research.func('revise 1', runtime=runtime)
        supervisor.research.func('revise 2', runtime=runtime)
        limit_message = supervisor.research.func('revise 3', runtime=runtime)

        self.assertIn('REVISION LIMIT REACHED', limit_message)
        self.assertEqual(agent.invoke.call_count, 3)
