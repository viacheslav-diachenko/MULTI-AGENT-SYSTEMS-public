"""Integration-style tests for tool wiring and filter behavior."""

from unittest import TestCase
from unittest.mock import patch

from langchain_core.documents import Document

import tools


class FakeRetriever:
    def __init__(self, docs):
        self.docs = docs
        self.calls = []

    def search(self, query, *, source_filter=None, page_filter=None, rerank_top_n=None):
        self.calls.append({
            'query': query,
            'source_filter': source_filter,
            'page_filter': page_filter,
            'rerank_top_n': rerank_top_n,
        })
        return self.docs


class KnowledgeSearchIntegrationTests(TestCase):
    @patch('tools._get_or_init_retriever')
    def test_knowledge_search_passes_filters_into_retriever(self, mock_get_retriever):
        fake_retriever = FakeRetriever([
            Document(
                page_content='Sentence-window retrieval summary.',
                metadata={'source': '/tmp/langchain.pdf', 'page': 3, 'rerank_score': 0.91},
            )
        ])
        mock_get_retriever.return_value = fake_retriever

        result = tools.knowledge_search.invoke({
            'query': 'sentence-window retrieval',
            'source_filter': 'langchain',
            'page_filter': 3,
        })

        self.assertEqual(len(fake_retriever.calls), 1)
        self.assertEqual(fake_retriever.calls[0]['source_filter'], 'langchain')
        self.assertEqual(fake_retriever.calls[0]['page_filter'], 3)
        self.assertEqual(
            fake_retriever.calls[0]['rerank_top_n'],
            tools.settings.filtered_rerank_top_n,
        )
        self.assertIn('langchain.pdf', result)
        self.assertIn('Page 3', result)

    @patch('tools._get_or_init_retriever')
    def test_knowledge_search_reports_no_results_after_filtered_search(self, mock_get_retriever):
        fake_retriever = FakeRetriever([])
        mock_get_retriever.return_value = fake_retriever

        result = tools.knowledge_search.invoke({
            'query': 'rag',
            'source_filter': 'missing',
        })

        self.assertIn('No results after filtering', result)
