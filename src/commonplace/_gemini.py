import re
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile

from bs4 import BeautifulSoup
from bs4.element import PageElement, Tag
from html_to_markdown import convert_to_markdown
from rich.progress import track

from commonplace import LOGGER
from commonplace._types import ActivityLog, Importer, Message, Role

_PROMPT_PREFIX = "Prompted"
_HTML_PATH = "Takeout/My Activity/Gemini Apps/My Activity.html"


class GeminiImporter(Importer):
    """
    Importer for Gemini activity logs from Google Takeout.

    The input is a zip file containing `Takeout/My Activity/Gemini Apps/My
    Activity.html`.

    All message/response pairs are in the HTML in a weird format with no way to
    tell which thread they belong to. This is fundamentally why commonplace is
    structured around day files, rather than threads.
    """

    source: str = "gemini"

    def can_import(self, path: Path) -> bool:
        """Check if the importer can potentially handle the given file path. It
        zip file with the expected path structure."""
        try:
            with closing(ZipFile(path, "r")) as zip_file:
                # Check if the expected path exists in the zip file
                return _HTML_PATH in zip_file.namelist()
        except Exception as e:
            LOGGER.info(
                f"{path} failed Gemini importability check: {e}",
                exc_info=True,
            )
            return False

    def import_(self, path: Path) -> list[ActivityLog]:
        """Import activity logs from the Gemini file."""
        with ZipFile(path, "r") as zip_file:
            # Read the HTML file from the zip
            with zip_file.open(_HTML_PATH) as file:
                content = file.read().decode("utf-8")
                return self._parse_gemini_html(content)

    def _parse_gemini_html(self, html_content: str) -> list[ActivityLog]:
        soup = BeautifulSoup(html_content, "lxml")

        TURN_CONTAINER_SELECTOR = "div.content-cell:not(.mdl-typography--caption)"
        all_content_cells = soup.select(TURN_CONTAINER_SELECTOR)

        LOGGER.info(f"Found {len(all_content_cells)} candidate content cells in the HTML")

        # Get all mesages
        messages = []
        for cell in track(all_content_cells):
            messages.extend(self._parse_cell(cell))
        LOGGER.info(f"Parsed {len(messages)} messages")

        # Sort and group messages into day logs
        logs_by_date = defaultdict(list)
        for message in sorted(messages, key=lambda m: m.created):
            date_key = message.created.date()
            logs_by_date[date_key].append(message)

        results = []
        for date, messages in logs_by_date.items():
            log = ActivityLog(
                source=self.source,
                title=f"Gemini conversations from {date.isoformat()}",
                created=messages[0].created,
                messages=messages,
            )
            LOGGER.debug(f"Created log for {date}: {log}")
            results.append(log)

        LOGGER.info(f"Created {len(results)} day logs")
        return results

    def _to_markdown(self, elements: Iterable[PageElement]) -> str:
        """
        Convert a list of BeautifulSoup elements to a Markdown string.
        """
        html = "".join(str(element) for element in elements).strip()
        if not html:
            return ""
        return convert_to_markdown(html, heading_style="atx").strip()

    def _parse_timestamp(self, timestamp: str) -> datetime:
        """
        18 Sept 2024, 00:12:50 BST
        """
        timestamp = timestamp.lower().replace("sept", "sep")
        return datetime.strptime(timestamp, "%d %b %Y, %H:%M:%S %Z")

    def _parse_cell(self, cell: Tag) -> Iterable[Message]:
        """
        Parse the horrible HTML representation of a Gemini exchange.
        TODO: Handle images
        """

        if len(cell) == 0:
            return []

        # print(cell.encode())
        # logger.debug(cell.encode())  # Expensive but meh
        children = iter(cell.children)

        timestamp_match = None
        user_bits = []
        for child in children:
            if child.string:
                timestamp_match = re.match(r"\d{1,2} \w+ \d{4}, \d{2}:\d{2}:\d{2} \w+", child.string)
                if timestamp_match is not None:
                    break
            user_bits.append(child)

        if timestamp_match is None:
            LOGGER.debug(f"Failed to parse cell {cell})")
            return []

        timestamp = self._parse_timestamp(timestamp_match.group(0))

        ai_bits = list(children)

        user_prompt = self._to_markdown(user_bits)
        ai_response = self._to_markdown(ai_bits)

        if not user_prompt.startswith(_PROMPT_PREFIX):
            LOGGER.debug(f"Skipping cell with no user prompt: {user_prompt} (in {cell}   )")
            return []
        user_prompt = user_prompt[len(_PROMPT_PREFIX) :].strip()

        if not ai_response:
            LOGGER.debug(f"Skipping cell with no AI repsonse {ai_response} (in {cell})")
            return []

        user_message = Message(
            sender=Role.USER,
            content=user_prompt,
            created=timestamp,
        )

        ai_message = Message(
            sender=Role.ASSISTANT,
            content=ai_response,
            created=timestamp,
        )
        return user_message, ai_message
