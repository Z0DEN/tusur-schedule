# Журнал проверок

Только то, что реально проверено запросом или запуском. Формат: что проверяли,
чем, что получили. Обновлять по мере работы, старые записи не переписывать.

## 2026-11-17

### Экосистема ТУСУРа

| Проверка | Команда | Результат |
|---|---|---|
| СДО — это Moodle | `curl https://sdo.tusur.ru/login/index.php` | форма `username/password` + `logintoken`, кнопка «Вход через кабинет ТУСУРа» → `profile.tusur.ru/users/sign_in?redirect_url=…/auth/edu/` |
| Версия Moodle | `PRODID` в фиде календаря | `Moodle Version 2024100715` → 4.5 |
| SSO-провайдер | `curl https://profile.tusur.ru/users/sign_in` | Devise-форма `/users/sign_in`, поля `user[email]`, `user[password]`, **капчи нет** |
| Другие системы | `curl` по хостам | `ocenka.tusur.ru` (журнал успеваемости), `attendance.tusur.ru`, `edu.tusur.ru` — отдельные приложения с `sign_in`; `storage` — Basic 401; `cloud` → `/login` |

### СДО: доступ к API и календарю

| Проверка | Команда | Результат |
|---|---|---|
| `login/token.php` живой | `POST login/token.php` без параметров | `missingparam: username` |
| Порядок проверок в `token.php` | `POST` с подставным сервисом `zzz_nosuchservice` | тоже `invalidlogin` → аутентификация раньше проверки сервиса, значит факт включения `moodle_mobile_app` этим не проверяется |
| Создание ключей WS | `/user/managetoken.php` | пользователь: «ничего не нашёл»; локального профиля Moodle нет |
| Экспорт календаря | `/calendar/export_execute.php?...&preset_what=all&preset_time=recentupcoming` | `200 text/calendar`, **19 событий**, 15.11–26.12.2026, без cookies |
| Окна пресетов | `preset_what=user&preset_time=weeknow` / `all&monthnext` / `all&all` | 0 событий / 4 события / `303` |
| Содержимое фида | разбор `VEVENT` | `CATEGORIES` = предмет; `DESCRIPTION` = полный текст задания с LaTeX и ссылками `sdo.tusur.ru/filter/tex/displaytex.php`; `UID` вида `242267@sdo.tusur.ru` |
| Формат фида | разбор строк | время в UTC; свёртка строк **табом**; `PRODID` Moodle 4.5 |

### Расписание (timetable.tusur.ru)

| Проверка | Команда | Результат |
|---|---|---|
| Группа и факультет | `GET /api/v1/groups` | 424 группы; `735-1` → «Факультет безопасности», `faculty_abbr: ФБ`, курс 2 |
| Страница группы | `GET /faculties/fb/groups/735-1` | `200`, 147 КБ, `<title>Расписание занятий группы 735-1` |
| Недели | разбор `ul.weeks li a` | 23 недели, `week_id` 839–861, 31.08.2026 – 01.02.2027, чёт/нечёт |
| Разметка | разбор HTML | 1 desktop-таблица + 6 мобильных `table-lessons.visible-xs` (по дню); в мобильных ячейка времени — `th`, тело — `td` |
| Поля пары | разбор HTML | `span.hidden`=id, `abbr[title]`=название, `span.kind`, `span.auditoriums` + `title` = корпус, `span.group` = преподаватель |
| Модалка пары | `div.js-lesson-info-modal` | абсолютная дата, время `13:15-14:50`, аудитория, ФИО, группы, `data-course-links-url` |
| Ссылка на курс СДО | `GET /ocenka/api/v1/lessons/688778/course_links` | `200 application/json`: `{"url":"https://sdo.tusur.ru/auth/edu?id=12911","anchor":"Курс (гр. 735-1)"}`; без `/ocenka/` → 404 |
| Содержимое недель | прогон парсера | неделя 850 (16–22.11): 3 пары; 851 (23–29.11): 19 пар; 852+ пусто |
| Лимит запросов | серия запросов | после ~15 быстрых запросов — TCP-таймаут на всех хостах ТУСУРа; после паузы восстановилось; 5 запросов с паузой 3 с — 19.5 с, без блокировки |

### Прототип `.ics`

| Проверка | Команда | Результат |
|---|---|---|
| Сборка из фикстуры | `python3 main.py --fixture fixtures/735-1.html` | 3 события, CRLF, сбалансированные `BEGIN/END`, макс. строка 73 октета |
| Живая сборка | `--faculty fb --weeks-ahead 4` | 22 события, 5 запросов, 19.5 с |
| Идемпотентность | повтор с тем же `--state` | `SEQUENCE:0` у всех — не растёт |
| Детект изменения | правка аудитории в фикстуре | `SEQUENCE:1` только у двух изменённых пар |

### Окружение

| Проверка | Результат |
|---|---|
| GitHub | `ssh -T git@github.com` → `Hi Myxo42Mop! You've successfully authenticated`; `gh` не авторизован (не нужен) |
| Инструменты | `bs4 4.15.0`, `pyyaml 6.0.3`, `jq`, `zoneinfo`, `tesseract`, `pdftotext`, `pandoc`; `actionlint`/`yq` нет |
| Браузер | `browsermcp` не подключён («No browser is connected»), CPD/playwright доступны как альтернатива |
| VPN | AmneziaWG (интерфейс `amn0`, маршрут `0.0.0.0/1`) был включён и мешал доступу к сайтам ТУСУРа; остановлен (`systemctl stop AmneziaVPN`) 2026-11-17 |

### Существующие сторонние проекты

- `github.com/Lican1907/tusur-schedule` — Python: парсер расписания → `.ics` на
  GitHub Pages + синк в Google Calendar + Telegram-бот (проверено по README/коду).
- `github.com/Keisha2112/tusur-timetable` — Android-приложение с расписанием.

## 2026-11-17, вечер — Vikunja, MCP, CalDAV, переименование

### Vikunja в Docker

| Проверка | Команда | Результат |
|---|---|---|
| Контейнер | `docker ps` | `laughing_yonath`, `vikunja/vikunja`, `Up`, `0.0.0.0:3456->3456/tcp` |
| Версия и флаги | `curl /api/v1/info` | `v2.8.0`, `caldav_enabled: true`, `frontend_url: http://localhost:3456/`, `max_file_size 20MB` |
| Миграции и БД | `docker logs` | SQLite `/db/vikunja.db`, миграции прошли, Pro отключён (нет ключа) |
| CalDAV-эндпоинт | `curl /dav/`, `/dav/principals/` | **401** — живой, ждёт токен |
| Старый путь | `curl /api/v1/dav/principals/Blesk/` | **404** (в docs Vikunja путь устарел) |
| MCP-эндпоинт | `curl -X GET /api/v2/mcp` | **405** — POST-эндпоинт на месте |
| Регистрация | `POST /api/v1/register {}` | `code 1004` «specify username and password» — открыта |
| Автозапуск | `systemctl is-enabled docker` + `docker update --restart unless-stopped` | `docker.service` = enabled; политика контейнера стала `unless-stopped` |
| Данные вне git | `git status` до/после `.gitignore` | было `?? db/` → добавлены `db/`, `files/`, дерево чистое |

### MCP Vikunja

| Проверка | Результат |
|---|---|
| Запись в `~/.config/opencode/opencode.jsonc` | сервер `vikunja`, `type: remote`, `url: http://127.0.0.1:3456/api/v2/mcp`, `Authorization: Bearer tk_…`; права **600**, бэкап `.bak-vikunja` |
| `initialize` | `HTTP 200`, `text/event-stream`, `protocolVersion 2025-06-18` |
| `tools/list` | **27 инструментов** (`projects_*`, `tasks_*`, `labels_*`, `task_assignees_*`, `task_comments_*`, `filter_syntax`, `find_action`/`do_action`) |
| Живой вызов | `projects_list` → проект `Inbox` (id 1), владелец `Blesk` |

### CalDAV

| Проверка | Результат |
|---|---|
| MCP-токен на CalDAV | `PROPFIND -u Blesk:tk_…` на `/dav/principals/Blesk/` → `{"message":"Unauthorized"}` — **не подходит**, нужен отдельный CalDAV-токен |
| Токен CalDAV | ещё не создан (действие пользователя в Settings → CalDAV) |

### Переименование и GitHub

| Проверка | Результат |
|---|---|
| `mv tusur-schedule tusur-assistent` | git цел, `origin` на месте, история 4 коммита, фикстура по-прежнему даёт 3 события |
| Абсолютные пути в коде | `grep` по `*.py` — нет ни `/home/…`, ни `~/opencode` |
| Deploy key, чтение | `ssh -T git@github-z0den` → `Hi Z0DEN/tusur-schedule!` |
| Репозиторий | `Z0DEN/tusur-schedule`, public, пустой, `has_pages: false` |
| Push | **не делался** (по договорённости) |
