"""Парсер страницы расписания timetable.tusur.ru.

На вход — HTML страницы группы с ?week_id=N (или без него = текущая неделя).
На выход — список событий (пар) с абсолютными датами и временем.

Разметка сайта: на странице 7 таблиц `table.table-lessons`:
  * одна desktop-сетка (hidden-xs) — неудобна для разбора;
  * шесть mobile-таблиц (visible-xs), по одной на день: шапка «пн, 16 нояб.»,
    далее строки «08:50 10:25 | <пара>».
Парсим mobile-таблицы: они линейные и стабильные.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "ма": 5, "мая": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}

# Короткие метки видов занятий для SUMMARY.
KIND_SHORT = {
    "лекция": "ЛЕК",
    "практика": "ПРАК",
    "практическое занятие": "ПРАК",
    "лабораторная": "ЛАБ",
    "лабораторная работа": "ЛАБ",
    "семинар": "СЕМ",
    "курсовая работа": "КУРС",
    "курсовой проект": "КУРС",
    "зачет": "ЗАЧ",
    "зачёт": "ЗАЧ",
    "экзамен": "ЭКЗ",
    "консультация": "КОНС",
    "самостоятельная работа": "СРС",
}


@dataclass
class Lesson:
    lesson_id: str
    subject: str
    kind: str
    room: str
    building: str
    teacher: str
    groups: str
    start: datetime
    end: datetime
    course_links_url: str = ""

    @property
    def uid(self) -> str:
        return f"{self.lesson_id}-{self.start:%Y%m%dT%H%M}@timetable.tusur.ru"

    def payload(self) -> str:
        """Всё, что влияет на отображение: для детекта изменений и SEQUENCE."""
        return "|".join([
            self.subject, self.kind, self.room, self.building,
            self.teacher, f"{self.start:%Y%m%dT%H%M}", f"{self.end:%Y%m%dT%H%M}",
        ])


@dataclass
class WeekInfo:
    week_id: str
    number: int
    parity: str  # 'нечётная' | 'чётная'
    starts: date


@dataclass
class GroupPage:
    group: str
    weeks: list[WeekInfo] = field(default_factory=list)
    lessons: list[Lesson] = field(default_factory=list)
    current_week_id: str = ""


def parse_weeks(soup: BeautifulSoup) -> list[WeekInfo]:
    weeks: list[WeekInfo] = []
    for a in soup.select("ul.weeks li a"):
        m = re.search(r"week_id=(\d+)", a.get("href", ""))
        if not m:
            continue
        divs = a.find_all("div")
        if len(divs) < 2:
            continue
        head = divs[0].get_text(" ", strip=True)          # «1 нечётная»
        tail = divs[1].get_text(" ", strip=True)          # «с 31 августа 2026»
        num = re.search(r"\d+", head)
        parity = "чётная" if "чёт" in head.replace("нечёт", "") else "нечётная"
        dm = re.search(r"(\d{1,2})\s+([а-я]+)\s+(\d{4})", tail)
        if not (num and dm):
            continue
        weeks.append(WeekInfo(
            week_id=m.group(1),
            number=int(num.group()),
            parity=parity,
            starts=date(int(dm.group(3)), MONTHS[dm.group(2)[:3]], int(dm.group(1))),
        ))
    return weeks


def _resolve_year(day: int, month: int, week_start: date) -> date:
    """Год из шапки дня не указан: берём год начала недели, с поправкой на
    переход через новый год (неделя с 29 дек, день «2 янв»)."""
    candidate = date(week_start.year, month, day)
    if (candidate - week_start).days < -180:
        candidate = date(week_start.year + 1, month, day)
    elif (candidate - week_start).days > 180:
        candidate = date(week_start.year - 1, month, day)
    return candidate


def _split_lesson_cell(cell) -> list[dict]:
    """Достаёт пары из ячейки: бывает несколько (подгруппы)."""
    out: list[dict] = []
    for block in cell.select("div.training"):
        hidden = block.find("span", class_="hidden")
        abbr = block.find("abbr")
        disc = block.find("span", class_="discipline")
        kind_el = block.find("span", class_="kind")
        aud = block.find("span", class_="auditoriums")
        teacher_el = block.find("span", class_="group")

        room, building = "", ""
        if aud:
            link = aud.find("i") or aud.find("a")
            room = aud.get_text(" ", strip=True)
            if link and link.get("title"):
                building = link["title"]

        subject = ""
        if abbr:
            subject = abbr.get("title") or abbr.get_text(strip=True)
        elif disc:
            subject = disc.get_text(" ", strip=True)

        out.append({
            "lesson_id": hidden.get_text(strip=True) if hidden else "",
            "subject": subject,
            "kind": kind_el.get_text(" ", strip=True) if kind_el else "",
            "room": room,
            "building": building,
            "teacher": teacher_el.get_text(" ", strip=True) if teacher_el else "",
            "groups": "",
        })
    return out


def parse_lessons(soup: BeautifulSoup, week: WeekInfo | None) -> list[Lesson]:
    lessons: list[Lesson] = []
    tables = [t for t in soup.select("table.table-lessons")
              if "visible-xs" in (t.get("class") or [])]

    for table in tables:
        rows = table.select("tr")
        if not rows:
            continue
        # Шапка дня: первая строка, ячейка с «пн, 16 нояб.»
        head_text = rows[0].get_text(" ", strip=True)
        dm = re.search(r"(\d{1,2})\s+([а-я]{3,})", head_text)
        if not dm:
            continue
        day = int(dm.group(1))
        month = MONTHS[dm.group(2)[:3]]
        if week is None:
            day_date = None
        else:
            day_date = _resolve_year(day, month, week.starts)

        for row in rows[1:]:
            cells = row.find_all(["td", "th"], recursive=False)
            if len(cells) < 2:
                continue
            # первый столбец — время (в разных таблицах это th или td)
            times = []
            body = None
            for cell in cells:
                found = re.findall(r"\d{2}:\d{2}", cell.get_text(" ", strip=True))
                if len(found) >= 2 and not cell.select("div.training"):
                    times = found
                elif cell.select("div.training") or body is None:
                    body = cell
            if len(times) < 2 or body is None or day_date is None:
                continue
            start_t = datetime.strptime(times[0], "%H:%M").time()
            end_t = datetime.strptime(times[1], "%H:%M").time()
            for raw in _split_lesson_cell(body):
                if not raw["lesson_id"]:
                    continue
                lessons.append(Lesson(
                    start=datetime.combine(day_date, start_t),
                    end=datetime.combine(day_date, end_t),
                    **raw,
                ))
    return lessons


def _parse_modal(modal) -> dict:
    """Разбор модалки: там абсолютные дата/время, полное название, состав групп."""
    text = " ".join(modal.get_text(" ", strip=True).split())
    out: dict = {"course_links_url": modal.get("data-course-links-url") or ""}

    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    if m:
        out["date"] = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"Время проведения:\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", text)
    if m:
        out["times"] = (m.group(1), m.group(2))
    m = re.search(r"Вид занятия:\s*(.+?)\s+(?:Дата проведения|Время проведения)", text)
    if m:
        out["kind"] = m.group(1)
    m = re.search(r"Место проведения:\s*(.+?)\s+Преподаватель", text)
    if m:
        out["room"] = m.group(1)
    m = re.search(r"Преподаватель:\s*(.+?)\s+Группы", text)
    if m:
        out["teacher"] = m.group(1)
    m = re.search(r"Группы:\s*(.+?)\s+Ссылка на", text)
    if m:
        out["groups"] = m.group(1)
    m = re.match(r"(?:×\s*)?(.+?)\s+Вид занятия:", text)
    if m:
        out["subject"] = m.group(1)
    return out


def parse_page(html: str, group: str) -> GroupPage:
    soup = BeautifulSoup(html, "html.parser")
    weeks = parse_weeks(soup)

    modals: dict[str, dict] = {}
    for modal in soup.select("div.js-lesson-info-modal"):
        lid = modal.get("data-lesson-id", "")
        if lid and lid not in modals:
            modals[lid] = _parse_modal(modal)

    current: WeekInfo | None = None
    if weeks:
        today = date.today()
        current = next((w for w in weeks if w.starts <= today < w.starts + timedelta(days=7)), None)
        if current is None:
            current = min(weeks, key=lambda w: abs((w.starts - today).days))

    lessons = parse_lessons(soup, current)

    for lesson in lessons:
        info = modals.get(lesson.lesson_id, {})
        # Модалка — источник истины: там абсолютные дата и время.
        if "date" in info:
            d = info["date"]
            lesson.start = datetime.combine(d, lesson.start.time())
            lesson.end = datetime.combine(d, lesson.end.time())
        if "times" in info:
            s_t = datetime.strptime(info["times"][0], "%H:%M").time()
            e_t = datetime.strptime(info["times"][1], "%H:%M").time()
            base = lesson.start.date()
            lesson.start = datetime.combine(base, s_t)
            lesson.end = datetime.combine(base, e_t)
        for key in ("subject", "kind", "room", "teacher", "groups"):
            if info.get(key):
                setattr(lesson, key, info[key])
        if not lesson.groups:
            lesson.groups = f"гр. {group}"
        if info.get("course_links_url"):
            lesson.course_links_url = info["course_links_url"]

    # Если у пары из модалки есть корпус в title ссылки на аудиторию — он уже в building.
    return GroupPage(group=group, weeks=weeks, lessons=lessons,
                     current_week_id=current.week_id if current else "")
