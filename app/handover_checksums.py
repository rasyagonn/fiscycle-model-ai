"""Verify every payload checksum in an extracted handover package."""
from __future__ import annotations

import hashlib
from pathlib import Path


def verify(root: Path) -> int:
    lines = (root / "CHECKSUMS.sha256").read_text(encoding="utf-8").splitlines()
    seen = set()
    for line in lines:
        expected, relative = line.split("  ", 1)
        if relative in seen or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Unsafe or duplicate checksum path")
        seen.add(relative)
        file = root / relative
        if not file.is_file():
            raise FileNotFoundError(relative)
        actual = hashlib.sha256(file.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Checksum mismatch: {relative}")
    print(f"PASS: {len(lines)} payload checksums")
    return len(lines)


if __name__ == "__main__":
    verify(Path(__file__).resolve().parent)
