# Текущий стек и состояние

Состояние на **2026-11-17, вечер**. Здесь только то, что фактически установлено и
проверено; замыслы — в `idea-and-architecture.md`, порядок работ — в
`implementation-plan.md`, доказательства — в `verified-facts.md`.

## 1. Машина и окружение

| Что | Значение |
|---|---|
| ОС | Arch Linux, хост `BTW`, пользователь `blesk` |
| Рабочий каталог проекта | `~/opencode/tusur-assistent` (переименован из `tusur-schedule`) |
| Docker | 29.9.3, compose 5.7.1; `docker.service` **enabled + active** |
| Tailscale | интерфейс `tailscale0`, адрес **100.121.145.104** |
| Python | 3.13, есть `bs4 4.15.0`, `pyyaml 6.0.3`; нет `actionlint`, `yq` |
| Документы | `pdftotext`, `pandoc`, `tesseract` (OCR), `jq` |
| Прокси | нет ни `caddy`, ни `nginx`, ни `traefik` → TLS и публичного домена нет |
| Диск | 114 ГБ свободно |
| VPN | AmneziaWG включался и мешал доступу к ТУСУРу; выключен 2026-11-17 |

## 2. Vikunja (задачи)

| Параметр | Значение |
|---|---|
| Версия | **v2.8.0** |
| Запуск | `docker run` вручную, контейнер `laughing_yonath`, образ без тега (`vikunja/vikunja` = latest) |
| Порт | `0.0.0.0:3456` → `3456/tcp` (слушает все интерфейсы) |
| Данные | SQLite `/db/vikunja.db` ← bind `./db`; вложения ← bind `./files` |
| Политика рестарта | `unless-stopped` (поставлена `docker update`); при пересборке контейнера сбросится |
| `VIKUNJA_SERVICE_PUBLICURL` | `http://localhost:3456/` — **не подходит для телефона**, надо Tailscale-адрес |
| Регистрация | открыта; создан пользователь **Blesk** (id 1), проект `Inbox` (id 1) |
| Возможности | `caldav_enabled: true`, вложения, link sharing, TOTP включён |
| Лицензия/Pro | ключа нет, Pro-фичи отключены (для нас не нужны) |

Задачи в интерфейсе: `http://localhost:3456/`.

## 3. MCP Vikunja (доступ агента к задачам)

| Параметр | Значение |
|---|---|
| Конфиг | `~/.config/opencode/opencode.jsonc`, секция `mcp.servers.vikunja` (файл права **600**, бэкап `opencode.jsonc.bak-vikunja`) |
| Тип | `remote`, streamable HTTP |
| URL | `http://127.0.0.1:3456/api/v2/mcp` |
| Авторизация | `Authorization: Bearer tk_…` (токен из Settings → MCP), длина 43 |
| Проверено | `initialize` → `HTTP 200` (SSE, `protocolVersion 2025-06-18`); `tools/list` → **27 инструментов**; `projects_list` → `Inbox` |
| Инструменты | `projects_*`, `tasks_*`, `labels_*`, `task_assignees_*`, `task_comments_*`, `users_search`, `filter_syntax`, `find_action`/`do_action` |
| Особенности | описания по умолчанию HTML (для markdown — `format: "markdown"`); фильтры через `&&`/`||`; `find_action` дотягивает уведомления, `project_views`, связи задач |

Токен в открытом виде в конфиге (единственный экземпляр, машина личная). При
переезде на env — `{env:VIKUNJA_MCP_TOKEN}` и переменная в профиле оболочки.

## 4. CalDAV Vikunja (телефон)

| Параметр | Значение |
|---|---|
| Базовый путь | **`/dav/`** (`http://100.121.145.104:3456/dav/principals/Blesk/`) |
| Не работает | `/api/v1/dav/…` → 404 (в документации Vikunja путь старый) |
| Токен | **ещё не создан**; MCP-токен для CalDAV не подходит (проверено: `PROPFIND` → Unauthorized) |
| Рабочие клиенты (docs Vikunja) | **Tasks.org**, OpenTasks + DAVx⁵, Evolution, Korganizer, Apple Reminders (iOS, 2.2.0+) |
| Нерабочий | Thunderbird 68 |
| Ограничения CalDAV | канбан-колонки и вложения не синхронизируются; HTML-описания приезжают текстом |
| Напоминания | держать в одном месте — иначе дубли Vikunja + клиент |

## 5. GitHub и публикация `.ics`

| Параметр | Значение |
|---|---|
| Аккаунт | **Z0DEN** |
| Репозиторий | `Z0DEN/tusur-schedule` — **public**, default `main`, пока пустой (size 0) |
| Доступ | deploy key `~/.ssh/z0den-tusur` (ed25519, без пароля, 600), алиас `Host github-z0den`, `IdentitiesOnly yes`; в GitHub должен быть включён **Allow write access** |
| Remote | `git@github-z0den:Z0DEN/tusur-schedule.git` |
| Локальные коммиты | **не запушены** (число — `git rev-list --count HEAD`) |
| Pages | не включён (`has_pages: false`) |
| Сборка | **GitHub Actions** (решение пользователя): workflow в облаке, локального `push` нет |
| Workflow | **ещё не создан** — `.github/` в проекте отсутствует |
| Секреты | authtoken фида СДО — в `Settings → Secrets`, в файлах не хранится |
| Личный календарь | Google Calendar, способ — секретный iCal-адрес (только чтение); адрес не получен, работа отложена |
| Календарный вид задач | в Vikunja нет: только `list`, `gantt`, `table`, `kanban`; `VEVENT` не поддерживается |
| Поля задачи | своих полей нет; в схеме `Task.json` нет `updated_by` — автор правки не определяется, см. `docs/vikunja-integration.md` |
| Изменения задач | опрос по `updated` (проверено); вебхуки через API-токен → `401`, только UI |
| Оценки трудоёмкости | метка `est-3h` из лестницы `est-*`; строка в описании — резерв |
| Планирование задач | **ИИ раз в сутки** (`opencode run --agent tusur`): обогащение задач через Vikunja MCP, слоты — только через `plan_apply` (наш MCP `tusur`); не создано |
| Проверено облако? | **нет**: неизвестно, пускает ли `timetable.tusur.ru` IP раннеров (Azure); проверяется первым `workflow_dispatch` |
| Старый ключ | блок `Host github.com` ссылается на отсутствующий `matvey-github`; не мешает, push идёт через алиас |

## 6. Проект `tusur-assistent`

```
AGENTS.md                  правила и карта проекта
docs/idea-and-architecture.md
docs/implementation-plan.md
docs/verified-facts.md
docs/stack.md              этот файл
parser.py                  страница группы → Lesson[] (мобильные таблицы + модалки)
ics.py                     Lesson[] → iCalendar (VTIMEZONE +0700, VALARM, UID/SEQUENCE)
main.py                    CLI: --fixture / --faculty / --weeks-ahead / --from-cache, кэш, паузы
requirements.txt           beautifulsoup4
.gitignore                 cache/, state.json, diff.json, fixtures/, db/, files/, *.url
```

Git: ветка `main`, рабочее дерево чистое, ничего не запушено.

## 7. Чего ещё нет (важно не забыть)

- Workflow `.github/workflows/update.yml` — не создан; генератор ещё не умеет
  `--state-from` (SEQUENCE из закоммиченного `.ics`).
- `deadlines.ics` / `schedule-735-1.ics` в репозитории — файлов пока нет.
- Парсера фида СДО (`feed.py`) — нет.
- CalDAV-токена и проверки синхронизации с телефоном — нет.
- Compose-файла, тега образа и Tailscale-URL — нет.
- HTTPS и обратного прокси — нет (и не планируется, пока хватает Tailscale).
- Локальный `systemd`-таймер — не создан; по решению от 2026-11-17 он только
  резерв на случай, если облачный запуск упрётся в блокировку IP.
- Сессии в СДО (файлы лекций) — нет.
