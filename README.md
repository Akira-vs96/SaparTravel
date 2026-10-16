# SaparTravel

SaparTravel — учебный веб-сервис для поиска и бронирования туров. Пользователь
находит опубликованный тур, выбирает выезд и количество путешественников,
создаёт заявку и отслеживает её статус. Интерфейс и каталог доступны на
русском, казахском и английском языках.

Текущий стек: React/Vite, FastAPI, SQLAlchemy, PostgreSQL 17, JWT/Argon2,
Docker Compose и Nginx. Supabase Auth и внешняя авторизация не используются.

## Быстрый старт

Требуются Docker Engine с запущенным daemon, Docker Compose v2 и Python 3.

```bash
python3 scripts/setup_env.py
docker compose up --build -d
```

После запуска:

| Компонент | Адрес |
|---|---|
| Сайт | http://127.0.0.1:5173 |
| Swagger / OpenAPI | http://127.0.0.1:8000/docs |
| Health API + БД | http://127.0.0.1:8000/api/v1/health |
| PostgreSQL с хоста | `127.0.0.1:55432` |

Порт PostgreSQL с хоста задаётся переменной `DB_PORT`. Если порт `5432`
свободен, можно использовать `DB_PORT=5432`; в текущем локальном окружении
`5432` занят, поэтому используется `55432`. Внутри Docker API всегда обращается
к `db:5432`.

Проверка:

```bash
docker compose ps
curl http://127.0.0.1:8000/api/v1/health
```

Ожидаемый ответ:

```json
{"status":"ok","service":"sapartravel-api","database":"ok"}
```

Миграции и демонстрационное наполнение запускаются автоматически при старте
API. Администратор создаётся из `ADMIN_EMAIL` и `ADMIN_PASSWORD` в `.env`.
Секреты генерируются скриптом и не должны попадать в Git.

## Возможности

- Каталог с поиском, фильтрами по направлению, континенту, категории, цене и длительности, сортировкой и пагинацией.
- Страница тура: программа по дням, включённые услуги, даты выездов, стоимость и свободные места.
- Регистрация, вход, профиль и сохранённое избранное.
- Бронирование выбранного выезда, расчёт стоимости на сервере, история и отмена собственных заявок.
- Кабинет поставщика: создание и изменение своих туров, публикация, добавление выездов, обработка бронирований.
- Кабинет администратора: управление каталогом, бронированиями и ролями пользователей.
- Защита от переполнения групп при одновременных бронированиях, журнал изменения статусов.

**Онлайн-оплаты нет.** Создание заявки не списывает деньги; условия оплаты согласуются после подтверждения поставщиком. Все суммы указаны в USD. Начальное наполнение — демонстрационные маршруты и цены, а не реальные предложения туроператоров. Его можно отключить через `SEED_DEMO_DATA=false`.

## Запуск через Docker

Нужны Docker Engine с запущенной службой, Docker Compose v2 и Python 3 для генерации конфигурации.

```bash
python3 scripts/setup_env.py
docker compose up --build -d
```

Скрипт создаёт локальный `.env` с уникальными секретами. Если файл уже существует, он сохраняется. Пример всех переменных — [.env.example](.env.example).

- Сайт: http://localhost:5173
- OpenAPI / Swagger: http://localhost:8000/docs
- Проверка API и БД: http://localhost:8000/api/v1/health
- PostgreSQL для локальных инструментов: `127.0.0.1:${DB_PORT}`, база `sapartravel`, пользователь `sapar`; пароль — `POSTGRES_PASSWORD` в `.env`.

Миграции и начальное наполнение выполняются при запуске API. База сохраняется в Docker volume `postgres_data`. Обычная остановка `docker compose down` данные сохраняет. **Ключ `-v` удаляет базу.**

Администратор создаётся из `ADMIN_EMAIL` и `ADMIN_PASSWORD` в `.env`. По умолчанию адрес — `admin@example.com`, пароль случайный и находится только в `.env`. Для своего адреса используйте `python3 scripts/setup_env.py --admin-email your@email.com` при первом запуске. Готовых общедоступных паролей в репозитории нет. Новые пользователи получают роль `traveler`; назначить поставщика может администратор на странице управления пользователями.

## Разработка без контейнеров приложения

Нужны Python 3.12+, Node.js 22.12+ и PostgreSQL 17. Базу можно поднять отдельно:

```bash
python3 scripts/setup_env.py
docker compose up -d db
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
```

API использует переменные из `.env`. Команды выполняются из корня проекта:

```bash
set -a
source .env
set +a
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/python -m app.seed
../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

В другом терминале:

```bash
cd frontend
npm ci
npm run dev
```

Vite проксирует `/api` на `localhost:8000`; в Docker это делает Nginx. Браузер не обращается к жёстко заданному адресу localhost API. Для раздельного размещения фронтенда и API задайте `VITE_API_URL` на этапе сборки и разрешённые источники `CORS_ORIGINS` на сервере.

## Проверки

```bash
cd backend
../.venv/bin/pytest -q
```

Быстрые API-тесты используют отдельную SQLite-базу только в тестовом окружении. Для интеграционных проверок PostgreSQL задайте `TEST_DATABASE_URL`, указывающий на **отдельную тестовую базу**: тесты пересоздают её таблицы. Рабочая конфигурация принимает только PostgreSQL.

```bash
cd frontend
npm ci
npm run build
```

GitHub Actions проверяет API с PostgreSQL, сборку фронтенда и основные сценарии в Chromium. Подробности сценариев — [план тестирования](docs/qa/test-plan.md).

Для проверки уже запущенной **отдельной демонстрационной среды** в браузере:

```bash
.venv/bin/pip install -r tests/requirements-browser.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_smoke.py --base-url http://127.0.0.1:5173
```

## Работа с базой данных

Рабочая база — PostgreSQL 17 в контейнере `db`. Данные хранятся в Docker
volume `postgres_data` и не удаляются обычной командой `docker compose down`.

Подключение через psql:

```bash
docker compose exec db psql -U sapar -d sapartravel
```

Полная схема, ER-диаграмма, ключи, ограничения и правило конкурентного
бронирования описаны в [ER-модели](docs/er-model.md) и
[описании PostgreSQL-схемы](docs/postgresql-schema.md).

Основные таблицы:

`users`, `destinations`, `experiences`, `departures`, `favorites`, `bookings`,
`booking_status_history`.

Удаление базы вместе с volume является разрушительной операцией:

```bash
docker compose down -v
```

Для резервного копирования и восстановления используйте
[операционный runbook](docs/ops/runbook.md).

## Функциональный объём MVP

### Турист

- каталог, поиск, фильтры, сортировка и пагинация;
- карточка тура с программой, услугами, ценой и выездами;
- регистрация, вход, профиль и избранное;
- создание заявки, серверный расчёт суммы, история, статус и отмена.

### Поставщик

- создание и редактирование собственных туров;
- управление публикацией и выездами;
- обработка заявок только по своим турам.

### Администратор

- управление направлениями и каталогом;
- управление заявками;
- назначение ролей и управление пользователями.

Доступ к операциям проверяется на API по JWT, роли и владельцу ресурса.
Создание бронирования выполняется транзакционно с блокировкой строки выезда
через `SELECT ... FOR UPDATE`, поэтому конкурентные заявки не создают
отрицательное количество мест.

## Качество и проверки

Backend-тесты:

```bash
cd backend
../.venv/bin/pytest -q
```

Frontend:

```bash
cd frontend
npm ci
npm run build
```

Браузерные проверки:

```bash
cd ..
.venv/bin/pip install -r tests/requirements-browser.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_smoke.py --base-url http://127.0.0.1:5173
```

План проверок и критерии приёмки находятся в
[docs/qa/test-plan.md](docs/qa/test-plan.md). CI проверяет PostgreSQL,
миграции, повторный seed, API-тесты, frontend build и сценарии Chromium.

## Безопасность и ЛЗ 7

Артефакты лабораторной работы:

- [RAID-лог](docs/security/raid.md): 20 рисков, владельцы, триггеры, EMV и резервы;
- [STRIDE-модель угроз](docs/security/threat-model.md);
- [файл Threat Dragon](docs/security/threat-model.json);
- [чек-лист соответствия](docs/security/compliance-checklist.md);
- [security backlog](docs/security/security-backlog.md);
- [отчёт Trivy и Gitleaks](docs/security/security-scan-report.md).

Запуск сканеров из корня проекта:

```bash
docker run --rm -v "$(pwd):/src" aquasec/trivy fs \
  --scanners vuln,secret /src
docker run --rm -v "$(pwd):/path" zricethezav/gitleaks:latest detect \
  -s /path -v --redact
```

Последний результат не является чистым `PASS`: Trivy нашёл 16 уязвимостей
зависимостей (включая 1 Critical и 5 High), а Gitleaks — 6
секретоподобных совпадений в тестовых значениях и истории Git. Подробности,
CVE и план исправлений находятся в [security-scan-report.md](docs/security/security-scan-report.md).

## Документация проекта

- [Устав проекта](docs/project-charter.md);
- [Story Map и MVP](docs/requirements/story-map.md);
- [План тестирования](docs/qa/test-plan.md);
- [ER-модель и PostgreSQL](docs/er-model.md);
- [Runbook эксплуатации](docs/ops/runbook.md);
- [ADR-001 о Scrum](docs/adr/ADR-001.md);
- [Итоговый портфель проекта](docs/portfolio/final-portfolio.md);
- [Security-документация](docs/security/risk-assessment.md).


## Структура

```text
backend/
  app/                 FastAPI, модели, авторизация, каталог и бронирования
  migrations/          версионируемые миграции PostgreSQL
  tests/               проверки API и бизнес-правил
frontend/
  src/                 React: страницы, компоненты, переводы и API-клиент
  nginx.conf           SPA и прокси API для Docker
scripts/               генерация конфигурации и резервное копирование
.github/workflows/     автоматические проверки
docs/                 требования, архитектура, планирование и эксплуатация
```

Архитектура и связи таблиц: [PostgreSQL](docs/postgresql-schema.md). Запуск, резервные копии и восстановление: [runbook](docs/ops/runbook.md). Продуктовые и учебные материалы сохранены в `docs/`, включая [ADR-001](docs/adr/ADR-001.md) о Scrum с двухнедельными спринтами.

## Границы текущей версии

В текущий MVP намеренно не входят онлайн-оплата и банковский эквайринг,
реальные API отелей/туроператоров, внешняя синхронизация, email/SMS,
восстановление пароля по почте, мобильное приложение, отзывы, возвраты и
полноценная продуктовая аналитика. Изображения загружаются с Unsplash, а
каталог и цены являются демонстрационными.

Локальный Docker-запуск не является production-развёртыванием. Для публичного
размещения нужны домен, HTTPS, защищённое хранилище секретов, политика
персональных данных, мониторинг, резервное копирование и проверка нагрузки.
