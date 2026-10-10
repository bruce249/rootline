from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1] / "rootline"
_SUFFIXES = {".py", ".md", ".j2", ".json", ".yaml", ".yml", ".txt"}


def test_rootline_does_not_reference_ground_truth():
    offenders = []
    for path in _ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in _SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        if "answers.yaml" in text or "bench/" in text:
            offenders.append(str(path))
    assert offenders == []
