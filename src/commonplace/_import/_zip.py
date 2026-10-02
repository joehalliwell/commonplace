"""Probing shared by the importers that claim an export ZIP by its members."""

from pathlib import Path
from zipfile import ZipFile


def zip_contains(path: Path, *members: str) -> bool:
    """Whether the ZIP at `path` holds every one of `members`; raises if it is not a ZIP."""
    with ZipFile(path) as zf:
        return set(members) <= set(zf.namelist())
