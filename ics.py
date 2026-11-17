"""Генератор iCalendar (.ics) из расписания ТУСУР.

Стабильные UID + SEQUENCE: календарь обновляет пары, а не дублирует их.
Время — Asia/Tomsk (UTC+7, без перехода на летнее время с 2014 года).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

from parser import KIND_SHORT, Lesson

PRODID = "-//tusur-schedule//RU"
ALARM_MINUTES = 30


def _esc(text: str) -> str:
    """Экранирование по RFC 5545."""
    return (text.replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Свёртка длинных строк: не больше 75 октетов на строку."""
    raw = line.encode("utf-8")
    if len(raw) <= 73:
        return line
    out, cur, cur_len = [], [], 0
    for ch in line:
        blen = len(ch.encode("utf-8"))
        if cur_len + blen > 73:
            out.append("".join(cur))
            cur, cur_len = [" "], 1
        cur.append(ch)
        cur_len += blen
    out.append("".join(cur))
    return "\r\n".join(out)


def _summary(lesson: Lesson) -> str:
    short = KIND_SHORT.get(lesson.kind.lower().strip(), lesson.kind or "Пара")
    return f"{short} {lesson.subject}".strip()


def _sequence(lesson: Lesson, state: dict) -> int:
    """Растёт только когда меняется содержимое пары."""
    digest = hashlib.sha1(lesson.payload().encode("utf-8")).hexdigest()
    prev = state.get(lesson.uid)
    if prev is None:
        state[lesson.uid] = {"hash": digest, "seq": 0}
        return 0
    if prev.get("hash") != digest:
        prev["seq"] = int(prev.get("seq", 0)) + 1
        prev["hash"] = digest
    return int(prev.get("seq", 0))


def build_ics(lessons: list[Lesson], group: str, state_path: str | None = None) -> str:
    state: dict = {}
    if state_path and os.path.exists(state_path):
        try:
            state = json.load(open(state_path, encoding="utf-8"))
        except (OSError, ValueError):
            state = {}

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Расписание {group}",
        "X-WR-TIMEZONE:Asia/Tomsk",
        # Томск: постоянный UTC+7, перехода нет.
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Tomsk",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0700",
        "TZOFFSETTO:+0700",
        "TZNAME:+07",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for lesson in sorted(lessons, key=lambda l: l.start):
        desc = [f"Вид занятия: {lesson.kind}"] if lesson.kind else []
        if lesson.teacher:
            desc.append(f"Преподаватель: {lesson.teacher}")
        if lesson.groups:
            desc.append(f"Группы: {lesson.groups}")
        if lesson.building:
            desc.append(f"Корпус: {lesson.building}")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{lesson.uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;TZID=Asia/Tomsk:{lesson.start:%Y%m%dT%H%M%S}",
            f"DTEND;TZID=Asia/Tomsk:{lesson.end:%Y%m%dT%H%M%S}",
            f"SUMMARY:{_esc(_summary(lesson))}",
        ]
        location = " ".join(x for x in (lesson.room, lesson.building.split(",")[0]) if x)
        if location:
            lines.append(f"LOCATION:{_esc(location)}")
        if desc:
            lines.append(f"DESCRIPTION:{_esc(chr(10).join(desc))}")
        seq = _sequence(lesson, state)
        lines += [
            f"SEQUENCE:{seq}",
            "STATUS:CONFIRMED",
            "TRANSP:OPAQUE",
            "BEGIN:VALARM",
            f"TRIGGER:-PT{ALARM_MINUTES}M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_esc(_summary(lesson))}",
            "END:VALARM",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    text = "\r\n".join(_fold(l) for l in lines) + "\r\n"

    if state_path:
        os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
        with open(state_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
    return text
