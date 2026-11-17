"""Дедлайны СДО из ICS-фида Moodle.

Вход: ссылка экспорта календаря (`~/.config/tusur/calendar.url`, права 600).
Выход: state (для детекта изменений), diff.json (что изменилось) и
`deadlines.md` / `deadlines.json` — вход для планировщика и `math-solver`.

Фиксы Moodle, из-за которых фид нельзя разбирать «наивно»:
  * строки свёрнуты `\\r\\n` + **таб** (иногда таб и пробел), а не только пробелом;
  * время в UTC, `TZID` в фиде не пишется — переводим в Asia/Tomsk (+0700);
  * `DTSTART == DTEND`: событие фида — момент срока, а не интервал;
  * текст задания уже в LaTeX, `\\n` экранированы.

Ссылка в файле может быть снята из любого окна экспорта СДО (по умолчанию там
`preset_what=user&preset_time=weeknow` — это пустой фид). Рабочее окно
`all` + `recentupcoming` ставится здесь принудительно.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tomsk")
UA = "tusur-assistant/1.0 (personal deadlines feed)"
DEFAULT_URL_FILE = "~/.config/tusur/calendar.url"
DEFAULT_STATE = "deadlines-state.json"
DEFAULT_DIFF = "diff.json"
DEFAULT_CACHE = "cache/feed.ics"
DEFAULT_MD = "deadlines.md"
DEFAULT_JSON = "deadlines.json"

PRESETS = {"preset_what": "all", "preset_time": "recentupcoming"}


@dataclass
class Deadline:
    uid: str
    summary: str
    start: datetime | date
    end: datetime | date | None = None
    categories: list[str] = field(default_factory=list)
    description: str = ""
    last_modified: str | None = None

    @property
    def subject(self) -> str:
        return self.categories[0] if self.categories else ""

    @property
    def hash(self) -> str:
        """План: hash(dtstart+summary). Даты — в ISO, чтобы сдвиг ловился."""
        payload = f"{_iso(self.start)}|{self.summary}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def to_json(self) -> dict:
        return {
            "uid": self.uid,
            "summary": self.summary,
            "subject": self.subject,
            "categories": self.categories,
            "start": _iso(self.start),
            "end": _iso(self.end) if self.end else None,
            "start_tomsk": _fmt(self.start),
            "description": self.description,
        }


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def _fmt(value: datetime | date | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.astimezone(TZ).strftime("%d.%m.%Y %H:%M")
    return value.strftime("%d.%m.%Y")


# --- ссылка -------------------------------------------------------------

def load_url(path: str = DEFAULT_URL_FILE) -> str:
    full = os.path.expanduser(path)
    try:
        with open(full, encoding="utf-8") as fh:
            url = fh.read().strip()
    except FileNotFoundError:
        raise SystemExit(f"нет файла ссылки {full} — положить ссылку экспорта СДО")
    if not url:
        raise SystemExit(f"пустой файл ссылки {full}")
    return with_presets(url)


def with_presets(url: str) -> str:
    """Принудительно рабочее окно экспорта (user/weeknow отдаёт пустой фид)."""
    parts = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query.update(PRESETS)
    return urllib.parse.urlunparse(parts._replace(query=urllib.parse.urlencode(query)))


def masked(url: str) -> str:
    """URL без authtoken — для логов и сообщений."""
    parts = urllib.parse.urlparse(url)
    query = [(k, "***" if k == "authtoken" else v)
             for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)]
    return urllib.parse.urlunparse(parts._replace(query=urllib.parse.urlencode(query)))


# --- загрузка -----------------------------------------------------------

def fetch(url: str, cache_path: str | None = None, *, from_cache: bool = False,
          delay: float = 2.5, retries: int = 2) -> str:
    if cache_path and from_cache:
        if not os.path.exists(cache_path):
            raise SystemExit(f"нет кэша {cache_path}")
        with open(cache_path, encoding="utf-8", newline="") as fh:
            return fh.read()
    last: Exception | None = None
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(delay * (2 ** attempt))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", "replace")
            if cache_path:
                os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
                with open(cache_path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(raw)
            return raw
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            print(f"  ! {masked(url)}: {exc}", file=sys.stderr)
    raise SystemExit(f"не удалось получить фид: {last}")


# --- разбор ICS ---------------------------------------------------------

def unfold(raw: str) -> str:
    """Разворот свёрнутых строк: CRLF + один пробел или таб (Moodle — таб)."""
    out = []
    for line in raw.splitlines():
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return "\n".join(out)


def _split_line(line: str) -> tuple[str, dict[str, str], str]:
    """`NAME;PARAM=VAL:"a:b":value` → (NAME, params, value)."""
    quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            quote = not quote
        elif ch == ":" and not quote:
            head, value = line[:i], line[i + 1:]
            break
    else:
        return line.strip().upper(), {}, ""
    name, *raw_params = head.split(";")
    params: dict[str, str] = {}
    for item in raw_params:
        key, _, val = item.partition("=")
        params[key.strip().upper()] = val.strip().strip('"')
    return name.strip().upper(), params, value


def unescape(value: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append("\n" if nxt in "nN" else nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_datetime(value: str, params: dict[str, str]) -> datetime | date:
    value = value.strip()
    if params.get("VALUE") == "DATE" or (len(value) == 8 and value.isdigit()):
        return datetime.strptime(value, "%Y%m%d").date()
    utc = value.endswith("Z")
    if utc:
        value = value[:-1]
    parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
    if utc:
        return parsed.replace(tzinfo=timezone.utc).astimezone(TZ)
    tzid = params.get("TZID")
    if tzid:
        try:
            return parsed.replace(tzinfo=ZoneInfo(tzid)).astimezone(TZ)
        except Exception:  # неизвестная зона — считаем томским временем
            pass
    return parsed.replace(tzinfo=TZ)


def parse(raw: str) -> list[Deadline]:
    text = unfold(raw)
    events: list[Deadline] = []
    block: dict[str, tuple[dict[str, str], str]] | None = None
    for line in text.split("\n"):
        if not line.strip():
            continue
        if line.strip().upper() == "BEGIN:VEVENT":
            block = {}
            continue
        if line.strip().upper() == "END:VEVENT":
            if block is not None:
                events.append(_build(block))
            block = None
            continue
        if block is None:
            continue
        name, params, value = _split_line(line)
        block.setdefault(name, (params, value))
    return sorted(events, key=lambda e: (_iso(e.start) or ""))


def _build(block: dict[str, tuple[dict[str, str], str]]) -> Deadline:
    def get(name: str) -> tuple[dict[str, str], str]:
        return block.get(name, ({}, ""))

    uid = unescape(get("UID")[1]).strip()
    summary = unescape(get("SUMMARY")[1]).strip()
    start = parse_datetime(get("DTSTART")[1], get("DTSTART")[0])
    end_raw = get("DTEND")[1]
    end = parse_datetime(end_raw, get("DTEND")[0]) if end_raw else None
    categories = [c.strip() for c in unescape(get("CATEGORIES")[1]).split(",") if c.strip()]
    return Deadline(
        uid=uid,
        summary=summary,
        start=start,
        end=end,
        categories=categories,
        description=unescape(get("DESCRIPTION")[1]).strip(),
        last_modified=get("LAST-MODIFIED")[1] or None,
    )


# --- состояние и дифф ---------------------------------------------------

def update_state(events: list[Deadline], state_path: str) -> dict:
    state: dict[str, dict] = {}
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
    diff: dict[str, list] = {"new": [], "changed": [], "gone": []}
    seen: set[str] = set()
    for ev in events:
        seen.add(ev.uid)
        prev = state.get(ev.uid)
        if prev is None:
            state[ev.uid] = {"hash": ev.hash, "summary": ev.summary,
                             "start": _iso(ev.start)}
            diff["new"].append({"uid": ev.uid, "summary": ev.summary,
                                "subject": ev.subject, "start": _iso(ev.start),
                                "start_tomsk": _fmt(ev.start)})
            continue
        if prev.get("hash") != ev.hash:
            diff["changed"].append({
                "uid": ev.uid,
                "summary": ev.summary,
                "subject": ev.subject,
                "was": {"summary": prev.get("summary"), "start": prev.get("start"),
                        "start_tomsk": _fmt(_parse_iso(prev.get("start")))},
                "now": {"summary": ev.summary, "start": _iso(ev.start),
                        "start_tomsk": _fmt(ev.start)},
            })
            prev.update(hash=ev.hash, summary=ev.summary, start=_iso(ev.start))
    for uid, prev in state.items():
        if uid in seen:
            continue
        diff["gone"].append({"uid": uid, "summary": prev.get("summary"),
                             "start": prev.get("start"),
                             "start_tomsk": _fmt(_parse_iso(prev.get("start")))})
    state = {uid: state[uid] for uid in sorted(state) if uid in seen}
    return {"state": state, "diff": diff}


def _parse_iso(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def diff_is_empty(diff: dict) -> bool:
    return not any(diff.get(k) for k in ("new", "changed", "gone"))


# --- артефакты ----------------------------------------------------------

def render_markdown(events: list[Deadline], generated: datetime,
                    diff: dict | None = None) -> str:
    lines = [
        "# Дедлайны СДО (сроки закрытия)",
        "",
        f"Обновлено: {generated.astimezone(TZ).strftime('%d.%m.%Y %H:%M')} (Asia/Tomsk). "
        f"Событий: {len(events)}.",
        "Источник — ICS-фид СДО. Время переведено в Томск, текст задания приведён как есть "
        "(формулы уже в LaTeX).",
    ]
    if diff and not diff_is_empty(diff):
        lines += ["", "## Изменения с прошлого прогона", ""]
        for item in diff.get("new", []):
            lines.append(f"- новое: {item['subject']} — {item['summary']} "
                         f"(срок {item['start_tomsk']})")
        for item in diff.get("changed", []):
            lines.append(f"- перенос: {item['summary']}: "
                         f"{item['was']['start_tomsk']} → {item['now']['start_tomsk']}")
        for item in diff.get("gone", []):
            lines.append(f"- снято: {item['summary']} (был срок {item['start_tomsk']})")
    lines += ["", "## Сроки", ""]
    for ev in events:
        lines.append(f"### {_fmt(ev.start)} — {ev.summary}")
        lines.append(f"- предмет: {ev.subject or '—'}")
        lines.append(f"- uid: `{ev.uid}`")
        if ev.description:
            lines.append("")
            lines.append(ev.description)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(events: list[Deadline], generated: datetime) -> str:
    payload = {
        "generated": generated.astimezone(TZ).isoformat(),
        "timezone": "Asia/Tomsk",
        "source": "sdo.tusur.ru calendar feed",
        "count": len(events),
        "deadlines": [ev.to_json() for ev in events],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


# --- CLI ----------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Дедлайны СДО → state/diff/deadlines")
    ap.add_argument("--fixture", help="локальный .ics вместо сети")
    ap.add_argument("--url-file", default=DEFAULT_URL_FILE)
    ap.add_argument("--cache", default=DEFAULT_CACHE, help="файл кэша фида")
    ap.add_argument("--from-cache", action="store_true", help="не ходить в сеть")
    ap.add_argument("--state", default=DEFAULT_STATE)
    ap.add_argument("--diff", default=DEFAULT_DIFF)
    ap.add_argument("--out", default=DEFAULT_MD)
    ap.add_argument("--json-out", default=DEFAULT_JSON)
    ap.add_argument("--delay", type=float, default=2.5)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.fixture:
        with open(args.fixture, encoding="utf-8", newline="") as fh:
            raw = fh.read()
        source = f"фикстура {args.fixture}"
    else:
        url = load_url(args.url_file)
        if not args.quiet:
            print(f"фид: {masked(url)}")
        raw = fetch(url, args.cache, from_cache=args.from_cache, delay=args.delay)
        source = args.cache if args.from_cache else "sdo.tusur.ru"

    events = parse(raw)
    if not events:
        raise SystemExit("в фиде нет ни одного VEVENT — проверь окно экспорта "
                         "(preset_what=all, preset_time=recentupcoming)")

    result = update_state(events, args.state)
    state, diff = result["state"], result["diff"]
    generated = datetime.now(TZ)

    _write(args.state, json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write(args.diff, json.dumps(diff, ensure_ascii=False, indent=2) + "\n")
    _write(args.out, render_markdown(events, generated, diff))
    _write(args.json_out, render_json(events, generated))

    if not args.quiet:
        print(f"источник: {source}; событий: {len(events)}")
        print(f"дифф: new {len(diff['new'])}, changed {len(diff['changed'])}, "
              f"gone {len(diff['gone'])}")
        for item in diff["new"]:
            print(f"  + {item['start_tomsk']} {item['subject']}: {item['summary'][:60]}")
        for item in diff["changed"]:
            print(f"  ~ {item['summary'][:60]}: "
                  f"{item['was']['start_tomsk']} → {item['now']['start_tomsk']}")
        for item in diff["gone"]:
            print(f"  - {item['summary'][:60]}")
        print(f"записано: {args.out}, {args.json_out}, {args.state}, {args.diff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
