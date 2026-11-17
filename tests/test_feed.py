"""Тесты разбора ICS-фида дедлайнов на синтетической фикстуре.

Приватный фид СДО в репозиторий не попадает, поэтому проверяются свойства
формата Moodle: свёртка табом, экранирование, UTC → Томск, `VALUE=DATE`,
дифф `new/changed/gone`. Запуск: `python3 tests/test_feed.py`.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feed  # noqa: E402

HEADER = """BEGIN:VCALENDAR
METHOD:PUBLISH
VERSION:2.0
PRODID:-//Moodle Pty Ltd//NONSGML Moodle Version 2024100715.01//EN
"""

SAMPLE = HEADER + """BEGIN:VEVENT
UID:1001@sdo.tusur.ru
SUMMARY:Тест "Интерполяция" закрывается
DTSTART:20261123T130500Z
DTEND:20261123T130500Z
CATEGORIES:ЧМ
DESCRIPTION:Выполнить задание:\\n\\t* шаг один\\n\\t* формула [ x_{i} = \\\\frac{b_i}{a_{ii}} ]
BEGIN:VALARM
TRIGGER:-PT1D
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:1002@sdo.tusur.ru
SUMMARY:Лабораторная работа №1 - срок сдачи
DTSTART:20261206T165900Z
DTEND:20261206T165900Z
CATEGORIES:ЭиС 1
END:VEVENT
END:VCALENDAR
"""


def folded(text: str) -> str:
    """Свернуть длинные строки табом, как это делает Moodle."""
    out = []
    for line in text.splitlines():
        raw = line.encode("utf-8")
        if len(raw) <= 70:
            out.append(line)
            continue
        parts, cur = [], b""
        for ch in line:
            b = ch.encode("utf-8")
            if len(cur) + len(b) > 70:
                parts.append(cur)
                cur = b"\t"
            cur += b
        parts.append(cur)
        out.append(b"\r\n".join(parts).decode("utf-8"))
    return "\r\n".join(out) + "\r\n"


def test_parse() -> None:
    events = feed.parse(folded(SAMPLE))
    assert len(events) == 2, events
    first, second = events
    assert first.uid == "1001@sdo.tusur.ru"
    assert first.subject == "ЧМ"
    # UTC 13:05 → Томск 20:05
    assert first.start == datetime(2026, 11, 23, 20, 5, tzinfo=feed.TZ)
    assert first.start.tzinfo is not None
    # Свёртка табом развёрнута, переводы строк и LaTeX восстановлены
    assert "\n" in first.description
    assert "\\frac{b_i}{a_{ii}}" in first.description
    assert second.summary.startswith("Лабораторная")
    print("parse ok")


def test_value_date() -> None:
    value = feed.parse_datetime("20261206", {"VALUE": "DATE"})
    assert value == date(2026, 12, 6), value
    utc = feed.parse_datetime("20261206T165900Z", {})
    assert utc == datetime(2026, 12, 6, 23, 59, tzinfo=feed.TZ)
    print("datetime ok")


def test_url_presets() -> None:
    url = ("https://sdo.tusur.ru/calendar/export_execute.php"
           "?userid=1&authtoken=secret&preset_what=user&preset_time=weeknow")
    fixed = feed.with_presets(url)
    assert "preset_what=all" in fixed and "preset_time=recentupcoming" in fixed
    assert "authtoken=secret" in fixed
    assert "secret" not in feed.masked(fixed)
    print("presets ok")


def test_diff() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = os.path.join(tmp, "state.json")
        events = feed.parse(SAMPLE)
        first = feed.update_state(events, state)
        assert len(first["diff"]["new"]) == 2 and not first["diff"]["changed"]
        with open(state, "w", encoding="utf-8") as fh:
            json.dump(first["state"], fh)

        again = feed.update_state(events, state)
        assert feed.diff_is_empty(again["diff"]), again["diff"]

        shifted = SAMPLE.replace("20261206T165900Z", "20261207T165900Z")
        changed = feed.update_state(feed.parse(shifted), state)
        assert len(changed["diff"]["changed"]) == 1, changed["diff"]
        assert changed["diff"]["changed"][0]["uid"] == "1002@sdo.tusur.ru"

        gone = feed.update_state(feed.parse(SAMPLE.split("BEGIN:VEVENT")[0]
                                             + "END:VCALENDAR\r\n"), state)
        assert len(gone["diff"]["gone"]) == 2, gone["diff"]
    print("diff ok")


def test_markdown() -> None:
    events = feed.parse(SAMPLE)
    text = feed.render_markdown(events, datetime.now(feed.TZ))
    assert "### 23.11.2026 20:05" in text
    assert "предмет: ЭиС 1" in text
    payload = json.loads(feed.render_json(events, datetime.now(feed.TZ)))
    assert payload["count"] == 2 and payload["timezone"] == "Asia/Tomsk"
    print("render ok")


if __name__ == "__main__":
    test_parse()
    test_value_date()
    test_url_presets()
    test_diff()
    test_markdown()
    print("все тесты прошли")
