"""Durable memory: structured entries, expiry auditing and changelog hygiene.

``MEMORY.md`` documented strong anti-staleness rules and then had no way to
enforce them. Entries are now a parseable table::

    | id | tag | fact | established | expires | source |

so ``omniagi memory --audit`` (and therefore CI) fails on facts that are past
their expiry date instead of letting them quietly rot.

Machine-specific state (hostnames, usernames, free-disk figures) belongs in the
gitignored ``memory/local.md``, never in the public durable memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .paths import resolve
from .results import CheckResult

MEMORY_FILE = "MEMORY.md"
CHANGELOG_FILE = "memory/CHANGELOG.md"
LOCAL_FILE = "memory/local.md"
NEVER = "never"
WARN_WINDOW_DAYS = 30

_ROW_RE = re.compile(r"^\|(?P<cells>.+)\|\s*$")
_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|$")

#: Patterns that must never appear in the public durable memory.
LEAK_PATTERNS: list[tuple[str, str]] = [
    (r"(?:/Users/|/home/|C:\\\\Users\\\\)[A-Za-z0-9_.-]+", "host home directory path"),
    (r"(?i)\bdisk free\b|\bfree disk\b|\b\d+(?:\.\d+)?\s*GB free\b", "volatile disk figure"),
]


class MemoryError_(RuntimeError):
    """Raised when MEMORY.md cannot be parsed."""


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    tag: str
    fact: str
    established: date
    expires: date | None
    source: str

    def is_expired(self, today: date | None = None) -> bool:
        if self.expires is None:
            return False
        return self.expires < (today or date.today())

    def days_remaining(self, today: date | None = None) -> int | None:
        if self.expires is None:
            return None
        return (self.expires - (today or date.today())).days

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tag": self.tag,
            "fact": self.fact,
            "established": self.established.isoformat(),
            "expires": self.expires.isoformat() if self.expires else NEVER,
            "source": self.source,
        }


def _parse_date(value: str, field: str, entry_id: str) -> date:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise MemoryError_(
            f"memory entry '{entry_id}' has an invalid {field} date {value!r} (want YYYY-MM-DD)"
        ) from exc


def parse_memory(path: Path | None = None) -> list[MemoryEntry]:
    """Parse the structured entry table out of MEMORY.md."""
    target = path or resolve(MEMORY_FILE)
    if not target.is_file():
        raise MemoryError_(f"{MEMORY_FILE} not found at {target}")

    entries: list[MemoryEntry] = []
    seen: set[str] = set()
    in_table = False
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if _SEPARATOR_RE.match(line):
            in_table = True
            continue
        match = _ROW_RE.match(line)
        if not match:
            in_table = False
            continue
        cells = [cell.strip() for cell in match.group("cells").split("|")]
        if not in_table or len(cells) != 6:
            continue
        entry_id, tag, fact, established, expires, source = cells
        if entry_id.lower() == "id":
            continue
        if entry_id in seen:
            raise MemoryError_(f"duplicate memory entry id '{entry_id}'")
        seen.add(entry_id)
        entries.append(
            MemoryEntry(
                id=entry_id,
                tag=tag,
                fact=fact,
                established=_parse_date(established, "established", entry_id),
                expires=None
                if expires.lower() == NEVER
                else _parse_date(expires, "expires", entry_id),
                source=source,
            )
        )
    if not entries:
        raise MemoryError_(f"{MEMORY_FILE} contains no structured entries")
    return entries


def check_memory_expiry(today: date | None = None) -> CheckResult:
    """Fail on entries past their expiry; warn when expiry is imminent."""
    name = "memory.expiry_audit"
    try:
        entries = parse_memory()
    except MemoryError_ as exc:
        return CheckResult.failed(name, str(exc))

    now = today or date.today()
    expired = [
        f"{entry.id}: expired {entry.expires} - correct or remove it, and log the change"
        for entry in entries
        if entry.is_expired(now)
    ]
    if expired:
        return CheckResult.failed(name, "MEMORY.md contains expired facts", expired)

    soon = [
        f"{entry.id}: expires {entry.expires} ({entry.days_remaining(now)} days)"
        for entry in entries
        if entry.expires is not None
        and entry.expires <= now + timedelta(days=WARN_WINDOW_DAYS)
    ]
    if soon:
        return CheckResult.warned(name, "MEMORY.md facts are approaching expiry", soon)
    return CheckResult.passed(name, f"{len(entries)} durable facts, none expired")


def check_memory_hygiene() -> CheckResult:
    """No machine-specific or personal state in the public durable memory."""
    name = "memory.hygiene"
    target = resolve(MEMORY_FILE)
    errors: list[str] = []
    if not target.is_file():
        return CheckResult.failed(name, f"{MEMORY_FILE} not found")
    for lineno, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        for pattern, reason in LEAK_PATTERNS:
            if re.search(pattern, line):
                errors.append(f"{MEMORY_FILE}:{lineno}: {reason} belongs in {LOCAL_FILE}")
    return CheckResult.from_errors(
        name,
        errors,
        "durable memory contains no machine-specific or personal state",
        "durable memory leaks machine-specific state",
    )


# -- changelog -----------------------------------------------------------------


def dedupe_changelog(path: Path | None = None) -> int:
    """Collapse identical consecutive changelog lines. Returns lines removed."""
    target = path or resolve(CHANGELOG_FILE)
    if not target.is_file():
        return 0
    lines = target.read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    removed = 0
    for line in lines:
        if kept and line.strip() and line == kept[-1]:
            removed += 1
            continue
        kept.append(line)
    if removed:
        target.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return removed


def append_changelog(message: str, path: Path | None = None, today: date | None = None) -> bool:
    """Append a dated changelog line, skipping an identical consecutive entry.

    Returns ``True`` when a line was written.
    """
    target = path or resolve(CHANGELOG_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = f"- {(today or date.today()).isoformat()} {message.strip()}"
    existing = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
    for line in reversed(existing):
        if line.strip():
            if line.strip() == entry:
                return False
            break
    with target.open("a", encoding="utf-8") as handle:
        handle.write(entry + "\n")
    return True


def check_changelog() -> CheckResult:
    """No identical consecutive changelog lines."""
    name = "memory.changelog"
    target = resolve(CHANGELOG_FILE)
    if not target.is_file():
        return CheckResult.failed(name, f"{CHANGELOG_FILE} not found")
    lines = [line for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    duplicates = [
        f"line {index + 1}: repeats the previous entry"
        for index, line in enumerate(lines)
        if index and line == lines[index - 1]
    ]
    return CheckResult.from_errors(
        name,
        duplicates,
        f"{len(lines)} changelog entries, no consecutive duplicates",
        "changelog contains consecutive duplicate entries",
    )


def all_checks() -> list[CheckResult]:
    return [check_memory_expiry(), check_memory_hygiene(), check_changelog()]
