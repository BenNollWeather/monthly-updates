"""AP style dates for plot text.

Months used with a day are abbreviated Jan., Feb., Aug., Sept., Oct., Nov.,
and Dec. March, April, May, June, and July stay spelled out. A month with a
year and no day is spelled out and has no comma: January 2026. A full date
uses a comma: Sept. 6, 2026. No ordinals.

Axis labels that are only a month use the same abbreviations, because a
12-month axis cannot hold the spelled-out names.
"""

from __future__ import annotations

import re

_FULL = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_ABBR = (
    "",
    "Jan.",
    "Feb.",
    "March",
    "April",
    "May",
    "June",
    "July",
    "Aug.",
    "Sept.",
    "Oct.",
    "Nov.",
    "Dec.",
)
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_MONTH_RE = (
    r"January|February|March|April|June|July|August|September|October|"
    r"November|December|Sept|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)
_TOKEN = re.compile(
    rf"""
    (?P<iso_day>(?P<iy>(?:19|20)\d{{2}})-(?P<im>0[1-9]|1[0-2])-(?P<id>0[1-9]|[12]\d|3[01]))
    |(?P<iso_month>(?P<iym>(?:19|20)\d{{2}})-(?P<imm>0[1-9]|1[0-2])(?!-\d))
    |(?P<mdy>\b(?P<mdy_m>{_MONTH_RE})\.?\s+(?P<mdy_d>\d{{1,2}})(?:st|nd|rd|th)?,\s+(?P<mdy_y>(?:19|20)\d{{2}}))
    |(?P<my>\b(?P<my_m>{_MONTH_RE})\.?\s+(?P<my_y>(?:19|20)\d{{2}}))
    |(?P<md>\b(?P<md_m>{_MONTH_RE})\.?\s+(?P<md_d>\d{{1,2}})(?:st|nd|rd|th)?)
    """,
    re.IGNORECASE | re.VERBOSE,
)
_GAP = re.compile(r"\s*(?:-|–|—|to)\s*")
_MONTH_ONLY = re.compile(rf"^(?P<month>{_MONTH_RE})\.?$", re.IGNORECASE)


def ap_rewrite(text: str, *, tabular: bool = False) -> str:
    """Return text with recognized dates rewritten in AP style."""
    if not isinstance(text, str) or text == "":
        return text
    stripped = text.strip()
    month_only = _MONTH_ONLY.fullmatch(stripped)
    if month_only:
        month = _month_number(month_only.group("month"))
        label = _ABBR[month] if tabular else _FULL[month]
        lead = text[: len(text) - len(text.lstrip())]
        tail = text[len(text.rstrip()) :]
        return f"{lead}{label}{tail}"
    return _rewrite_tokens(text)


def _rewrite_tokens(text: str) -> str:
    matches = list(_TOKEN.finditer(text))
    if not matches:
        return text
    parts: list[str] = []
    cursor = 0
    index = 0
    while index < len(matches):
        current = matches[index]
        if index + 1 < len(matches):
            nxt = matches[index + 1]
            gap = text[current.end() : nxt.start()]
            if _GAP.fullmatch(gap):
                parts.append(text[cursor : current.start()])
                parts.append(_format_range(current, nxt))
                cursor = nxt.end()
                index += 2
                continue
        parts.append(text[cursor : current.start()])
        parts.append(_format_one(current))
        cursor = current.end()
        index += 1
    parts.append(text[cursor:])
    return "".join(parts)


def _month_number(name: str) -> int:
    return _MONTHS[name.lower().rstrip(".")]


def _parts(match: re.Match) -> tuple[int | None, int, int | None]:
    if match.group("iso_day"):
        return int(match.group("iy")), int(match.group("im")), int(match.group("id"))
    if match.group("iso_month"):
        return int(match.group("iym")), int(match.group("imm")), None
    if match.group("mdy"):
        return int(match.group("mdy_y")), _month_number(match.group("mdy_m")), int(match.group("mdy_d"))
    if match.group("my"):
        return int(match.group("my_y")), _month_number(match.group("my_m")), None
    return None, _month_number(match.group("md_m")), int(match.group("md_d"))


def _format_one(match: re.Match) -> str:
    year, month, day = _parts(match)
    if day is None and year is not None:
        return f"{_FULL[month]} {year}"
    if day is None:
        return _FULL[month]
    if year is None:
        return f"{_ABBR[month]} {day}"
    return f"{_ABBR[month]} {day}, {year}"


def _format_range(left: re.Match, right: re.Match) -> str:
    y1, m1, d1 = _parts(left)
    y2, m2, d2 = _parts(right)
    if d1 is None and d2 is None and y1 is not None and y2 is not None:
        if y1 == y2 and m1 == m2:
            return f"{_FULL[m1]} {y1}"
        if y1 == y2:
            return f"{_FULL[m1]}-{_FULL[m2]} {y1}"
        return f"{_FULL[m1]} {y1}-{_FULL[m2]} {y2}"
    if d1 is not None and d2 is not None and y1 is not None and y1 == y2:
        if m1 == m2:
            return f"{_ABBR[m1]} {d1}-{d2}, {y1}"
        return f"{_ABBR[m1]} {d1}-{_ABBR[m2]} {d2}, {y1}"
    if d1 is not None and d2 is not None and y1 is not None and y2 is not None:
        return f"{_ABBR[m1]} {d1}, {y1}-{_ABBR[m2]} {d2}, {y2}"
    return f"{_format_one(left)}-{_format_one(right)}"
