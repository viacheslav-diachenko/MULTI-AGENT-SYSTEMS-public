"""hw10 evaluation harness — conftest.

hw10 is a self-contained extension of homework-lesson-8: all hw8 source
files now live physically under homework-lesson-10/ (per the README
structure). conftest.py just adds PROJECT_ROOT to sys.path so tests can
`from schemas import ResearchPlan`, `from supervisor import ...` etc.

Responsibilities of this conftest:
  1) sys.path mount на обрану базу + import-path guard (ISSUE 3 з code review)
  2) autouse fixture thread_id per test + reset_thread() cleanup
  3) session-scoped staleness guard для fixtures/hw8/_manifest.json
     (code-drift, dirty-tree, stale metadata)
  4) golden_dataset loader
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PROJECT_ROOT.parent
BASE_DIR = PROJECT_ROOT  # hw8 source files live here directly

# sys.path mount + import-path guard — гарантуємо, що config/supervisor
# приходять з PROJECT_ROOT, а не з випадкового site-packages.
sys.path.insert(0, str(PROJECT_ROOT))

_CANONICAL_MODULES = ("config", "supervisor")
for _modname in _CANONICAL_MODULES:
    try:
        _mod = __import__(_modname)
    except ImportError as exc:  # pragma: no cover — structural failure
        raise RuntimeError(
            f"Cannot import {_modname!r} from {PROJECT_ROOT}: {exc}"
        ) from exc
    _got = pathlib.Path(_mod.__file__).resolve().parent
    if _got != PROJECT_ROOT:
        raise RuntimeError(
            f"Import shadowing: {_modname} loaded from {_got}, expected {PROJECT_ROOT}. "
            "Remove conflicting installed package or reorder sys.path."
        )

FIXTURES_DIR = PROJECT_ROOT / "fixtures" / "hw8"
MANIFEST_PATH = FIXTURES_DIR / "_manifest.json"

# Runtime paths under hw10 itself (since hw8 files live here now).
# git status / git diff against these detects that fixtures must be re-recorded.
_RUNTIME_PATHS = [
    "homework-lesson-10/config.py",
    "homework-lesson-10/supervisor.py",
    "homework-lesson-10/retriever.py",
    "homework-lesson-10/tools.py",
    "homework-lesson-10/main.py",
    "homework-lesson-10/schemas.py",
    "homework-lesson-10/tool_parser.py",
    "homework-lesson-10/agents",
]


def _git(args: list[str]) -> str:
    """Run git from REPO_ROOT, fail-loud на non-zero."""
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _prompts_hash() -> str:
    """Hash конкатенованих prompt-функцій з обраної бази.
    hw8 експортує get_supervisor_prompt/get_planner_prompt/get_researcher_prompt/get_critic_prompt;
    якщо набір інший — fallback до config.py bytes."""
    try:
        import config  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(f"config module not importable: {exc}") from exc

    chunks: list[bytes] = []
    for fn_name in (
        "get_supervisor_prompt",
        "get_planner_prompt",
        "get_researcher_prompt",
        "get_critic_prompt",
    ):
        fn = getattr(config, fn_name, None)
        if callable(fn):
            try:
                chunks.append(str(fn()).encode("utf-8"))
            except TypeError:
                # Деякі prompt-getter-и приймають settings — передаємо None.
                chunks.append(str(fn(None)).encode("utf-8"))
    if not chunks:
        # hw8 може тримати промпти як константи в config.py.
        chunks.append((BASE_DIR / "config.py").read_bytes())
    return _hash_bytes(b"\n---\n".join(chunks))


def _golden_dataset_hash() -> str:
    path = PROJECT_ROOT / "tests" / "golden_dataset.json"
    return _hash_bytes(path.read_bytes())


def _model_endpoint_hash() -> str:
    import config  # type: ignore

    s = config.Settings()
    sig = f"{getattr(s, 'api_base', '')}|{getattr(s, 'model_name', '')}|{getattr(s, 'temperature', '')}"
    return _hash_bytes(sig.encode("utf-8"))


def _corpus_hash() -> str | None:
    index_dir = BASE_DIR / "index"
    if not index_dir.is_dir():
        return None
    h = hashlib.sha256()
    for p in sorted(index_dir.rglob("*")):
        if p.is_file():
            h.update(p.name.encode("utf-8"))
            h.update(p.read_bytes())
    return "sha256:" + h.hexdigest()


def _git_runtime_status() -> tuple[bool, str]:
    """(dirty, porcelain_output) для runtime-шляхів hw10."""
    out = _git(["status", "--porcelain", "--", *_RUNTIME_PATHS])
    return (bool(out.strip()), out)


def _verify_manifest(manifest: dict) -> None:
    """Raise з осмисленим повідомленням при будь-якому drift."""
    # Base-match guard (manifest schema лишає поле hw_base для зворотної сумісності)
    if manifest.get("hw_base") not in (None, "hw8"):
        raise RuntimeError(
            f"Manifest was recorded for hw_base={manifest.get('hw_base')!r} "
            "but hw10 now expects hw_base='hw8' (or unset). Re-record fixtures."
        )

    # Freshness (30 days)
    try:
        gen_at = datetime.fromisoformat(manifest["generated_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise RuntimeError(f"Invalid generated_at in manifest: {exc}") from exc
    if datetime.now(timezone.utc) - gen_at > timedelta(days=30):
        raise RuntimeError(
            f"Fixtures older than 30 days (generated_at={manifest['generated_at']}). "
            "Re-record: python scripts/record_fixtures.py"
        )

    # Hash drift — all 4 dimensions that record_fixtures writes.
    if manifest.get("prompts_hash") != _prompts_hash():
        raise RuntimeError(
            "prompts_hash drift — base prompts changed since fixtures were recorded. "
            "Re-record: python scripts/record_fixtures.py"
        )
    if manifest.get("golden_dataset_hash") != _golden_dataset_hash():
        raise RuntimeError(
            "golden_dataset_hash drift — tests/golden_dataset.json changed since recording."
        )
    if manifest.get("model_endpoint_hash") != _model_endpoint_hash():
        raise RuntimeError(
            "model_endpoint_hash drift — Settings.api_base / model_name / temperature "
            "changed since fixtures were recorded. Re-record with current model."
        )
    expected_corpus = _corpus_hash()
    if manifest.get("corpus_hash") != expected_corpus:
        raise RuntimeError(
            f"corpus_hash drift — FAISS index changed since fixtures recorded. "
            f"manifest={manifest.get('corpus_hash')!r}, current={expected_corpus!r}. "
            "Re-ingest and re-record fixtures."
        )

    # Committed code drift
    head = _git(["rev-parse", "HEAD"])
    base_commit = manifest.get("base_commit")
    if base_commit and base_commit != head:
        diff = _git(["diff", "--stat", f"{base_commit}", "HEAD", "--", *_RUNTIME_PATHS])
        if diff:
            raise RuntimeError(
                f"Runtime code drift since fixtures recorded ({base_commit[:8]}..HEAD):\n"
                f"{diff}\nRe-record fixtures or revert runtime paths."
            )

    # Dirty-tree guard
    dirty, porcelain = _git_runtime_status()
    if dirty:
        raise RuntimeError(
            f"hw10 runtime paths have uncommitted changes:\n"
            f"{porcelain}\n"
            "Commit/stash or re-record fixtures."
        )


# Tests that do NOT need recorded fixtures — staleness guard must not block them.
# Checked as substrings against the item's file path (POSIX, with forward slashes).
_FIXTURE_FREE_PATHS = (
    "tests/smoke/",
    "tests/enhancements/test_judge_bias.py",
)

# Cache verified-manifest state for a single session run so we don't re-hash
# prompts/corpus once per test.
_MANIFEST_STATE: dict[str, object] = {"validated": False, "error": None}


def _ensure_manifest_validated() -> None:
    if _MANIFEST_STATE["validated"]:
        err = _MANIFEST_STATE["error"]
        if err is not None:
            pytest.skip(str(err))
        return
    _MANIFEST_STATE["validated"] = True
    try:
        if not MANIFEST_PATH.is_file():
            raise RuntimeError(
                f"Manifest not found at {MANIFEST_PATH}. "
                f"Run: python scripts/record_fixtures.py"
            )
        manifest = json.loads(MANIFEST_PATH.read_text())
        _verify_manifest(manifest)
    except Exception as exc:
        _MANIFEST_STATE["error"] = exc
        pytest.skip(str(exc))


@pytest.fixture(autouse=True)
def _staleness_guard(request) -> None:  # noqa: ANN001
    """Autouse guard: validates manifest lazily.

    Skips validation for fixture-free suites (`tests/smoke/`, `test_judge_bias.py`)
    so that explicit optional runs still work when fixtures are absent.
    Validation itself is memoized per session — only the first gated test pays
    the git/hash cost.
    """
    fspath = str(request.node.fspath).replace("\\", "/")
    if any(marker in fspath for marker in _FIXTURE_FREE_PATHS):
        return
    _ensure_manifest_validated()


@pytest.fixture
def thread_id() -> str:
    """Уникальний thread_id per test + cleanup через supervisor.reset_thread."""
    tid = uuid.uuid4().hex
    yield tid
    try:
        import supervisor  # type: ignore
    except ImportError:
        return
    reset = getattr(supervisor, "reset_thread", None)
    if callable(reset):
        try:
            reset(tid)
        except Exception:  # pragma: no cover — defensive, teardown mustn't raise
            pass


@pytest.fixture(scope="session")
def golden_dataset() -> list[dict]:
    path = PROJECT_ROOT / "tests" / "golden_dataset.json"
    return json.loads(path.read_text())


@pytest.fixture(scope="session")
def fixtures_dir() -> pathlib.Path:
    return FIXTURES_DIR


def load_agent_fixtures(name: str) -> list[dict]:
    """Читає fixtures/hw8/{name}_outputs.json під час parametrize-collection.

    Якщо fixtures відсутні — повертає 1 stub-запис з маркером _missing_fixtures:
    тести побачать його через guard-helper `skip_if_stub(record)` і зроблять
    акуратний `pytest.skip` замість падіння стеком під час collection.
    """
    path = FIXTURES_DIR / f"{name}_outputs.json"
    if not path.is_file():
        return [{"_missing_fixtures": True, "input": f"<no fixtures for {name}>",
                 "category": "happy_path", "outputs": [], "tool_calls": []}]
    return json.loads(path.read_text())


def skip_if_stub(record: dict) -> None:
    """Test-level graceful skip when fixtures absent. Message tells user how
    to recover."""
    if record.get("_missing_fixtures"):
        import pytest as _pytest
        _pytest.skip(
            f"No fixtures at {FIXTURES_DIR}. "
            f"Run: python scripts/record_fixtures.py"
        )
