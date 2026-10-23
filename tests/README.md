# Проверки SaparTravel

Работайте только с отдельной демонстрационной средой. Браузерные сценарии
создают пользователей, туры и сделки. PostgreSQL-тесты очищают свою базу;
рабочий `DATABASE_URL` нельзя подставлять в `TEST_DATABASE_URL`.

## Backend и миграции

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/sapartravel_test ../.venv/bin/python -m pytest -q
```

Тестовое имя БД должно заканчиваться на `_test`. Тест миграций создаёт
собственную случайную БД и требует CREATEDB. PostgreSQL 17 необходим для
проверки блокировок, конкурентности и миграций. SQLite разрешена только
для быстрых изолированных проверок, она не заменяет PostgreSQL.

Сохраняются исходные проверки. Новые наборы проверяют quote и деньги KZT,
снимок условий, участников/услуги/промокоды, места, срок резерва, идемпотентность,
3DS/тайм-ауты, возвраты, права, одноразовый reset, поддержку/отзывы, seed,
миграцию старых USD-сделок, N+1 и полночь Asia/Almaty.

## Frontend и Chromium

```bash
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=high
.venv/bin/python -m pip install -r tests/requirements-browser.txt
.venv/bin/python -m playwright install chromium
```

Для ролевых сценариев задайте `E2E_ADMIN_EMAIL/PASSWORD` в окружении процесса
из приватной конфигурации тестовой среды. Не печатайте их в CI/отчётах.

| Скрипт | Проверяет |
|---|---|
| `browser_smoke.py` | Регистрация, профиль, избранное, поиск, quote/участники/услуги, ошибка карты, оплата 3DS, подтверждение/ICS, отмена/возврат, admin, 401, mobile/error |
| `browser_management.py` | Направления/переводы/программа/галерея/услуги/ограничения/политика/выезды, публикация/скрытие, новый поставщик |
| `browser_engagement.py` | Приватная reset-ссылка, поддержка/права/ответы, уведомления, сохранённый поиск, сравнение |
| `browser_localization.py` | Полный checkout/payment/refund ru/360, kk/768, en/1440, сохранение форм, локализованные ошибки/документы и отсутствие PAN/CVC в storage |
| `browser_visual.py` | 45 сочетаний публичных экранов, языков и размеров, фото и ошибки JS |
| `browser_roles_visual.py` | 9 сочетаний кабинета, таблиц и аналитики, диалог с Tab/Shift+Tab/Escape |

```bash
.venv/bin/python tests/browser_smoke.py --base-url http://127.0.0.1:5173
.venv/bin/python tests/browser_management.py --base-url http://127.0.0.1:5173
.venv/bin/python tests/browser_engagement.py --base-url http://127.0.0.1:5173 --api-url http://127.0.0.1:8000
.venv/bin/python tests/browser_localization.py --base-url http://127.0.0.1:5173 --api-url http://127.0.0.1:8000
.venv/bin/python tests/browser_visual.py --base-url http://127.0.0.1:5173
.venv/bin/python tests/browser_roles_visual.py --base-url http://127.0.0.1:5173
```

Артефакты — `test-results/`, исключены из Git. В снимках локализованной
оплаты поля платёжной формы маскируются. Используются только документированные
тестовые инструменты. Внешние банковские/почтовые операции не выполняются.

Основной smoke требует private demo с действующим `SAPAR10` (`python -m app.demo`).
Отдельное `backend/debugging_lab` — сохранённое упражнение с намеренной
ошибкой: его прямой запуск даёт 2 failed / 1 passed, как в исходном учебном
отчёте. Оно не импортируется приложением и не входит в неизменённый
`backend/pytest.ini:testpaths=tests`. Проверки не отключались ради результата.

Фактические команды и результаты: [verification-results.md](../docs/verification-results.md).
Матрица 16 обязательных сценариев находится там же. Workflow CI запускает
миграции, повторный seed, PostgreSQL, сборку/npm audit и все шесть скриптов.
