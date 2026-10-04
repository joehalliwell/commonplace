"""`doctor`: named operations that check the repository and fix what they safely can, run in order.

Each operation is a step returning a `DoctorReport`; selecting one is the opt-in, so a fix that
loses nothing needs no `--fix`, and `check` stops every step writing.
"""

from collections.abc import Callable
from dataclasses import dataclass

from commonplace._links import check_links, summarize
from commonplace._logging import logger
from commonplace._repo import Commonplace

_CLAUDE_SETTINGS = ".claude/settings.json"


@dataclass(frozen=True)
class DoctorReport:
    """What `doctor` put right, and what it wants a human to look at."""

    actions: list[str]
    warnings: list[str]


type Step = Callable[[Commonplace, bool], DoctorReport]


def doctor(repo: Commonplace, check: bool = False, scaffold: bool = True, links: bool = True) -> DoctorReport:
    """Run the selected operations in order, logging each as it goes."""
    steps = ((_scaffold, scaffold), (_links, links))  # In run order
    reports = []
    for n, (step, selected) in enumerate(steps, 1):
        reports.append(_run(step, selected, repo, check, f"{n}/{len(steps)}"))
    return _total(*reports)


def _run(step: Step, selected: bool, repo: Commonplace, check: bool, position: str) -> DoctorReport:
    """Run one operation under its heading, logging its results and a status line, or log that it was skipped."""
    name = step.__name__.removeprefix("_")  # A codename: the CLI flag too
    if not selected:
        logger.info(f"── {name} ({position}): skipped (--{name} to run)")
        return DoctorReport(actions=[], warnings=[])
    logger.info(f"── {name} ({position})")
    report = step(repo, check)
    for action in report.actions:
        logger.info(_indent(action))
    for warning in report.warnings:
        logger.warning(_indent(warning))
    logger.info(_indent(_tally(report) if report.actions or report.warnings else "ok"))
    return report


def _scaffold(repo: Commonplace, check: bool) -> DoctorReport:
    """Restore and commit missing scaffolding, and diff whatever has fallen behind `init`'s templates."""
    if check:
        actions = [f"Would create {path}" for path in repo.missing_scaffolding()]
    else:
        actions = [_restored(path) for path in repo.restore_scaffolding()]
    warnings = [
        f"{path} differs from the template init now writes:\n" + "\n".join(diff)
        for path, diff in repo.scaffolding_drift().items()
    ]
    return DoctorReport(actions=actions, warnings=warnings)


def _restored(path: str) -> str:
    # The marketplace config only takes effect once Claude Code is told to add it.
    if path == _CLAUDE_SETTINGS:
        return f"Created {path}; to enable its plugins, run in Claude Code: /plugin marketplace add joehalliwell/commonplace"
    return f"Created {path}"


def _links(repo: Commonplace, check: bool) -> DoctorReport:
    """Find broken links; there is nothing to write."""
    return DoctorReport(actions=[], warnings=summarize(check_links(repo.root, list(repo.paths()))))


def _total(*reports: DoctorReport) -> DoctorReport:
    report = DoctorReport(
        actions=[a for r in reports for a in r.actions], warnings=[w for r in reports for w in r.warnings]
    )
    logger.info(f"doctor: {_tally(report)}")
    return report


def _indent(text: str) -> str:
    return "\n".join(f"   {line}" for line in text.splitlines())


def _tally(report: DoctorReport) -> str:
    return f"{len(report.actions)} fixed, {len(report.warnings)} warnings"
