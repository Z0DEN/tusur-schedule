"""Сборка .ics расписания группы с timetable.tusur.ru.

Режимы:
  python3 main.py --group 735-1 --faculty fb --out schedule-735-1.ics
  python3 main.py --fixture fixtures/735-1.html --group 735-1 --out /tmp/test.ics
  python3 main.py --group 735-1 --faculty fb --from-cache --out schedule-735-1.ics

Вежливость к сайту: не больше одного запроса раз в --delay секунд (по умолчанию
2.5), повторы с паузой, локальный кэш HTML — повторная сборка без сети.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request

from ics import build_ics
from parser import Lesson, WeekInfo, parse_page

BASE = "https://timetable.tusur.ru"
UA = "tusur-schedule/1.0 (personal schedule feed; +https://github.com/)"


def fetch(url: str, cache_path: str | None, delay: float, retries: int = 2) -> str:
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            return fh.read()
    last: Exception | None = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(delay * (2 ** attempt))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Language": "ru-RU,ru"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", "replace")
            if cache_path:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as fh:
                    fh.write(html)
            return html
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            print(f"  ! {url}: {exc}", file=sys.stderr)
    raise SystemExit(f"не удалось получить {url}: {last}")


def collect(group: str, faculty: str, weeks_ahead: int, cache_dir: str,
            delay: float, from_cache: bool) -> tuple[list[Lesson], list[WeekInfo]]:
    base_url = f"{BASE}/faculties/{faculty}/groups/{group}"
    base_cache = os.path.join(cache_dir, f"{group}-base.html")
    if from_cache and not os.path.exists(base_cache):
        raise SystemExit(f"нет кэша {base_cache}")
    html = fetch(base_url, base_cache, delay)
    page = parse_page(html, group)
    if not page.weeks:
        raise SystemExit("на странице не найдено ни одной недели — изменилась разметка?")

    # Первая страница без ?week_id показывает текущую неделю.
    lessons: list[Lesson] = list(page.lessons)
    have = {l.lesson_id for l in lessons}

    starts = sorted(page.weeks, key=lambda w: w.starts)
    idx = next((i for i, w in enumerate(starts)
                if w.week_id == page.current_week_id), 0)
    wanted = starts[idx: idx + weeks_ahead + 1]
    print(f"{group}: недель на сайте {len(page.weeks)}, берём {len(wanted)} "
          f"(текущая {page.current_week_id} — {len(lessons)} пар)")

    for week in wanted:
        if week.week_id == page.current_week_id:
            continue
        url = f"{base_url}?week_id={week.week_id}"
        cache = os.path.join(cache_dir, f"{group}-{week.week_id}.html")
        if from_cache and not os.path.exists(cache):
            continue
        time.sleep(delay)
        wpage = parse_page(fetch(url, cache, delay), group)
        fresh = [l for l in wpage.lessons if l.lesson_id not in have]
        have.update(l.lesson_id for l in fresh)
        lessons += fresh
        print(f"  неделя {week.number} ({week.parity}, с {week.starts}): +{len(fresh)}")

    return lessons, page.weeks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True)
    ap.add_argument("--faculty", help="слаг факультета в URL (fb, fvs, iret, …)")
    ap.add_argument("--weeks-ahead", type=int, default=4)
    ap.add_argument("--fixture", help="локальный HTML вместо сети")
    ap.add_argument("--out", default=None)
    ap.add_argument("--cache-dir", default="cache")
    ap.add_argument("--state", default="state.json")
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--from-cache", action="store_true")
    args = ap.parse_args()

    out = args.out or f"schedule-{args.group}.ics"

    if args.fixture:
        with open(args.fixture, encoding="utf-8") as fh:
            page = parse_page(fh.read(), args.group)
        lessons = page.lessons
        print(f"{args.group}: фикстура, пар {len(lessons)}, недель в списке {len(page.weeks)}")
    else:
        if not args.faculty:
            raise SystemExit("нужен --faculty (например fb для 735-1)")
        lessons, _ = collect(args.group, args.faculty, args.weeks_ahead,
                             args.cache_dir, args.delay, args.from_cache)

    ics = build_ics(lessons, args.group, state_path=args.state)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write(ics)
    print(f"готово: {out} — событий {len(lessons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
