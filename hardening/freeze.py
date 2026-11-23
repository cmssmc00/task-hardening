"""Freeze hidden cases and references on disk, with a SHA-256 manifest.

Grading against frozen, hashed references (instead of recomputing them at test time) means a later change to
the reference solver or to a library version cannot silently change what "correct" means. The manifest is
checked before every grading run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .task import HardTask, _jsonable


def _dump(obj, path: Path) -> None:
    path.write_text(json.dumps(obj, sort_keys=True, indent=1, default=_jsonable) + "\n")


def freeze(task: HardTask, seeds: list[int], out_dir: str | Path) -> Path:
    """Write hidden inputs, references and MANIFEST.sha256 under out_dir. The generator's truth is not
    written: graders compare against the reference, and the truth is only for the authoring gates."""
    out = Path(out_dir)
    (out / "cases").mkdir(parents=True, exist_ok=True)
    (out / "ref").mkdir(parents=True, exist_ok=True)
    for i, seed in enumerate(seeds):
        case = task.make_case(seed)
        _dump(case.inputs, out / "cases" / f"case_{i:02d}.json")
        _dump(task.reference(case.inputs), out / "ref" / f"case_{i:02d}.json")
    lines = []
    for p in sorted(out.rglob("*.json")):
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}")
    (out / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")
    return out


def verify(out_dir: str | Path) -> list[str]:
    """Return the files whose hash no longer matches the manifest (empty list = intact)."""
    out = Path(out_dir)
    bad = []
    listed = set()
    for line in (out / "MANIFEST.sha256").read_text().splitlines():
        digest, rel = line.split(maxsplit=1)
        listed.add(rel)
        p = out / rel
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            bad.append(rel)
    extra = [p.relative_to(out).as_posix() for p in out.rglob("*.json") if p.relative_to(out).as_posix() not in listed]
    return bad + [f"{e} (not in manifest)" for e in extra]
