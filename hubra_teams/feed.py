"""Fixture feeds: fetch a league's iCal calendar and read its matches.

Leagues publish match schedules as iCal (Swiss football, unihockey, handball
and volleyball federations all offer a calendar link per team). Only public
https hosts are fetched, so a coach can't point the server at its own
network (TEAMS_FEED_ALLOW_PRIVATE=1 lifts that for a local test server).
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

LIMIT = 2 * 1024 * 1024
TIMEOUT = 15


class FeedError(Exception):
    """Shown to the coach."""


def normalise(url: str) -> str:
    url = (url or "").strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://") :]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        raise FeedError("The calendar link must start with https:// or webcal://")
    if len(url) > 500:
        raise FeedError("The calendar link is too long")
    return url


def _check_host(url: str) -> None:
    if os.environ.get("TEAMS_FEED_ALLOW_PRIVATE") == "1":
        return
    parsed = urllib.parse.urlparse(url)
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except OSError as exc:
        raise FeedError(f"{parsed.hostname} can't be found") from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise FeedError(f"{parsed.hostname} is not a public address")


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_host(normalise(newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str) -> str:
    url = normalise(url)
    _check_host(url)
    req = urllib.request.Request(
        url, headers={"User-Agent": "Hubra Teams", "Accept": "text/calendar"}
    )
    opener = urllib.request.build_opener(_CheckedRedirects)
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            data = resp.read(LIMIT + 1)
    except urllib.error.HTTPError as exc:
        raise FeedError(f"The calendar server answered HTTP {int(exc.code)}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FeedError("The calendar server can't be reached") from exc
    if len(data) > LIMIT:
        raise FeedError("The calendar is larger than 2 MB")
    text = data.decode("utf-8", errors="replace")
    if "BEGIN:VCALENDAR" not in text:
        raise FeedError("That link is not an iCal calendar")
    return text


# ── Parsing ──────────────────────────────────────────────────────────────────


@dataclass
class FeedEvent:
    uid: str
    summary: str
    starts_at: datetime
    location: str | None
    description: str | None
    cancelled: bool


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _when(params: dict[str, str], value: str, zone: ZoneInfo) -> datetime | None:
    value = value.strip()
    try:
        if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
            return datetime.combine(
                date(int(value[:4]), int(value[4:6]), int(value[6:8])), time(0, 0)
            )
        moment = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    if value.endswith("Z"):
        return (
            moment.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone).replace(tzinfo=None)
        )
    tzid = params.get("TZID")
    if tzid:
        try:
            return (
                moment.replace(tzinfo=ZoneInfo(tzid))
                .astimezone(zone)
                .replace(tzinfo=None)
            )
        except Exception:  # noqa: BLE001 - an unknown zone is read as local
            return moment
    return moment


def parse(text: str, zone: ZoneInfo) -> list[FeedEvent]:
    events: list[FeedEvent] = []
    current: dict | None = None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current and current.get("uid") and current.get("start"):
                events.append(
                    FeedEvent(
                        uid=current["uid"][:300],
                        summary=(current.get("summary") or "")[:200],
                        starts_at=current["start"],
                        location=(current.get("location") or None),
                        description=(current.get("description") or None),
                        cancelled=current.get("status") == "CANCELLED",
                    )
                )
            current = None
            continue
        if current is None or ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, *rest = head.split(";")
        params = {}
        for part in rest:
            if "=" in part:
                k, v = part.split("=", 1)
                params[k.upper()] = v.strip('"')
        name = name.upper()
        if name == "UID":
            current["uid"] = value.strip()
        elif name == "SUMMARY":
            current["summary"] = _unescape(value)
        elif name == "LOCATION":
            current["location"] = _unescape(value)[:300]
        elif name == "DESCRIPTION":
            current["description"] = _unescape(value)[:2000]
        elif name == "STATUS":
            current["status"] = value.strip().upper()
        elif name == "DTSTART":
            current["start"] = _when(params, value, zone)
    return events


_SIDES = re.compile(r"\s+(?:-|–|—|vs\.?|gegen|:)\s+", re.IGNORECASE)


def split_summary(summary: str, our_name: str | None) -> tuple[str, bool | None]:
    """ "FC Muster - SC Gegner" → ("SC Gegner", True) when we are FC Muster."""
    parts = _SIDES.split(summary, maxsplit=1)
    if len(parts) != 2 or not our_name:
        return summary, None
    ours = our_name.strip().lower()
    left, right = parts[0].strip(), parts[1].strip()
    # Leagues add the competition after a comma or in brackets.
    right = re.split(r"\s*[,(\[]", right, maxsplit=1)[0].strip() or right
    if ours and ours in left.lower():
        return right, True
    if ours and ours in right.lower():
        return left, False
    return summary, None
