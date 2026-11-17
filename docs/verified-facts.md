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

### GitHub Actions — что проверено и что нет

| Проверка | Результат |
|---|---|
| Наличие `.github/` в проекте | **нет** — workflow не создавался |
| `state.json` в `.gitignore` | да; на раннере его не будет → нужен `--state-from` (файл как состояние) |
| Блокировка по IP | уже наблюдалась: ~15 быстрых запросов → TCP-таймаут всего `.tusur.ru` (см. блок про расписание) |
| Доступность `timetable.tusur.ru` с IP раннеров GitHub | **не проверялось** — только через `workflow_dispatch` |
| Минуты Actions для публичного репозитория | не проверялись на аккаунте `Z0DEN` |

## 2026-11-17, вечер — возможности Vikunja для планировщика

Проверено на живом инстансе 2.8.0, проект `Inbox` (id 1). Тестовая задача
`probe-verify-delete-me` создана, изменена и удалена (в Inbox пусто).

| Проверка | Команда / вызов | Результат |
|---|---|---|
| Поля задачи | `GET /api/v2/schemas/Task.json` | 38 полей; **нет** пользовательских полей и **нет** `updated_by`; есть `created_by`, `updated`, `time_entries_count` |
| Создание задачи | MCP `tasks_create {project:1,…}` | ok, id 2; параметр называется **`project`**, `project_id` → ошибка валидации |
| Чтение/правка/удаление | MCP `tasks_read/update/delete {task:2}` | ok; параметр **`task`**, `id` → ошибка валидации |
| Фильтр по времени изменения | `tasks_list {filter:"updated > now-1h"}` | **1 задача** сразу после создания — курсорный опрос работает |
| Фильтр по заголовку | `filter:"title like 'probe-verify%'"` | 1 задача; после `tasks_delete` → **0** |
| Описание | `tasks_update {description:"est=300 src=user"}` | сохраняется как есть, читается обратно без изменений |
| Вебхуки | `GET /api/v1/projects/1/webhooks` | **401** с API-токеном, тогда как `/api/v1/projects/1` → 200; `/api/v1/user`, `/api/v1/tokens` тоже 401. Неверный путь `…/webhooksXYZ` → 404, значит роут есть, но токен к нему не пускают |
| Вебхуки, документация | `vikunja.io/docs/webhooks`, `/help/webhooks` | существуют проектные (задача создана/завершена/комментарий) и личные (напоминания, просрочки); управление через API — `GET/PUT/DELETE /api/v1/projects/{id}/webhooks` |
| CalDAV | — | токен всё ещё не создан; синхронизация с телефоном не проверена |

Не проверено: принимает ли Vikunja webhook на `127.0.0.1` (SSRF), можно ли выдать
API-токену права на вебхуки, поведение при одновременной записи CalDAV + API.

### Каталог действий Vikunja MCP (для варианта D)

| Проверка | Результат |
|---|---|
| `find_action` (полный список) | **57 действий**: `tasks_*`, `task_labels_*`, `task_assignees_*`, `task_relations_*`, `task_attachments_list/delete`, `task_comments_*`, `projects_*`, `project_views_*`, `buckets_*`, `teams_*`, `filters_*`, `notifications_*`, `reactions_*` |
| Создание вложений | **отсутствует** — только `task_attachments_list` и `task_attachments_delete` |
| Напоминания | **отсутствуют** и в 27 инструментах, и в 57 действиях |
| Учёт времени | отсутствует |
| Вебхуки | отсутствуют; API-токен к `/api/v1/projects/1/webhooks` → `401` |

### Google Calendar: проверка ссылки (2026-11-17)

Ссылка получена от пользователя, сохранена в `~/.config/tusur/google-calendar.url`
(600, каталог 700). Адрес в документах не приводится.

| Проверка | Результат |
|---|---|
| Ответ | `HTTP 200`, `PRODID:-//Google Inc//Google Calendar 70.9054//EN` |
| Событий | **12** `VEVENT` |
| Диапазон дат | **10.11.2021 — 28.02.2025**, то есть **все в прошлом** (сегодня 17.11.2026) |
| Формат времени | все `DTSTART` в UTC (`…Z`), `VTIMEZONE` в файле нет |
| Повторяющиеся | `RRULE` — **0** |
| События «на весь день» | в этой выборке нет (`VALUE=DATE` не встречается) |
| Наши пары в выгрузке | `@timetable.tusur.ru` — **0** (календарь не содержит подписки на фид) |
| Поля события | `ATTENDEE`, `ORGANIZER`, `CLASS`, `STATUS`, `TRANSP`, `X-MICROSOFT-CDO-*` — похоже на календарь приглашений |
| Тип ссылки | **публичная** (`…/public/basic.ics`), значит календарь открыт публично |

Вывод: ссылка рабочая, но для планирования бесполезна — в горизонте 14 дней из
неё не приходит ни одного занятого интервала. Нужен календарь, где лежат
актуальные личные события (или несколько ссылок, по одной на календарь).

### Google Calendar: второй запрос ссылки (2026-11-17)

| Проверка | Результат |
|---|---|
| Пришла ссылка | **та же самая**: `cmp cal-1.url cal-2.url` → идентичны (120 байт) |
| Выгрузка | 12 `VEVENT`, диапазон 10.11.2021 — 28.02.2025, **0 событий в будущем** |
| Действие | `cal-2.url` удалён, остаётся `cal-1.url` (не годится для планирования) |

Вывод: карточка секрета, вероятно, отдала запомненное значение; ссылку на
актуальный календарь пользователь ещё не передал. Нужен **секретный** адрес
(`…/private-<ключ>/basic.ics`) того календаря, где лежат текущие события.

### Google Calendar: третий запрос — рабочий адрес (2026-11-17)

Получен **секретный** адрес (`…/private-…/basic.ics`) основного календаря.
Хранится в `~/.config/tusur/calendars/cal-1.url` (600, каталог 700); в документах
адреса нет.

| Проверка | Результат |
|---|---|
| Ответ | `HTTP 200`, 11190 байт (прежняя публичная выгрузка — 10836) |
| Событий | **13** `VEVENT` — те же 12, что были в публичной ссылке, плюс одно новое; ни одно не пропало |
| Диапазон | 10.11.2021 — **17.11.2026** |
| В будущем | **1** событие (17.11.2026 21:30 по Томску), в горизонте 14 дней — 1 |
| По годам | 2021 — 1, 2023 — 2, 2024 — 5, 2025 — 4, 2026 — 1 |
| Повторяющиеся | `RRULE` — **0**, `VTIMEZONE` — нет (всё в UTC) |
| «На весь день» | 0 в этой выборке |
| Наши пары (`@timetable.tusur.ru`) | 0 |
| Поля | `ATTENDEE` у 8 из 13, `ORGANIZER` у 1 → календарь приглашений/встреч |

Вывод: ссылка рабочая и это действительно календарь пользователя, но он почти
пуст — в горизонте планирования одно событие. Чтение реализуемо; наполненность —
вопрос к пользователю (возможно, личные события лежат в другом аккаунте или в
локальном календаре телефона).

### Android-клиент задач для Vikunja (проверено 2026-11-17)

| Проверка | Как | Результат |
|---|---|---|
| Tasks.org: что платно | `tasks.org/pricing/` | бесплатный уровень — только «popular cloud services»; **«Self-hosted synchronization with DAVx⁵, CalDAV, and EteSync»** — в платном: name-your-price от $0.99 (спонсорство на GitHub — $1/год), подписка $2.49/мес / $29.99/год. Оценка пользователя «платное» верна |
| jtx Board: лицензия и свежесть | F-Droid `at.techbee.jtx`, GitHub `TechbeeAT/jtxBoard` | GPL-3.0; F-Droid 2.17.03.ose (06.10.2026); `versionName = 2.17.04`, ветка `develop`, push 16.11.2026 — жив |
| jtx Board: Pro в F-Droid-сборке | `app/src/ose/java/at/techbee/jtx/flavored/BillingManager.kt` | `override var isProPurchased: LiveData<Boolean> = MutableLiveData(true) // always true for OSE flavor` — в сборке F-Droid **все Pro-функции открыты бесплатно** |
| jtx Board: Pro в Play-сборке | `app/src/gplay/.../BillingManager.kt` | Google Billing, товар `IN_APP_PRODUCT_PRO = "adfree"`, разовая покупка; README: Play-Pro «enables editing options for remote entries» |
| jtx Board: два времени у задачи | `ui/detail/DetailsCardDates.kt` | есть и `dtstart`, и `due`, у каждого своя таймзона (`dtstartTimezone`, `dueTimezone`), поля включаются флагами `enableDtstart` / `enableDue`, есть валидация `due_date_before_dtstart` → блок 19:20–20:20 представим |
| jtx Board: остальные поля | файлы `DetailsCard*` | категории, приоритет/классификация/статус, напоминания (`DetailsCardAlarms`), подзадачи, вложения, комментарии, участники, повторения, коллекции |
| jtx Board: русский | F-Droid/репозиторий (`values-ru`) | есть |
| DAVx⁵: цена | `davx5.com`, F-Droid `at.bitfire.davdroid` | GPL-3.0; на F-Droid **бесплатно** (сборка из исходников, свой ключ), в Google Play — платно; 4.5.21-ose (18.10.2026) |
| Fossify Calendar | F-Droid, issue FossifyOrg/Calendar#36 | задачи **не** синхронизируются по CalDAV (открытый запрос) |
| OpenTasks | F-Droid `org.dmfs.opentasks` | пакета на F-Droid **нет** (404); последний релиз 1.4.2 от 21.03.2021 — проект стоит |

Вывод: связка **DAVx⁵ + jtx Board** закрывает задачу бесплатно и полностью
открытым кодом; платить за CalDAV не нужно.
