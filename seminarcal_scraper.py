import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag
from ics import Calendar, Event

URL = "https://www.economics.utoronto.ca/index.php/index/research/seminars"
TORONTO_TZ = ZoneInfo("America/Toronto")
SERIES_TAG = "ECO_SEMINAR"
UID_NAMESPACE = uuid.UUID("b59e11d6-02b2-4d26-9e9b-4c233a33e313")


# ---------- Helpers ----------

def fetch_page(url: str) -> BeautifulSoup:
    """Fetch *url* and return a parsed BeautifulSoup object.

    Raises:
        requests.HTTPError: If the server returns a non-2xx status code.
    """
    resp = requests.get(url)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def safe_text(tag: Tag | None) -> str:
    """Return the stripped text content of *tag*, or an empty string if *tag* is None."""
    return tag.get_text(strip=True) if tag else ""


def parse_datetime_location(
    date_str: str,
) -> tuple[datetime, datetime, str] | tuple[None, None, None]:
    """Parse a seminar date/time/location string into structured components.

    Expected format::

        "Wednesday, October 15 2025 12:30–14:00, Rotman, room 147"

    Location strings are normalized:
        - ``"Max Gluskin House, room NNN"``  →  ``"GE NNN"``
        - ``"Rotman, room NNN"``             →  ``"RT NNN"``

    Args:
        date_str: Raw date/time/location string scraped from the seminar page.

    Returns:
        A ``(start_datetime, end_datetime, location)`` tuple on success, or
        ``(None, None, None)`` if *date_str* does not match the expected pattern.
    """
    pattern = (
        r"[A-Za-z]+,\s+([A-Za-z]+\s+\d{1,2}\s+\d{4})\s+"
        r"(\d{1,2}:\d{2})–(\d{1,2}:\d{2}),\s*(.*)"
    )
    m = re.match(pattern, date_str)
    if not m:
        return None, None, None

    date_part, start_time_str, end_time_str, location = m.groups()

    if location.startswith("Max Gluskin House, room"):
        location = location.replace("Max Gluskin House, room", "GE")
    elif location.startswith("Rotman, room"):
        location = location.replace("Rotman, room", "RT")

    date_obj = datetime.strptime(date_part, "%B %d %Y")
    start_dt = datetime.strptime(start_time_str, "%H:%M")
    end_dt = datetime.strptime(end_time_str, "%H:%M")

    start_datetime = datetime.combine(date_obj.date(), start_dt.time())
    end_datetime = datetime.combine(date_obj.date(), end_dt.time())

    return start_datetime, end_datetime, location


def extract_series_and_organizers(
    card: Tag,
) -> tuple[str, str, list[str]]:
    """Extract the seminar series name and organizer list from a card element.

    Looks for ``div.block`` elements whose text contains ``"Series:"`` or
    ``"Organizer(s):"``. If the series name appears in the organizer list it is
    removed to avoid duplication.

    Args:
        card: A ``div.card-body`` BeautifulSoup tag.

    Returns:
        A ``(series, organizers_string, organizer_list)`` tuple where
        *organizers_string* is a comma-joined version of *organizer_list*.
    """
    series = ""
    organizer_list: list[str] = []

    for block in card.find_all("div", class_="block"):
        block_text = block.get_text(" ", strip=True)

        if "Series:" in block_text:
            link = block.find("a")
            if link:
                series = link.get_text(strip=True)

        if "Organizer" in block_text:
            organizer_list = [a.get_text(strip=True) for a in block.find_all("a")]

    if series and series in organizer_list:
        organizer_list = [o for o in organizer_list if o != series]

    return series, ", ".join(organizer_list), organizer_list


# ---------- Parsing ----------

# Type alias for the seminar data dict
type SeminarDict = dict[str, str | datetime | bool | list[str] | None]


def parse_seminar_card(card: Tag) -> SeminarDict | None:
    """Parse a single ``div.card-body`` element into a seminar data dict.

    Cancellation is detected via a ``<s>`` (strikethrough) tag or an ``<i>``
    tag containing the word "cancelled" inside the speaker ``<h5>``. The title
    is prefixed with ``"CANCELLED: "`` when applicable.

    Args:
        card: A ``div.card-body`` BeautifulSoup tag.

    Returns:
        A dict with keys ``title``, ``speaker``, ``start``, ``end``,
        ``location``, ``series``, ``organizers``, ``speaker_link``,
        ``title_link``, ``cancelled``, and ``_organizer_list``, or ``None``
        if the card is missing required fields.
    """
    is_cancelled = False
    speaker = ""
    speaker_link = ""

    speaker_tag = card.find("h5")
    if isinstance(speaker_tag, Tag):
        if speaker_tag.find("s"):
            is_cancelled = True

        cancelled_i = speaker_tag.find("i")
        if isinstance(cancelled_i, Tag) and "cancel" in cancelled_i.get_text(strip=True).lower():
            is_cancelled = True

        speaker = re.sub(r"\bCancelled\b", "", speaker_tag.get_text(" ", strip=True), flags=re.I).strip()

        speaker_link_tag = speaker_tag.find("a")
        speaker_link = speaker_link_tag.get("href", "") if isinstance(speaker_link_tag, Tag) else ""

    title_tag = card.find("h6")
    title = title_tag.get_text(strip=True) if title_tag else ""
    title_link_tag = title_tag.find("a") if title_tag else None
    title_link = title_link_tag.get("href", "") if isinstance(title_link_tag, Tag) else ""

    if is_cancelled:
        title = f"CANCELLED: {title}"

    date_tag = card.find("span", style="font-weight:500")
    date_str = safe_text(date_tag if isinstance(date_tag, Tag) else None)
    if not date_str:
        print("Skipping item with no date:", title)
        return None

    start_dt, end_dt, location = parse_datetime_location(date_str)
    if not start_dt:
        print("Could not parse date format:", date_str)
        return None

    series, organizers, organizer_list = extract_series_and_organizers(card)

    seminar: SeminarDict = {
        "title": title,
        "speaker": speaker,
        "start": start_dt,
        "end": end_dt,
        "location": location,
        "series": series,
        "organizers": organizers,
        "speaker_link": speaker_link,
        "title_link": title_link,
        "cancelled": is_cancelled,
        "_organizer_list": organizer_list,
    }

    print(f"\n Seminar: {title} | {speaker} | {series} | {organizers}")
    print(f"          {start_dt} - {end_dt} | {location} | Cancelled: {is_cancelled}")

    return seminar


# ---------- Calendar building ----------

def add_seminar_event(cal: Calendar, seminar: SeminarDict) -> None:
    """Build an :class:`ics.Event` from *seminar* and add it to *cal*.

    Cancelled seminars are skipped. Event UIDs are deterministic (UUID v5)
    so that re-importing the calendar does not create duplicate events in
    clients that support ``UID``-based deduplication.

    The event description is formatted as HTML with bolded field labels and,
    where available, hyperlinks for the paper title and speaker profile.

    Args:
        cal: The :class:`ics.Calendar` to add the event to.
        seminar: A seminar dict as returned by :func:`parse_seminar_card`.
    """
    if seminar.get("cancelled", False):
        return

    start_value = seminar.get("start")
    end_value = seminar.get("end")
    if not isinstance(start_value, datetime) or not isinstance(end_value, datetime):
        return

    start_local = start_value.replace(tzinfo=TORONTO_TZ)
    end_local = end_value.replace(tzinfo=TORONTO_TZ)

    speaker_value = seminar.get("speaker", "")
    speaker_raw: str = speaker_value if isinstance(speaker_value, str) else ""
    inst_match = re.search(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)$", speaker_raw)
    institution = inst_match.group(1) if inst_match else ""
    speaker_clean = re.sub(r"\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)$", "", speaker_raw).strip()

    uid_string = (
        f"{start_value.isoformat()}|"
        f"{seminar.get('title_link') or seminar.get('title')}|"
        f"{seminar.get('speaker_link')}"
    )
    stable_uid = uuid.uuid5(UID_NAMESPACE, uid_string)

    title_part = (
        f"<b>Title:</b> <a href=\"{seminar['title_link']}\">{seminar['title']}</a>\n"
        if seminar.get("title_link")
        else f"<b>Title:</b> {seminar.get('title', '')}\n"
    )
    speaker_link_part = (
        f"<b>Speaker link:</b> {seminar['speaker_link']}\n"
        if seminar.get("speaker_link")
        else ""
    )

    event = Event()
    event.name = speaker_clean
    event.begin = start_local
    event.end = end_local
    location_value = seminar.get("location")
    event.location = location_value if isinstance(location_value, str) else None
    series_value = seminar.get("series")
    series_category = series_value if isinstance(series_value, str) else ""
    event.categories = {SERIES_TAG, series_category}
    event.uid = f"{SERIES_TAG}-{stable_uid}"
    event.description = (
        title_part
        + f"<b>Institution:</b> {institution}\n"
        + f"<b>Series:</b> {seminar.get('series', '')}\n"
        + f"<b>Organizers:</b> {seminar.get('organizers', '')}\n"
        + speaker_link_part
    )

    cal.events.add(event)


def build_calendar(seminars: list[SeminarDict]) -> Calendar:
    """Build and return an :class:`ics.Calendar` from a list of seminar dicts.

    Args:
        seminars: List of dicts as returned by :func:`parse_seminar_card`.

    Returns:
        A populated :class:`ics.Calendar` instance.
    """
    cal = Calendar()
    for seminar in seminars:
        add_seminar_event(cal, seminar)
    return cal


# ---------- Main ----------

def main() -> None:
    """Scrape the UofT Economics seminar page and write ``seminars.ics``.

    Fetches :data:`URL`, parses every ``div.card-body`` card, builds an iCal
    calendar, and writes it to ``seminars.ics`` in the current directory.
    """
    soup = fetch_page(URL)

    bodies = soup.find_all("div", class_="card-body")
    if bodies:
        # print(bodies[0].prettify())
        pass

    seminars: list[SeminarDict] = []
    for item in bodies:
        parsed = parse_seminar_card(item)
        if parsed:
            seminars.append(parsed)

    print(f"\nTotal seminars parsed: {len(seminars)}")

    cal = build_calendar(seminars)

    with open("seminars.ics", "w", encoding="utf-8") as f:
        f.write(cal.serialize())

    print("💾 Calendar saved to seminars.ics")


if __name__ == "__main__":
    main()