"""Probing shared by the importers that claim an export: the ZIP by its members, or a stored member by its content."""

from pathlib import Path
from zipfile import ZipFile

_SNIFF_BYTES = 1 << 20


def zip_contains(path: Path, *members: str) -> bool:
    """Whether the ZIP at `path` holds every one of `members`; raises if it is not a ZIP."""
    with ZipFile(path) as zf:
        return set(members) <= set(zf.namelist())


def head_contains(path: Path, marker: str) -> bool:
    """Whether `marker` appears in the first megabyte of the text file at `path`."""
    with path.open(encoding="utf-8", errors="replace") as f:
        return marker in f.read(_SNIFF_BYTES)
