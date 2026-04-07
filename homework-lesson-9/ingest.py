"""Knowledge ingestion pipeline — same as hw8.

Loads PDFs from DATA_DIR, chunks, embeds via TEI, saves FAISS + BM25 to INDEX_DIR.
By default hw9 reuses the hw8 index, so you normally do NOT need to run this
inside hw9 — run it from hw8 or set DATA_DIR/INDEX_DIR in .env to hw9-local
paths first.

Usage: python ingest.py
"""

import json
import logging
import os

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def ingest() -> None:
    settings = Settings()

    docs = []
    data_dir = settings.data_dir
    for filename in sorted(os.listdir(data_dir)):
        if filename.lower().endswith(".pdf"):
            filepath = os.path.join(data_dir, filename)
            logger.info("Loading %s", filepath)
            loader = PyPDFLoader(filepath)
            docs.extend(loader.load())

    if not docs:
        logger.error("No PDF files found in %s", data_dir)
        return
    logger.info("Loaded %d pages", len(docs))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks = splitter.split_documents(docs)
    logger.info("Created %d chunks", len(chunks))

    embeddings = OpenAIEmbeddings(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key.get_secret_value(),
        model=settings.embedding_model,
        chunk_size=200,
    )
    vectorstore = FAISS.from_documents(chunks, embeddings)

    os.makedirs(settings.index_dir, exist_ok=True)
    vectorstore.save_local(settings.index_dir)
    logger.info("FAISS index saved to %s/", settings.index_dir)

    bm25_path = os.path.join(settings.index_dir, "bm25_chunks.json")
    bm25_data = [
        {"page_content": c.page_content, "metadata": c.metadata}
        for c in chunks
    ]
    with open(bm25_path, "w", encoding="utf-8") as f:
        json.dump(bm25_data, f, ensure_ascii=False)
    logger.info("BM25 chunks saved (%d chunks)", len(chunks))
    logger.info("Ingestion complete!")


if __name__ == "__main__":
    ingest()
