"""Tests for Reciprocal Rank Fusion (RRF) merge logic.

Tests the pure function reciprocal_rank_fusion without network dependencies.
"""

import pytest
from langchain_core.documents import Document

from retriever import reciprocal_rank_fusion


def _doc(text: str, **metadata) -> Document:
    """Helper to create a Document with given text and metadata."""
    return Document(page_content=text, metadata=metadata)


class TestReciprocalRankFusion:
    """Tests for reciprocal_rank_fusion function."""

    # --- Basic behavior ---

    def test_single_list(self):
        docs = [_doc("first"), _doc("second"), _doc("third")]
        result = reciprocal_rank_fusion([docs])

        assert len(result) == 3
        assert result[0].page_content == "first"
        assert result[1].page_content == "second"
        assert result[2].page_content == "third"

    def test_two_identical_lists_preserve_order(self):
        list1 = [_doc("A"), _doc("B"), _doc("C")]
        list2 = [_doc("A"), _doc("B"), _doc("C")]
        result = reciprocal_rank_fusion([list1, list2])

        assert len(result) == 3
        # Same order — A has highest score (found first in both lists)
        assert result[0].page_content == "A"

    def test_document_in_both_lists_ranks_higher(self):
        """A document found by both retrievers should outrank one found by only one."""
        list1 = [_doc("only_semantic"), _doc("both")]
        list2 = [_doc("only_bm25"), _doc("both")]
        result = reciprocal_rank_fusion([list1, list2])

        # "both" appears in both lists → higher RRF score
        contents = [d.page_content for d in result]
        both_idx = contents.index("both")
        sem_idx = contents.index("only_semantic")
        bm25_idx = contents.index("only_bm25")
        assert both_idx < sem_idx
        assert both_idx < bm25_idx

    def test_rrf_scores_in_metadata(self):
        docs = [_doc("A"), _doc("B")]
        result = reciprocal_rank_fusion([docs])

        for doc in result:
            assert "rrf_score" in doc.metadata
            assert isinstance(doc.metadata["rrf_score"], float)
            assert doc.metadata["rrf_score"] > 0

    def test_rrf_score_higher_for_top_ranked(self):
        docs = [_doc("first"), _doc("second"), _doc("third")]
        result = reciprocal_rank_fusion([docs])

        assert result[0].metadata["rrf_score"] > result[1].metadata["rrf_score"]
        assert result[1].metadata["rrf_score"] > result[2].metadata["rrf_score"]

    # --- Deduplication ---

    def test_deduplicates_identical_content(self):
        list1 = [_doc("same content here", source="a.pdf")]
        list2 = [_doc("same content here", source="b.pdf")]
        result = reciprocal_rank_fusion([list1, list2])

        assert len(result) == 1
        # Score should be sum from both lists
        assert result[0].metadata["rrf_score"] > 1.0 / (60 + 1)

    def test_different_content_not_deduplicated(self):
        list1 = [_doc("content A")]
        list2 = [_doc("content B")]
        result = reciprocal_rank_fusion([list1, list2])

        assert len(result) == 2

    def test_shared_prefix_not_falsely_deduplicated(self):
        """Chunks with same prefix but different content should NOT collide."""
        shared_prefix = "Introduction to RAG systems. " * 20  # >200 chars
        list1 = [_doc(shared_prefix + "Chunk A details about vector search.")]
        list2 = [_doc(shared_prefix + "Chunk B details about BM25 scoring.")]
        result = reciprocal_rank_fusion([list1, list2])

        assert len(result) == 2

    # --- Edge cases ---

    def test_empty_lists(self):
        result = reciprocal_rank_fusion([[], []])
        assert result == []

    def test_no_lists(self):
        result = reciprocal_rank_fusion([])
        assert result == []

    def test_one_empty_one_populated(self):
        result = reciprocal_rank_fusion([[], [_doc("A")]])
        assert len(result) == 1
        assert result[0].page_content == "A"

    # --- k parameter ---

    def test_custom_k_affects_scores(self):
        # Use separate doc instances to avoid shared metadata mutation
        result_k10 = reciprocal_rank_fusion([[_doc("A")]], k=10)
        result_k60 = reciprocal_rank_fusion([[_doc("A")]], k=60)

        # Lower k → higher score for rank 1: 1/(10+1) ≈ 0.0909 > 1/(60+1) ≈ 0.0164
        assert result_k10[0].metadata["rrf_score"] > result_k60[0].metadata["rrf_score"]

    # --- Metadata preservation ---

    def test_preserves_original_metadata(self):
        doc = _doc("content", source="test.pdf", page=5)
        result = reciprocal_rank_fusion([[doc]])

        assert result[0].metadata["source"] == "test.pdf"
        assert result[0].metadata["page"] == 5
        assert "rrf_score" in result[0].metadata

    # --- RRF score calculation verification ---

    def test_rrf_score_formula(self):
        """Verify RRF score matches the formula: 1/(k + rank)."""
        k = 60
        docs = [_doc("A"), _doc("B")]
        result = reciprocal_rank_fusion([docs], k=k)

        # Rank 1: 1/(60+1) ≈ 0.016393
        assert abs(result[0].metadata["rrf_score"] - 1.0 / (k + 1)) < 1e-5
        # Rank 2: 1/(60+2) ≈ 0.016129
        assert abs(result[1].metadata["rrf_score"] - 1.0 / (k + 2)) < 1e-5

    def test_rrf_score_two_lists_formula(self):
        """Document in both lists at rank 1: score = 1/(k+1) + 1/(k+1) = 2/(k+1)."""
        k = 60
        list1 = [_doc("A")]
        list2 = [_doc("A")]
        result = reciprocal_rank_fusion([list1, list2], k=k)

        expected = 2.0 / (k + 1)
        assert abs(result[0].metadata["rrf_score"] - expected) < 1e-5
