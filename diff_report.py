"""Report which seminars are new in a freshly-scraped seminars.ics.

Usage: python diff_report.py <old_ics_path> <new_ics_path>

Parses both calendar files into events keyed by UID and reports any UID
present in the new file but not the old one, writing a short markdown
summary to $GITHUB_STEP_SUMMARY (falling back to stdout when that variable
isn't set, e.g. when run locally).

Comparing fully-parsed files (rather than a textual diff of the two) avoids
ambiguity from the repeated BEGIN:VEVENT/END:VEVENT boundary lines, which
can otherwise cause a line-based diff to misalign block boundaries and miss
or misreport additions.
"""
import os
import sys
from datetime import datetime

Event = dict[str, str]


def parse_events(ics_text: str) -> dict[str, Event]:
    events: dict[str, Event] = {}
    current: list[str] | None = None

    for line in ics_text.splitlines():
        if line.startswith("BEGIN:VEVENT"):
            current = []
        elif line.startswith("END:VEVENT") and current is not None:
            fields = _parse_fields(current)
            uid = fields.get("UID")
            if uid:
                events[uid] = fields
            current = None
        elif current is not None:
            current.append(line)

    return events


def _parse_fields(lines: list[str]) -> Event:
    fields: Event = {}
    for line in lines:
        key, sep, value = line.partition(":")
        if sep:
            fields[key] = value
    return fields


def _format_start(dtstart: str) -> str:
    try:
        dt = datetime.strptime(dtstart, "%Y%m%dT%H%M%SZ")
        return dt.strftime("%a %b %d, %Y %H:%M UTC")
    except ValueError:
        return dtstart


def format_summary(new_events: list[Event]) -> str:
    if not new_events:
        return "### Seminar calendar\nNo new seminars added.\n"

    lines = ["### Seminar calendar", f"{len(new_events)} new seminar(s) added:", ""]
    for ev in sorted(new_events, key=lambda e: e.get("DTSTART", "")):
        speaker = ev.get("SUMMARY", "Unknown speaker")
        when = _format_start(ev.get("DTSTART", ""))
        where = ev.get("LOCATION", "")
        lines.append(f"- **{speaker}** — {when} ({where})")
    return "\n".join(lines) + "\n"


def main() -> None:
    old_path, new_path = sys.argv[1], sys.argv[2]

    try:
        with open(old_path, encoding="utf-8") as f:
            old_events = parse_events(f.read())
    except FileNotFoundError:
        old_events = {}

    with open(new_path, encoding="utf-8") as f:
        new_events = parse_events(f.read())

    added_uids = new_events.keys() - old_events.keys()
    added = [new_events[uid] for uid in added_uids]

    summary = format_summary(added)

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        with open(step_summary_path, "a", encoding="utf-8") as f:
            f.write(summary)
    else:
        print(summary)


if __name__ == "__main__":
    main()
