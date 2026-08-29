"""Integrity check for the `beta.md` autonomous work queue.

`beta.md` is operational infrastructure: an agent reads its status header and
its `## Autonomous Work Queue` section to decide what to do next. Prose review
alone has already let a stale status header and stale state markers survive
several completed commits (see BETA-038), so the machine-readable half of the
file gets a machine check.

Dependency-free on purpose. The queue is a fixed, shallow Markdown shape —
`### <STATE>` headings and `- [<STATE>] <ID> | <title>` bullets with
two-space `  - key: value` metadata beneath — and a real Markdown parser
would be a new dependency bought to re-discover a grammar this file already
pins in its own header comment. `re` and `str.splitlines()` are enough.

What counts as a failure (exit 1):

* an unknown state, in a `### heading` or an item's `[STATE]` prefix;
* an item whose `[STATE]` prefix disagrees with the heading it sits under;
* a duplicate item ID anywhere in the queue;
* more than one `IN_PROGRESS` item;
* an `IN_PROGRESS` item with no `next_action` metadata line;
* a top-level `- [...]` bullet in the queue that does not parse as an item;
* the `AUTONOMOUS_QUEUE_VERSION` marker missing entirely.

Everything softer — an actionable item missing a recommended metadata field,
an unrecognised queue version — is a warning. Warnings never fail the check,
so the years of `DONE` history written before the current metadata template
stay valid (BETA-038's `next_action`).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

QUEUE_HEADING = "## Autonomous Work Queue"

# The header comment is the grammar's own source of truth; this list is only
# the fallback for a file whose comment has been mangled.
DEFAULT_VALID_STATES = (
    "NEXT",
    "IN_PROGRESS",
    "BLOCKED",
    "READY",
    "RESEARCH",
    "DEFERRED",
    "DONE",
)

# The queue-format version this validator was written against. A different
# value is a warning, not an error: the file may have moved ahead of this
# script, and failing CI on that helps nobody.
KNOWN_QUEUE_VERSION = "1"

# Recommended metadata for work that is queued to be picked up. Only enforced
# (as warnings) for the states an agent actually actions next; BLOCKED,
# RESEARCH, DEFERRED and DONE items predate this template and keep their own
# shapes.
ACTIONABLE_STATES = ("IN_PROGRESS", "NEXT", "READY")
RECOMMENDED_METADATA = (
    "priority",
    "impact",
    "effort",
    "confidence",
    "risk",
    "area",
    "objective",
)

_ITEM_RE = re.compile(r"^- \[([A-Za-z_]+)\] +([A-Za-z]+-\d+) +\| +(.+?)\s*$")
_STATE_HEADING_RE = re.compile(r"^### +([A-Za-z_]+)\s*$")
_METADATA_RE = re.compile(r"^  - ([a-z0-9_]+):(?:\s.*)?$")
_VERSION_RE = re.compile(r"^AUTONOMOUS_QUEUE_VERSION:\s*(\S+)\s*$")


class _Item:
    __slots__ = ("item_id", "state", "heading", "line", "keys")

    def __init__(self, item_id: str, state: str, heading: str | None, line: int) -> None:
        self.item_id = item_id
        self.state = state
        self.heading = heading
        self.line = line
        self.keys: set[str] = set()


def _queue_section(lines: list[str]) -> tuple[int, int] | None:
    """The half-open line range of the `## Autonomous Work Queue` section.

    Ends at the next top-level `## ` heading — `### ` subsection headings do
    not start with `"## "` (their third character is `#`), so state headings
    inside the queue are not mistaken for its end.
    """
    start = None
    for i, line in enumerate(lines):
        if line.strip() == QUEUE_HEADING:
            start = i
            break
    if start is None:
        return None
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            return start, i
    return start, len(lines)


def _parse_valid_states(section: list[str]) -> list[str]:
    """The state vocabulary listed under `Valid states:` in the header comment."""
    states: list[str] = []
    collecting = False
    for raw in section:
        stripped = raw.strip()
        if stripped == "Valid states:":
            collecting = True
            continue
        if collecting:
            if re.fullmatch(r"[A-Z_]+", stripped):
                states.append(stripped)
            else:
                break
    return states


def validate(text: str) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for the queue in *text*.

    An empty ``errors`` list means the queue is structurally sound.
    """
    errors: list[str] = []
    warnings: list[str] = []
    lines = text.splitlines()

    span = _queue_section(lines)
    if span is None:
        return [f"{QUEUE_HEADING!r} heading not found"], warnings
    start, end = span
    section = lines[start:end]

    valid_states = _parse_valid_states(section)
    if not valid_states:
        warnings.append(
            "could not read 'Valid states:' from the header comment; "
            "using the built-in list"
        )
        valid_states = list(DEFAULT_VALID_STATES)

    version = None
    for raw in section:
        match = _VERSION_RE.match(raw.strip())
        if match:
            version = match.group(1)
            break
    if version is None:
        errors.append("AUTONOMOUS_QUEUE_VERSION marker is missing from the queue header")
    elif version != KNOWN_QUEUE_VERSION:
        warnings.append(
            f"queue version is {version!r}; this validator was written for "
            f"{KNOWN_QUEUE_VERSION!r} and may be out of date"
        )

    current_heading: str | None = None
    current_item: _Item | None = None
    items: list[_Item] = []

    for offset, raw in enumerate(section):
        lineno = start + offset + 1

        heading = _STATE_HEADING_RE.match(raw)
        if heading:
            current_heading = heading.group(1)
            current_item = None
            if current_heading not in valid_states:
                errors.append(
                    f"line {lineno}: unknown state heading '### {current_heading}'"
                )
            continue

        item = _ITEM_RE.match(raw)
        if item:
            state, item_id, _title = item.group(1), item.group(2), item.group(3)
            current_item = _Item(item_id, state, current_heading, lineno)
            items.append(current_item)
            if state not in valid_states:
                errors.append(f"line {lineno}: item {item_id} has unknown state '[{state}]'")
            if current_heading is None:
                errors.append(
                    f"line {lineno}: item {item_id} appears before any '### <STATE>' heading"
                )
            elif current_heading in valid_states and state != current_heading:
                errors.append(
                    f"line {lineno}: item {item_id} is '[{state}]' under "
                    f"'### {current_heading}'"
                )
            continue

        metadata = _METADATA_RE.match(raw)
        if metadata and current_item is not None:
            current_item.keys.add(metadata.group(1))
            continue

        # A top-level bracketed bullet that reached here is a malformed item:
        # a real metadata line is indented two spaces, and prose never starts
        # a line with "- [".
        if raw.startswith("- ["):
            errors.append(f"line {lineno}: malformed queue item: {raw.strip()!r}")

    first_seen: dict[str, int] = {}
    for it in items:
        if it.item_id in first_seen:
            errors.append(
                f"line {it.line}: duplicate item id {it.item_id} "
                f"(first seen at line {first_seen[it.item_id]})"
            )
        else:
            first_seen[it.item_id] = it.line

    in_progress = [it for it in items if it.state == "IN_PROGRESS"]
    if len(in_progress) > 1:
        where = ", ".join(f"{it.item_id} (line {it.line})" for it in in_progress)
        errors.append(f"more than one IN_PROGRESS item: {where}")
    for it in in_progress:
        if "next_action" not in it.keys:
            errors.append(
                f"line {it.line}: IN_PROGRESS item {it.item_id} has no 'next_action' line"
            )

    for it in items:
        if it.state not in ACTIONABLE_STATES:
            continue
        missing = [key for key in RECOMMENDED_METADATA if key not in it.keys]
        if missing:
            warnings.append(
                f"line {it.line}: {it.state} item {it.item_id} is missing "
                f"recommended metadata: {', '.join(missing)}"
            )

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    strict = "--strict" in args
    args = [a for a in args if a != "--strict"]
    path = Path(args[0]) if args else Path(__file__).resolve().parent.parent / "beta.md"

    if not path.exists():
        # `beta.md` lives only on the `beta` branch. CI runs this workflow on
        # every branch, so its absence is not a failure here — the branch that
        # owns the file is where the check has teeth.
        print(f"{path} not found; nothing to validate")
        return 0

    errors, warnings = validate(path.read_text(encoding="utf-8"))
    for warning in warnings:
        print(f"warning: {warning}")
    for error in errors:
        print(f"error: {error}")

    if errors or (strict and warnings):
        print(f"\n{path}: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"{path}: queue OK ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
