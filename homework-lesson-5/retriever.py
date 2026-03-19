"""Hybrid retrieval module.

Combines semantic search (FAISS) + BM25 (lexical) with Infinity reranker.
"""

import json
import os
import logging
from typing import Optional

import httpx
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.callbacks import CallbackManagerForChainRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_openai import OpenAIEmbeddings

from config import Settings

logger = logging.getLogger(__name__)


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


class HybridRetriever(BaseRetriever):
    """Ensemble retriever: FAISS semantic + BM25 lexical + Infinity reranker."""

    vectorstore: FAISS
    bm25: BM25Retriever
    reranker: InfinityReranker
    semantic_k: int = 10
    bm25_k: int = 10

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForChainRun] = None,
    ) -> list[Document]:
        # 1. Semantic search
        semantic_docs = self.vectorstore.similarity_search(query, k=self.semantic_k)

        # 2. BM25 search
        bm25_docs = self.bm25.invoke(query)

        # 3. Merge and deduplicate (by page_content prefix)
        seen = set()
        merged = []
        for doc in semantic_docs + bm25_docs:
            content_key = doc.page_content[:200]
            if content_key not in seen:
                seen.add(content_key)
                merged.append(doc)

        logger.info(
            "Hybrid search: %d semantic + %d BM25 → %d unique → reranking",
            len(semantic_docs), len(bm25_docs), len(merged),
        )

        # 4. Rerank
        return self.reranker.rerank(query, merged)


def get_retriever() -> HybridRetriever:
    """Load index from disk and create a HybridRetriever."""
    settings = Settings()

    # Load FAISS
    embeddings = OpenAIEmbeddings(
        base_url=settings.embedding_base_url,
        api_key="not-needed",
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
