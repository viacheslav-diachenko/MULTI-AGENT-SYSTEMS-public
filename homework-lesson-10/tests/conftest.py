"""tests/-local conftest: second-line guard проти випадкової збірки
enhancements/ та smoke/ у *default* deepeval/pytest run.

pytest.ini уже виключає ці директорії через norecursedirs. Якщо попри це
pytest зібрав items з цих директорій, хук прибирає їх — АЛЕ тільки коли
користувач не націлив їх явно (тобто запустив `pytest tests/` чи
`deepeval test run tests/`).

Якщо команда містить явний шлях до enhancements/ або smoke/ (або маркер
-m enhancement / -m live), хук пропускає items без змін — optional suites
тепер запускаються саме так, як задокументовано в README.
"""
from __future__ import annotations

import warnings
from pathlib import Path


def _explicitly_targeted(config) -> set[str]:
    """Повертає множину {'enhancements', 'smoke'}, які користувач явно
    обрав у командному рядку — через шлях або через -m маркер."""
    targeted: set[str] = set()
    args = list(getattr(config, "args", []) or [])
    markexpr = (config.getoption("-m", default="") or "").lower()
    for arg in args:
        ap = str(arg).replace("\\", "/")
        if "tests/enhancements" in ap or ap.endswith("enhancements"):
            targeted.add("enhancements")
        if "tests/smoke" in ap or ap.endswith("smoke"):
            targeted.add("smoke")
    if "enhancement" in markexpr:
        targeted.add("enhancements")
    if "live" in markexpr:
        targeted.add("smoke")
    return targeted


def pytest_collection_modifyitems(config, items) -> None:
    targeted = _explicitly_targeted(config)
    kept, dropped = [], []
    for item in items:
        parts = Path(str(item.fspath)).parts
        if "enhancements" in parts and "enhancements" not in targeted:
            dropped.append(item.nodeid)
            continue
        if "smoke" in parts and "smoke" not in targeted:
            dropped.append(item.nodeid)
            continue
        kept.append(item)
    if dropped:
        warnings.warn(
            "Dropped from default run (use explicit path or marker to run): "
            + ", ".join(dropped[:5])
            + (f" +{len(dropped) - 5} more" if len(dropped) > 5 else ""),
            stacklevel=1,
        )
    items[:] = kept
