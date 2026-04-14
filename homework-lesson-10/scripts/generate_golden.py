"""Synthetic golden-dataset seeding via Ragas TestsetGenerator + manual review stub.

Usage:
    python scripts/generate_golden.py --out tests/golden_dataset_ragas.json

The output is a *draft* — lesson-10 explicitly warns that synthetic examples
require manual review. Inspect, edit, drop bad items, then merge into
tests/golden_dataset.json by hand.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
BASE_DIR = PROJECT_ROOT  # hw8 source files live under hw10 directly
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "tests" / "golden_dataset_ragas.json"),
        help="Output path for draft dataset (JSON).",
    )
    parser.add_argument(
        "--size", type=int, default=7, help="Number of synthetic examples to generate."
    )
    parser.add_argument(
        "--docs-dir",
        default=None,
        help="Optional directory of .txt/.md documents to seed the knowledge graph. "
        "Defaults to homework-lesson-{base}/data/ if present.",
    )
    args = parser.parse_args()

    try:
        from ragas.testset import TestsetGenerator
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from langchain_openai import OpenAIEmbeddings
        from langchain_core.documents import Document as LCDocument
    except ImportError as exc:
        raise RuntimeError(
            "Missing deps. Run: pip install -r requirements.txt"
        ) from exc

    from config import create_llm  # type: ignore

    docs_dir = (
        pathlib.Path(args.docs_dir)
        if args.docs_dir
        else BASE_DIR / "data"
    )
    if not docs_dir.is_dir():
        raise RuntimeError(
            f"docs_dir not found: {docs_dir}. Provide --docs-dir explicitly."
        )

    documents: list = []
    for p in docs_dir.rglob("*"):
        if p.suffix.lower() in {".txt", ".md"} and p.is_file():
            documents.append(
                LCDocument(page_content=p.read_text(errors="ignore"), metadata={"source": str(p)})
            )
    if not documents:
        raise RuntimeError(f"No .txt/.md documents found in {docs_dir}")

    generator = TestsetGenerator(
        llm=LangchainLLMWrapper(create_llm()),
        embedding_model=LangchainEmbeddingsWrapper(OpenAIEmbeddings()),
    )
    testset = generator.generate_with_langchain_docs(documents, testset_size=args.size)

    draft = []
    for sample in testset.to_list():
        draft.append(
            {
                "input": sample.get("user_input") or sample.get("question") or "",
                "expected_output": sample.get("reference") or sample.get("ground_truth") or "",
                "category": "happy_path",
                "_ragas_raw": sample,
            }
        )

    out = pathlib.Path(args.out)
    out.write_text(json.dumps(draft, indent=2, ensure_ascii=False))
    print(
        f"Wrote {len(draft)} draft examples → {out}.\n"
        "NEXT: Manual review — edit/drop bad items, then merge into golden_dataset.json."
    )


if __name__ == "__main__":
    main()
