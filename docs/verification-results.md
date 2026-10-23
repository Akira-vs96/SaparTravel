# Фактические результаты проверки SaparTravel

Дата: **2026-10-23**, пользовательская зона **Asia/Almaty**. Учебные отчёты
прошлых лабораторных работ не изменялись. Все тесты, создающие данные,
выполнялись в отдельных PostgreSQL-базах/Compose-проекте `sapartravel-qa`.
Рабочая база не очищалась. Секретная часть URL и пароли в журнал не включаются.

## Команды и результаты

| Проверка | Фактическая команда / способ | Результат |
|---|---|---|
| Исходный backend | `cd backend && TEST_DATABASE_URL=…/sapartravel_test ../.venv/bin/python -m pytest -q` | **20 passed**, PostgreSQL 17 |
| Исходный frontend | `npm --prefix frontend run build` | Успешно, Vite 8.3.0 |
| Финальный backend | `cd backend && TEST_DATABASE_URL=…/sapartravel_test ../.venv/bin/python -m pytest -o addopts='' -q --tb=short --show-capture=no` | **74 passed**, 21.34 s, PostgreSQL 17; одно предупреждение Starlette/AnyIO |
| Финальная сборка | `npm --prefix frontend run build`; также build образа web | Успешно, **Vite 8.3.5**, 1908 модулей; JS 469.61 kB / gzip 138.07 kB, CSS 87.44 kB / gzip 17.35 kB |
| Зависимости frontend | `cd frontend && npm audit --audit-level=high` | **0 vulnerabilities**; исправлено обнаруженное предупреждение Vite 8.3.0 |
| Чистые миграции | `alembic upgrade head && alembic check` в отдельной чистой PostgreSQL | **0001 → 0002 → 0003 → 0004**, No new upgrade operations detected |
| Копия реальной MVP-базы | Custom `pg_dump` → `pg_restore --no-owner --no-privileges` в `sapartravel_upgrade_final_test`, затем `alembic upgrade head && alembic check` | Успешно; 24 направления/24 тура; исходные ID и учётные данные сохранены |
| Старые сделки USD | `pytest tests/test_migrations.py` в составе полного набора | Четыре искусственные старые сделки pending/confirmed/cancelled/completed сохранены; валюты/суммы/снимки/история не потеряны; фиктивных оплат нет |
| Seed / private demo | Повторные `python -m app.seed`, `python -m app.demo --credentials-file …`; `test_seed.py`, `test_demo.py` | Дублей и перезаписи паролей/редактирования нет; даты существующих выездов сохраняются |
| Docker Compose | `docker compose --env-file .env.qa -p sapartravel-qa up --build -d` | PostgreSQL и API healthy, Nginx и worker работают; Python 3.12, Node 22, PostgreSQL 17 |
| Основной E2E | `python tests/browser_smoke.py --base-url http://127.0.0.1:5182` | **PASS**: регистрация, профиль, избранное, расчёт, участники/услуга, ошибка срока карты, отказ банка, 3DS, подтверждение, HTML/ICS, отмена и полный возврат, admin/401/mobile/API error |
| Поставщик и администратор | `python tests/browser_management.py --base-url http://127.0.0.1:5182` | **PASS**: переводы направления/тура, программа, галерея, услуги, ограничения, политика отмены, выезд, публикация/скрытие, новый vendor и собственный черновик |
| Дополнительные сервисы | `python tests/browser_engagement.py --base-url http://127.0.0.1:5182 --api-url http://127.0.0.1:8012` | **PASS**: приватная reset-ссылка и одноразовость, logout, поддержка/ответы/права, уведомления, сохранённый поиск, сравнение до 3 |
| Оформление на трёх языках | `python tests/browser_localization.py --base-url http://127.0.0.1:5182 --api-url http://127.0.0.1:8012` | **PASS**: ru/360, kk/768, en/1440; сохранение формы при переключении языка и reload; 422, отказ, отмена 3DS, успешный повтор, HTML нужного языка, ICS, возврат 60 000 KZT и освобождение двух мест; PAN/CVC в storage нет |
| Публичные экраны | `python tests/browser_visual.py --base-url http://127.0.0.1:5182` | **45/45** сочетаний: главная/каталог/тур/подбор/вход × ru/kk/en × 360/768/1440; фотографии загружены, ошибок JS и горизонтального скролла нет |
| Кабинеты и клавиатура | `python tests/browser_roles_visual.py --base-url http://127.0.0.1:5182` | **PASS**: управление/пользователи/аналитика, 9 сочетаний языка/ширины; Tab/Shift+Tab остаются в диалоге, Escape закрывает его |
| Перезапуск всех процессов | `docker compose --env-file .env.qa -p sapartravel-qa restart db api worker web`; сравнение SHA-256 упорядоченных финансовых записей до/после | **PASS**: сохранены 11 броней, 16 попыток оплаты, 5 возвратов, 21 операция провайдера; HTTP health OK |
| Worker | `docker compose … exec -T api python -m app.worker --once`; тесты идемпотентности sweep | **PASS**, повтор не создаёт повторных действий |
| Число SQL-запросов | `test_recommendations_and_manager_list_batch_queries_as_catalog_grows` | **PASS**: при росте 1 → 6 туров / 26 выездов число SELECT не растёт; данные не обрезаются |
| Лимит промокода на границе commit | `test_promo_confirmation_holds_limit_until_commit_across_expiry` | **PASS**: вторая PostgreSQL-транзакция ждёт блокировку; после commit не получает второй промокод |
| Компенсированная поздняя оплата и промокод | `test_late_compensated_payment_does_not_reconsume_released_promo` | **PASS**, освобождённое использование не расходуется повторно |
| Переполнение денежного итога | `test_aggregate_money_overflow_is_rejected_before_reserving` | **PASS**, 422 до записи брони и резерва |
| Изолированное учебное упражнение | `cd backend && ../.venv/bin/python -m pytest -o addopts='' -q debugging_lab/test_booking_total.py` | **2 failed, 1 passed** — намеренный исход учебного примера, исходники и отчёт сохранены; код не используется приложением |
| Полночь Алматы | `test_almaty_midnight_boundary_matches_validation_catalog_and_booking` | **PASS**: дата UTC ещё 1 января, Алматы уже 2; нельзя создать/показать доступным начавшийся местный день |
| Статические проверки | `git diff --check`; `python -m compileall -q backend/app backend/migrations backend/tests tests scripts/setup_env.py` | Успешно |
| Обновление локального приложения | Backup, `docker compose up --build -d`, private demo, `alembic check`, health | **PASS**, приложение http://localhost:5173; исходные пользователи и ID 24 направлений/туров сохранены |

Для браузерных команд `E2E_ADMIN_EMAIL/PASSWORD` загружались из приватной
`.env.qa` в память процесса без печати. Сначала эти же сценарии отлажены на
изолированных Uvicorn/Vite 8011/5181; итоговые результаты таблицы относятся
к Nginx/Compose 8012/5182. Финальные патчи общей бизнес-даты, денежного лимита и межтранзакционного
лимита промокода покрыты полным набором 74 тестов; основной браузерный путь
дополнительно проверяет реальный промокод в расчёте и оплате.

## Обязательные 16 сценариев из promt1.md

| № | Сценарий | Покрытие | Фактический итог |
|---|---|---|---|
| 1 | Регистрация → поиск → выезд → участники/услуги → KZT → оплата → кабинет | browser_smoke, browser_localization | PASS |
| 2 | Оплаченная бронь → отмена → возврат → история/уведомление | test_cancellation_refund_policy_and_repeat; браузерные пути | PASS, полный/80%/50% возврат |
| 3 | Истёкшая карта и последний месяц действия | test_expiry_boundary_controlled_clock, UI expiry error | PASS, управляемое время |
| 4 | Номер/CVC/срок/средства/банк/3DS | test_instrument_validation, declines/3ds parametric tests; UI 422 и decline | PASS |
| 5 | Один/разные ключи и повторный клик | checkout idempotency, parallel payments | PASS, максимум одна успешная оплата |
| 6 | Неопределённый исход и поздний результат | unknown_late_success_compensates, unknown_failure_durable_provider | PASS, сверка и компенсационный возврат |
| 7 | Два запроса на последнее место | test_last_seat_cannot_be_booked_twice | PASS, ровно один успешный резерв |
| 8 | Истечение / гонки оплаты и отмены | parallel_promo_and_payment_cancel_race; worker idempotency | PASS, вместимость сохранена |
| 9 | Параллельные и повторные возвраты | parallel_payments_and_refunds_bounded, pending_refund_reserves_balance | PASS, сумма не выше оплаты |
| 10 | Подмена денег, валюты, пользователя, статуса | strict schemas, payload_tampering, ownership/state tests | PASS, 422/403/404/409 по контракту |
| 11 | Изоляция ролей и чужих объектов | API, support vendor isolation, browser_management | PASS |
| 12 | Срок и конкурентный лимит промокода | promo_limits_unpaid_release_and_expiry, parallel promo | PASS |
| 13 | Право на отзыв / одноразовый reset | engagement verified review, concurrent reset, UI reset | PASS; одновременный reset [200,422] |
| 14 | Перезапуск / повторный seed | provider persistence, seed/demo tests, полный Compose restart | PASS |
| 15 | Чистая БД / копия MVP | реальные Alembic/PostgreSQL, migration fixture четырёх USD-сделок | PASS |
| 16 | Mobile/desktop/ru/kk/en/ошибки/пустые состояния | все шесть браузерных скриптов | PASS |

## Артефакты и границы результатов

Снимки находятся в игнорируемом `test-results/`: `visual-*`,
`localization-*`, `engagement-*`, `management*`, `booking-confirmed-desktop.png`.
Основные снимки просмотрены визуально. Поля платёжной формы в снимках локализованного пути маскируются.
В истории используются только идентификаторы и маски тестовых карт;
пароли и ссылки восстановления в журнал не выводятся.

До обновления сохранён private backup
`backups/sapartravel-20261023T075626Z-BFuMKb.dump`, проверено восстановление
его копии. Исходный `.env` сохранён в приватном `.env.before-promt1`; секреты
и порты не заменялись. Тестовые доступы локального приложения — приватный
`.env.demo-credentials.json` (0600, исключён из Git).

Workflow CI обновлён: миграции/seed/PostgreSQL, build/npm audit, шесть
браузерных скриптов и артефакты. **Запуск на GitHub Actions из этого сеанса
не выполнялся**; локальные команды выше выполнены фактически.

Остаётся одно предупреждение совместимости Starlette TestClient/AnyIO, тесты
не отключались. Нагрузочный тест, новое сканирование контейнеров Trivy,
публичное HTTPS и интеграции с банком/SMTP не выполнялись. Демонстрационный
провайдер и почта — имитации; локальные PASS не являются допуском к публичной
коммерческой эксплуатации.

Обновление Vite основано на официальном
[описании исправления уязвимости](https://github.com/vitejs/vite/security/advisories/GHSA-rq7h-c2jc-7f22)
и [релизе 8.3.5](https://github.com/vitejs/vite/releases/tag/v8.3.5).
