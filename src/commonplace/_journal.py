"""`journal`: open today's (or a given day's) daily journal entry in the user's editor and commit edits."""

import datetime as dt
import subprocess
from pathlib import Path

from commonplace._logging import logger
from commonplace._repo import Commonplace
from commonplace._types import Note
from commonplace._utils import dump_frontmatter, edit_in_editor, load_frontmatter


def journal(repo: Commonplace, date: str | None = None) -> Path | None:
    """Create or edit the journal entry for `date` (`YYYY-MM-DD`, default today); returns its path if committed."""
    # Journals are keyed by the user's local calendar day, not by instant, so
    # both of these are deliberately naive. Using UTC here would file an entry
    # written just after midnight under the previous day.
    if date is None:
        day = dt.datetime.now()  # noqa: DTZ005
    else:
        try:
            day = dt.datetime.strptime(date, "%Y-%m-%d")  # noqa: DTZ007
        except ValueError as e:
            raise ValueError(f"Invalid date format '{date}'. Use YYYY-MM-DD (e.g., 2025-10-11)") from e

    path = Path("journal") / day.strftime("%Y/%m/%Y-%m-%d.md")
    default_content = f"# {day.strftime('%A, %B %d, %Y')}\n\n## Tasks\n\n## Notes\n\n"

    # Load existing content or use default (without creating the file yet).
    note = repo.get(path) if (repo.root / path).exists() else Note(path, default_content)
    original_content = dump_frontmatter(note.metadata, note.body)

    try:
        edited_content = edit_in_editor(original_content, repo.config.editor)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Editor exited with error code {e.returncode}") from e
    except FileNotFoundError as e:
        raise ValueError(
            f"Editor '{repo.config.editor}' not found. Set COMMONPLACE_EDITOR environment variable or config."
        ) from e

    if edited_content is None:
        return None

    metadata, body = load_frontmatter(edited_content)
    repo.put(Note(path, body, metadata, text=note.text))
    logger.info(f"Saved journal entry to {path}")
    repo.commit(f"Update journal entry for {day.strftime('%Y-%m-%d')}")
    return path
