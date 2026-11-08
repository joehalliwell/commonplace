"""Parts of sources, for tests: built by the source that owns them, or by a stand-in for an invented one."""

from dataclasses import dataclass, replace
from typing import Any

from commonplace._sources import SOURCES
from commonplace._types import ChatSource, Source


def owned(kind: type, **kwargs: Any) -> Any:
    """The part of type `kind`, as the source that owns it builds it: its importer, or a fetcher given `kwargs`."""
    for source in SOURCES:
        if source.fetcher_type is kind:
            return kind(source, **kwargs)
        for part in source.importers:
            if type(part) is kind:
                return part
    raise LookupError(f"No source owns a {kind.__name__}")


@dataclass(frozen=True)
class _Built:
    """Stands in for a fetcher type: configuring it hands back a fetcher already built."""

    built: Any

    def configured(self, source: Source, config: Any) -> Any:
        return self.built


def fetching(*fetchers: Any) -> list[Source]:
    """A source per fetcher, fetching with it: the source it belongs to, or a chat source named as a stub names it."""
    sources: list[Source] = []
    for part in fetchers:
        owner = part.source if isinstance(part.source, Source) else ChatSource(part.source, (), None)
        sources.append(replace(owner, fetcher_type=_Built(part)))  # type: ignore[arg-type]
    return sources
