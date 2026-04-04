"""Hybrid retrieval module.

Combines semantic search (FAISS) + BM25 (lexical) with Reciprocal Rank Fusion
(RRF) scoring and Infinity reranker.
"""

import hashlib
import json
import logging
import os
from typing import Optional

import httpx
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.callbacks import CallbackManagerForChainRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_openai import OpenAIEmbeddings
from pydantic import ConfigDict

from config import Settings

logger = logging.getLogger(__name__)


def _matches_filters(
    doc: Document,
    source_filter: str | None = None,
    page_filter: int | None = None,
) -> bool:
    """Return True when a document matches optional metadata filters."""
    if source_filter:
        source_lower = source_filter.lower()
        source_name = os.path.basename(doc.metadata.get("source", "")).lower()
        if source_lower not in source_name:
            return False
    if page_filter is not None and doc.metadata.get("page") != page_filter:
        return False
    return True


class InfinityReranker:
    """Reranker client for Infinity API."""

    def __init__(self, url: str, top_n: int = 3):
        self.url = url
        self.top_n = top_n

    def rerank(self, query: str, documents: list[Document]) -> list[Document]:
        if not documents:
            return []

        doc_texts = [d.page_content for d in documents]

        try:
            resp = httpx.post(
                self.url,
                json={"query": query, "documents": doc_texts, "return_documents": False},
                timeout=30.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Reranker request failed: %s — returning unranked results", e)
            return documents[: self.top_n]

        results = resp.json().get("results", [])
        # Results are already sorted by relevance_score descending
        reranked = []
        for item in results[: self.top_n]:
            idx = item["index"]
            doc = documents[idx]
            doc.metadata["rerank_score"] = item["relevance_score"]
            reranked.append(doc)

        return reranked


def reciprocal_rank_fusion(
    ranked_lists: list[list[Document]],
    k: int = 60,
) -> list[Document]:
    """Merge multiple ranked lists using Reciprocal Rank Fusion (RRF).

    RRF assigns each document a score: RRF(d) = Σ 1/(k + rank_i(d))
    where k is a constant (default 60) and rank_i is the 1-based rank
    of document d in the i-th list. Documents found by multiple retrievers
    accumulate higher scores.

    Args:
        ranked_lists: List of ranked document lists from different retrievers.
        k: RRF constant that controls how much rank position matters.
            Higher k → more uniform scores; lower k → top ranks dominate.

    Returns:
        Deduplicated list of documents sorted by RRF score (descending).
        Each document has 'rrf_score' in its metadata.
    """
    scores: dict[str, float] = {}
    doc_map: dict[str, Document] = {}

    for ranked_docs in ranked_lists:
        for rank, doc in enumerate(ranked_docs, start=1):
            # Use hash of full content to avoid false collisions from shared prefixes
            # (e.g. PDF chunks with identical headers or repeated introductions)
            content_key = hashlib.md5(doc.page_content.encode()).hexdigest()
            scores[content_key] = scores.get(content_key, 0.0) + 1.0 / (k + rank)
            # Keep the first occurrence (preserves original metadata)
            if content_key not in doc_map:
                doc_map[content_key] = doc

    # Sort by RRF score descending
    sorted_keys = sorted(scores, key=lambda key: scores[key], reverse=True)

    result = []
    for key in sorted_keys:
        doc = doc_map[key]
        doc.metadata["rrf_score"] = round(scores[key], 6)
        result.append(doc)

    return result


class HybridRetriever(BaseRetriever):
    """Ensemble retriever: FAISS semantic + BM25 lexical + RRF + Infinity reranker."""

    vectorstore: FAISS
    bm25: BM25Retriever
    reranker: InfinityReranker
    semantic_k: int = 10
    bm25_k: int = 10
    rrf_k: int = 60

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def search(
        self,
        query: str,
        *,
        source_filter: str | None = None,
        page_filter: int | None = None,
        rerank_top_n: int | None = None,
    ) -> list[Document]:
        """Search documents with optional pre-rerank metadata filtering."""
        # 1. Semantic search
        semantic_docs = self.vectorstore.similarity_search(query, k=self.semantic_k)

        # 2. BM25 search
        bm25_docs = self.bm25.invoke(query)

        # 3. Reciprocal Rank Fusion — documents found by both retrievers
        #    get higher scores than those found by only one
        merged = reciprocal_rank_fusion(
            [semantic_docs, bm25_docs], k=self.rrf_k,
        )

        logger.info(
            "Hybrid search: %d semantic + %d BM25 → %d unique (RRF)",
            len(semantic_docs), len(bm25_docs), len(merged),
        )

        if source_filter is not None or page_filter is not None:
            pre_filter_count = len(merged)
            merged = [
                doc for doc in merged
                if _matches_filters(doc, source_filter=source_filter, page_filter=page_filter)
            ]
            logger.info(
                "Applied pre-rerank filters source=%r page=%r → %d/%d documents",
                source_filter, page_filter, len(merged), pre_filter_count,
            )

        if not merged:
            return []

        original_top_n = self.reranker.top_n
        if rerank_top_n is not None:
            self.reranker.top_n = rerank_top_n

        try:
            return self.reranker.rerank(query, merged)
        finally:
            self.reranker.top_n = original_top_n

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForChainRun] = None,
    ) -> list[Document]:
        return self.search(query)


def get_retriever() -> HybridRetriever:
    """Load index from disk and create a HybridRetriever."""
    settings = Settings()

    # Load FAISS
    embeddings = OpenAIEmbeddings(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key.get_secret_value(),
        model=settings.embedding_model,
    )
    vectorstore = FAISS.load_local(
        settings.index_dir, embeddings, allow_dangerous_deserialization=True,
    )

    # Load BM25 chunks from JSON
    bm25_path = os.path.join(settings.index_dir, "bm25_chunks.json")
    with open(bm25_path, "r", encoding="utf-8") as f:
        bm25_data = json.load(f)

    chunks = [
        Document(page_content=item["page_content"], metadata=item["metadata"])
        for item in bm25_data
    ]

    bm25 = BM25Retriever.from_documents(chunks)
    bm25.k = settings.retrieval_top_k

    # Reranker
    reranker = InfinityReranker(url=settings.reranker_url, top_n=settings.rerank_top_n)

    return HybridRetriever(
        vectorstore=vectorstore,
        bm25=bm25,
        reranker=reranker,
        semantic_k=settings.retrieval_top_k,
        bm25_k=settings.retrieval_top_k,
    )
