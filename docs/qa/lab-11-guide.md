# ЛЗ 11 — единый гайд по артефактам и запуску

Этот файл объясняет, где находятся материалы ЛЗ 11, что именно было сделано,
как запустить проверки и что показать преподавателю.

## 1. Кратко: что такое UAT

**UAT (User Acceptance Testing)** — User Acceptance Testing, или
приёмочное тестирование пользователем/заказчиком.

Цель UAT — проверить не только корректность кода, но и то, что пользователь
может выполнить реальные бизнес-сценарии: найти тур, оформить бронирование,
оплатить, отменить и получить возврат.

В этом проекте владелец продукта и разработчик — один человек, поэтому
оформлена **самоприёмка владельца продукта**. Это нужно отличать от
независимого UAT другой команды.

## 2. Главные файлы

### План тестирования

- [docs/qa/test-plan.md](test-plan.md) — стратегия тестирования, тестовая
  пирамида, среды, данные, дефекты, quality gates и стоимость дефекта.
- [docs/qa/accessibility-security.md](accessibility-security.md) —
  проверки доступности интерфейса и безопасности.
- [docs/verification-results.md](../verification-results.md) — фактические
  результаты автоматических и CI-проверок.
- [tests/README.md](../../tests/README.md) — команды запуска тестов.

### UAT

- [docs/qa/uat-protocol.md](uat-protocol.md) — 10 UAT-сценариев, критерии
  прохождения и результаты.
- [docs/qa/uat.md](uat.md) — протокол передачи и решение о приёмке.
- [docs/qa/uat-execution.md](uat-execution.md) — команды технического
  прогона UAT.
- [docs/qa/uat-owner-acceptance.md](uat-owner-acceptance.md) —
  самоприёмка Product Owner.

### Инцидент и эксплуатация

- [docs/qa/postmortem.md](postmortem.md) — безвинный postmortem инцидента.
- [docs/ops/runbook.md](../ops/runbook.md) — эксплуатационный runbook.
- [docs/ops/service-levels.md](../ops/service-levels.md) — SLI, SLO,
  error budget и поддержка.
- [docs/ops/handoff.md](../ops/handoff.md) — передача в эксплуатацию,
  quality gates и роли.
- [docs/ops/free-hosting.md](../ops/free-hosting.md) — фактический деплой
  через GitHub → Render Free и Neon Free.
- [docs/ops/monitoring-setup.md](../ops/monitoring-setup.md) — настройка
  Uptime Kuma.

### Инструменты

- [api/bruno/](../../api/bruno/) — API-коллекция Bruno.
- [load/k6/catalog-health.js](../../load/k6/catalog-health.js) — k6 smoke
  для нагрузки.
- [scripts/catalog_load.py](../../scripts/catalog_load.py) — основной Python
  нагрузочный профиль с каталогом из 500 туров.
- [scripts/prepare_catalog_load.py](../../scripts/prepare_catalog_load.py) —
  подготовка нагрузочных данных.
- [.github/workflows/service-level-acceptance.yml](../../.github/workflows/service-level-acceptance.yml)
  — CI-профиль нагрузки и восстановления.

## 3. Что уже подтверждено

| Требование | Где доказательство |
|---|---|
| План тестирования | [test-plan.md](test-plan.md) |
| Пирамида тестов | [test-plan.md](test-plan.md) |
| Backend/API/integration tests | [backend/tests/](../../backend/tests/) |
| Browser/Playwright tests | [tests/](../../tests/) |
| Результаты браузерных запусков | [browser.json](../labs/lab-11/evidence/browser.json) |
| Мультиязычность | `tests/browser_localization.py` |
| Визуальные проверки | `tests/browser_visual.py` |
| Роли и клавиатура | `tests/browser_roles_visual.py` |
| Нагрузочный CI-профиль | [service-level-acceptance.yml](../../.github/workflows/service-level-acceptance.yml) |
| Восстановление после отказа | `scripts/recovery_acceptance.py` и CI evidence |
| UAT-сценарии | [uat-protocol.md](uat-protocol.md) |
| Самоприёмка PO | [uat-owner-acceptance.md](uat-owner-acceptance.md) |
| Postmortem | [postmortem.md](postmortem.md) |
| Runbook | [runbook.md](../ops/runbook.md) |
| Uptime Kuma в Compose | [docker-compose.yml](../../docker-compose.yml) |
| API collection | [api/bruno/](../../api/bruno/) |
| k6-сценарий | [load/k6/catalog-health.js](../../load/k6/catalog-health.js) |
| Передача в эксплуатацию | [handoff.md](../ops/handoff.md) |

## 4. Подготовка окружения

Команды выполняются из корня проекта:

```bash
cd /home/akira/IdeaProjects/SaparTravel
```

Создать demo-конфигурацию:

```bash
python3 scripts/setup_env.py --demo
```

Команда создаёт `.env`. Секреты из `.env` нельзя добавлять в Git или
показывать на защите.

Необходимые инструменты:

- Python 3.12;
- Docker и Docker Compose;
- Node.js и npm;
- PostgreSQL 17 для полного backend-набора;
- Playwright и Chromium для browser-тестов;
- Bruno CLI для API-коллекции;
- k6 для нагрузочного smoke.

## 5. Запуск приложения и Uptime Kuma

Запустить все сервисы:

```bash
set -euo pipefail
docker info >/dev/null
docker compose up --build -d
```

Если `docker info` не проходит, сначала запустите Docker Engine:

```bash
sudo systemctl start docker
docker info
```

Для Docker Desktop сначала откройте Docker Desktop. Не запускайте browser-
тесты, пока health endpoint не отвечает: иначе появится вторичная ошибка
`ECONNREFUSED`.

Проверить состояние:

```bash
docker compose ps
```

Проверить health API:

```bash
curl --fail http://localhost:8000/api/v1/health
```

Адреса:

| Сервис | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Swagger API | http://localhost:8000/docs |
| API health | http://localhost:8000/api/v1/health |
| Uptime Kuma | http://localhost:3001 |

Логи API:

```bash
docker compose logs --tail=100 api
```

В Uptime Kuma после первого открытия нужно:

1. создать локальную учётную запись администратора;
2. создать HTTP-монитор;
3. указать URL `http://api:8000/api/v1/health`;
4. установить интервал 60 секунд;
5. установить timeout 5 секунд;
6. ожидать HTTP-код `200`.

Для проверки frontend можно добавить второй монитор на `http://web/`.
Uptime Kuma подтверждает доступность, но не заменяет нагрузочные тесты,
логи, метрики, трассировки и независимые внешние probes.

Остановить стенд:

```bash
docker compose down
```

## 6. Backend-тесты

Тесты должны работать с отдельной базой, имя которой заканчивается на
`_test`. Нельзя использовать рабочую базу.

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/sapartravel_test \
  ../.venv/bin/python -m pytest -q
cd ..
```

Быстрые тесты доказательств из корня:

```bash
.venv/bin/python -m pytest -q \
  tests/course/test_evidence.py \
  tests/test_service_operations.py
```

Ожидаемый результат для текущего набора: `29 passed`.

## 7. Frontend build и audit

```bash
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=high
```

Ожидаемые результаты: успешная сборка и отсутствие high/critical
уязвимостей.

## 8. Browser/Playwright-тесты

Установка зависимостей:

```bash
.venv/bin/python -m pip install -r tests/requirements-browser.txt
.venv/bin/python -m playwright install chromium
```

Запуск основных сценариев:

```bash
.venv/bin/python tests/browser_smoke.py \
  --base-url http://localhost:5173

.venv/bin/python tests/browser_management.py \
  --base-url http://localhost:5173

.venv/bin/python tests/browser_engagement.py \
  --base-url http://localhost:5173 \
  --api-url http://localhost:8000

.venv/bin/python tests/browser_localization.py \
  --base-url http://localhost:5173 \
  --api-url http://localhost:8000

.venv/bin/python tests/browser_visual.py \
  --base-url http://localhost:5173

.venv/bin/python tests/browser_roles_visual.py \
  --base-url http://localhost:5173

.venv/bin/python tests/browser_invalid_response.py \
  --base-url http://localhost:5173
```

Проверяется:

- основной путь туриста;
- управление поставщика и администратора;
- поддержка, reset, уведомления и saved search;
- ru/kk/en;
- размеры 360/768/1440;
- отсутствие горизонтального скролла;
- отсутствие JavaScript page errors;
- `Tab`, `Shift+Tab`, `Escape`;
- корректное поведение при `null` и HTML вместо JSON.

Результаты браузерных проверок сохраняются в `test-results/`. Эта папка
исключена из Git.

## 9. Bruno API collection

Коллекция находится в [api/bruno/](../../api/bruno/).

Если Bruno CLI установлен:

```bash
bruno run api/bruno --env Local
```

Коллекция проверяет:

- `GET /api/v1/health`;
- `GET /api/v1/catalog`.

Если команда `bruno` не найдена, установите Bruno CLI согласно инструкции
вашей ОС или запустите те же запросы вручную через Swagger:
http://localhost:8000/docs.

## 10. Нагрузочное тестирование

### Быстрый k6 smoke

```bash
k6 run \
  -e BASE_URL=http://localhost:8000 \
  -e K6_RATE=20 \
  -e K6_DURATION=30s \
  load/k6/catalog-health.js
```

Сценарий проверяет HTTP-коды, JSON-ответы, долю ошибок и p95 менее 500 мс.

### Полный acceptance-профиль проекта

Подготовить каталог:

```bash
.venv/bin/python -m scripts.prepare_catalog_load \
  --manifest test-results/catalog-load-fixture.json
```

Запустить профиль:

```bash
.venv/bin/python -m scripts.catalog_load \
  --base-url http://localhost:8000 \
  --stand-config test-results/catalog-load-stand.json \
  --output test-results/catalog-load.json
```

В CI используется профиль:

- 500 туров;
- 20 RPS;
- 120 секунд прогрева;
- 600 секунд измерения;
- p95 не более 500 мс;
- отсутствие ошибок и потерь.

Workflow запускается через GitHub Actions:

[Service level acceptance workflow](https://github.com/Akira-vs96/SaparTravel/actions/workflows/service-level-acceptance.yml)

## 11. UAT: как провести и что показать

### Сценарии

В [uat-protocol.md](uat-protocol.md) есть 10 сценариев:

1. поиск тура;
2. выбор даты, участников и услуги;
3. оформление и тестовая оплата;
4. отмена и возврат;
5. обязательное поле;
6. доступ к чужой заявке;
7. права поставщика;
8. отказ без причины;
9. ru/kk/en и мобильный экран;
10. обращение в поддержку.

### Технический прогон

```bash
docker compose up --build -d
curl --fail http://localhost:8000/api/v1/health

.venv/bin/python tests/browser_smoke.py \
  --base-url http://localhost:5173

.venv/bin/python tests/browser_localization.py \
  --base-url http://localhost:5173 \
  --api-url http://localhost:8000

.venv/bin/python tests/browser_roles_visual.py \
  --base-url http://localhost:5173
```

Для `browser_roles_visual.py` нужны временные доступы администратора:

```bash
export E2E_ADMIN_EMAIL='admin@example.test'
export E2E_ADMIN_PASSWORD='use-a-private-demo-password'
```

Замените значения на доступы из приватной demo-конфигурации. Не сохраняйте
пароль в репозитории.

Подробное описание находится в [uat-execution.md](uat-execution.md).

### Решение PO

Так как PO и разработчик — один человек, итог оформлен в
[uat-owner-acceptance.md](uat-owner-acceptance.md).

Формулировка для защиты:

> Технический UAT-прогон выполнен автоматически на отдельном demo/QA
> стенде. Самоприёмка проведена владельцем продукта. Независимая команда
> заказчика не участвовала.

Учебная симуляция находится в
[docs/labs/lab-11/practice/](../labs/lab-11/practice/), но её нельзя выдавать
за реальный внешний UAT.

## 12. Postmortem и дефекты

Postmortem:

[docs/qa/postmortem.md](postmortem.md)

Инцидент: frontend получил HTTP 200 с `null` или HTML вместо ожидаемого JSON,
что ранее приводило к JavaScript-ошибке.

В postmortem есть:

- хронология;
- влияние;
- системные факторы;
- что сработало;
- три corrective actions;
- владельцы и сроки;
- ссылки на backlog.

Связанные задачи:

- [#35](https://github.com/Akira-vs96/SaparTravel/issues/35);
- [#36](https://github.com/Akira-vs96/SaparTravel/issues/36);
- [#37](https://github.com/Akira-vs96/SaparTravel/issues/37).

Сейчас задачи закрыты как выполненные в режиме self-review владельца
продукта. Это не означает независимое внешнее review.

## 13. Runbook и передача в эксплуатацию

Runbook:

[docs/ops/runbook.md](../ops/runbook.md)

В нём описаны:

- запуск;
- health-check;
- просмотр логов;
- миграции;
- backup;
- restore;
- обновление;
- откат;
- диагностика.

Передача в эксплуатацию:

[docs/ops/handoff.md](../ops/handoff.md)

Основные команды:

```bash
docker compose ps
docker compose logs --tail=50 api
curl --fail http://localhost:8000/api/v1/health
```

Backup:

```bash
bash scripts/backup_db.sh
```

Restore в отдельную базу:

```bash
docker compose exec -T db createdb -U sapar sapartravel_restore
docker compose exec -T db pg_restore \
  -U sapar \
  -d sapartravel_restore \
  --no-owner \
  --no-acl \
  < backups/FILE.dump
```

## 14. Что показать преподавателю за 5 минут

1. Открыть этот файл и показать карту артефактов.
2. Открыть [test-plan.md](test-plan.md).
3. Показать `29 passed` или результаты из
   [verification-results.md](../verification-results.md).
4. Показать [uat-protocol.md](uat-protocol.md) и
   [uat-owner-acceptance.md](uat-owner-acceptance.md).
5. Показать [postmortem.md](postmortem.md) и закрытые Issues #35–#37.
6. Запустить:

   ```bash
   docker compose ps
   curl --fail http://localhost:8000/api/v1/health
   ```

7. Открыть `http://localhost:3001` и показать Uptime Kuma.
8. Показать [runbook.md](../ops/runbook.md) и
   [handoff.md](../ops/handoff.md).

## 15. Честные ограничения

- Независимая команда заказчика не участвовала: выполнена self-acceptance.
- Учебная UAT-симуляция не является реальным пользовательским сеансом.
- Uptime Kuma требует первого ручного создания мониторов через веб-интерфейс.
- k6 добавлен как локальный smoke; полный исторический acceptance-профиль
  проекта выполнялся собственным Python-скриптом в CI.
- Три клиента на одном CI-хосте не являются тремя независимыми внешними
  узлами доступности.
- Внешний production SLA нельзя выводить из локального Docker-прогона.

## 16. Распределение выступления на 4 участников

Рекомендуемая последовательность выступления: аналитика и критерии →
управление качеством и UAT → backend и данные → frontend и эксплуатация.
Каждый участник показывает только свою зону, но все используют один общий
документ как навигацию.

### 1. Абинсериков Нурасыл

**Роль:** Product Owner, Fullstack & Backend-разработчик.  
**Основная зона:** бизнес-результат, самоприёмка, backend и интеграция.

#### Что говорить

> Я Product Owner проекта и отвечаю за то, чтобы техническая реализация
> соответствовала бизнес-сценариям. Также я реализовал backend/fullstack
> часть. Поэтому я показываю, как требования превращаются в API, бизнес-правила
> и итоговое решение о самоприёмке.
>
> В UAT мы проверяем не отдельный HTTP-ответ, а полный пользовательский путь:
> поиск тура, выбор участников и услуг, расчёт KZT, бронирование, оплата,
> отмена и возврат. По текущему автоматизированному прогону все 10 сценариев
> имеют PASS. Так как Product Owner и разработчик — один человек, это
> self-acceptance, а не независимый UAT другой команды.

#### Какие файлы показывать

1. [docs/qa/uat-owner-acceptance.md](uat-owner-acceptance.md) — решение PO о самоприёмке.
2. [docs/qa/uat-protocol.md](uat-protocol.md) — 10 UAT-сценариев.
3. [docs/qa/test-plan.md](test-plan.md) — бизнес-правила и quality gates.
4. [backend/tests/](../../backend/tests/) — API, интеграционные и PostgreSQL-тесты.
5. [docs/verification-results.md](../verification-results.md) — фактические результаты.
6. [backend/app/](../../backend/app/) — backend/API-реализация.

#### Что запустить

```bash
docker compose up --build -d
curl --fail http://localhost:8000/api/v1/health
```

Для показа backend-тестов:

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/sapartravel_test \
  ../.venv/bin/python -m pytest -q
cd ..
```

#### На чём сделать акцент

- бизнес-ценность продукта;
- корректность KZT-расчётов;
- права доступа и запрет доступа к чужим данным;
- транзакции, конкуренция и идемпотентность;
- честное отличие self-acceptance от независимого UAT.

### 2. Айдар Елнара

**Роль:** Бизнес-аналитик, Системный аналитик, Scrum-мастер.  
**Основная зона:** требования, критерии приёмки, процесс и управление качеством.

#### Что говорить

> Я отвечаю за связь между бизнес-требованиями и проверяемыми критериями.
> Для каждой функции определены ожидаемый результат и условие прохождения.
> Поэтому команда проверяет не только наличие функции, но и её пригодность
> для пользователя.
>
> В плане тестирования описана пирамида: основную массу составляют быстрые
> API и интеграционные тесты, затем идут сквозные browser-проверки, отдельные
> нагрузочные и recovery-профили, а UAT подтверждает бизнес-пригодность.
>
> Качество контролируется quality gates по фазам: требования, разработка,
> интеграция, приёмка и эксплуатация. Чем позже найден дефект, тем дороже его
> исправление, поэтому переход на следующую фазу разрешается только при
> выполнении критериев.

#### Какие файлы показывать

1. [docs/qa/test-plan.md](test-plan.md) — стратегия, пирамида и quality gates.
2. [docs/qa/uat-protocol.md](uat-protocol.md) — критерии 10 сценариев.
3. [docs/qa/uat.md](uat.md) — порядок передачи и решения о приёмке.
4. [docs/ops/handoff.md](../ops/handoff.md) — quality gates передачи.
5. [docs/requirements/](../requirements/) — требования и NFR.
6. [docs/sow-sla-slo-sli.md](../sow-sla-slo-sli.md) — договорённости по SLA/SLO/SLI.

#### Что запустить или показать

Фактические результаты:

```bash
cat docs/verification-results.md
```

Быстрая проверка структурных evidence-тестов:

```bash
.venv/bin/python -m pytest -q \
  tests/course/test_evidence.py \
  tests/test_service_operations.py
```

Ожидаемый результат:

```text
29 passed
```

#### На чём сделать акцент

- критерии прохождения сформулированы заранее;
- UAT-сценариев 10, то есть больше требуемых 8;
- дефект имеет severity, priority, владельца и срок;
- self-acceptance обозначена честно;
- процесс качества — управленческая функция, а не только тестирование.

### 3. Баекеева Бибінұр

**Роль:** Product Manager, Database Developer, Frontend-разработчик.  
**Основная зона:** пользовательский интерфейс, мультиязычность, данные и
эксплуатационная готовность приложения.

#### Что говорить

> Я отвечаю за frontend и database-направление. Показываю, что пользователь
> может пройти основные сценарии в интерфейсе, что интерфейс работает на трёх
> языках и разных размерах экрана, а данные сохраняются после перезапуска.
>
> Мы проверяем ru, kk и en, размеры 360, 768 и 1440 пикселей, отсутствие
> горизонтального скролла, ошибки JavaScript и управление клавиатурой.
> Также проверяется, что платёжные данные PAN/CVC не сохраняются в storage.

#### Какие файлы показывать

1. [tests/browser_smoke.py](../../tests/browser_smoke.py) — основной путь туриста.
2. [tests/browser_localization.py](../../tests/browser_localization.py) —
   мультиязычность и платёжные сценарии.
3. [tests/browser_visual.py](../../tests/browser_visual.py) — визуальные проверки.
4. [tests/browser_roles_visual.py](../../tests/browser_roles_visual.py) —
   роли, кабинеты и клавиатура.
5. [frontend/src/](../../frontend/src/) — frontend-реализация.
6. [backend/app/](../../backend/app/) — backend-модели, миграции и работа с базой данных.
7. [docs/qa/accessibility-security.md](accessibility-security.md) — evidence НФТ.

#### Что запустить

```bash
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python tests/browser_localization.py \
  --base-url http://localhost:5173 \
  --api-url http://localhost:8000
.venv/bin/python tests/browser_visual.py \
  --base-url http://localhost:5173
.venv/bin/python tests/browser_roles_visual.py \
  --base-url http://localhost:5173
```

#### На чём сделать акцент

- три языка: ru/kk/en;
- адаптивность 360/768/1440;
- сохранение формы при переключении языка;
- accessibility-проверки `Tab`, `Shift+Tab`, `Escape`;
- запрет хранения PAN/CVC;
- защита от повторной оплаты: backend Idempotency-Key, уникальная БД-операция
  и сохранение ключа в sessionStorage до терминального результата;
- сохранение данных после restart и корректность миграций.

### 4. Бердебек Әмір

**Роль:** IT Project Manager, QA-инженер, Delivery Manager.  
**Основная зона:** тестовая стратегия, дефект-менеджмент, postmortem, нагрузка,
мониторинг и передача в эксплуатацию.

#### Что говорить

> Я отвечаю за QA-процесс, delivery и эксплуатационную готовность. Показываю,
> как дефект проходит от обнаружения до corrective action, как проводится
> postmortem без поиска виноватого и как система передаётся в эксплуатацию.
>
> В postmortem разобран случай HTTP 200 с некорректным телом ответа. Причина
> описана через поведение системы и недостаток тестового покрытия, а не через
> виновного человека. Для инцидента сформулированы три действия, владельцы и
> сроки. Сейчас они закрыты через self-review владельца продукта.
>
> Для эксплуатации есть runbook, SLO/SLI, backup/restore, Uptime Kuma,
> нагрузочный smoke на k6 и полный acceptance-профиль в CI.

#### Какие файлы показывать

1. [docs/qa/postmortem.md](postmortem.md) — хронология, влияние и corrective actions.
2. [docs/ops/runbook.md](../ops/runbook.md) — запуск, диагностика, backup/restore.
3. [docs/ops/service-levels.md](../ops/service-levels.md) — SLI/SLO и error budget.
4. [docs/ops/monitoring-setup.md](../ops/monitoring-setup.md) — Uptime Kuma.
5. [docs/ops/handoff.md](../ops/handoff.md) — передача в эксплуатацию.
6. [load/k6/catalog-health.js](../../load/k6/catalog-health.js) — k6.
7. [.github/workflows/service-level-acceptance.yml](../../.github/workflows/service-level-acceptance.yml)
   — CI нагрузки и recovery.

#### Что запустить

Uptime Kuma и сервисы:

```bash
docker compose up --build -d
docker compose ps
curl --fail http://localhost:8000/api/v1/health
```

k6:

```bash
k6 run \
  -e BASE_URL=http://localhost:8000 \
  -e K6_RATE=20 \
  -e K6_DURATION=30s \
  load/k6/catalog-health.js
```

Bruno:

```bash
bruno run api/bruno --env Local
```

#### На чём сделать акцент

- severity и priority дефектов;
- конкретные corrective actions;
- отсутствие поиска виноватого;
- SLO/error budget как правило принятия решений;
- health-check, логи, мониторинг и runbook;
- ограничения локального стенда и отличие CI от production SLA.

## 17. Общая последовательность защиты

### Шаг 1 — Айдар Елнара

Показывает требования, тестовую стратегию и критерии приёмки.

### Шаг 2 — Абинсериков Нурасыл

Показывает бизнес-сценарии, backend/API и решение PO о самоприёмке.

### Шаг 3 — Баекеева Бибінұр

Показывает frontend, языки, адаптивность, accessibility и данные.

### Шаг 4 — Бердебек Әмір

Показывает postmortem, defect-management, нагрузку, мониторинг и runbook.

### Финальная фраза команды

> Мы заранее спроектировали не только разработку, но и приёмку и эксплуатацию:
> определили quality gates, автоматизировали проверки, подготовили UAT,
> разобрали инцидент, добавили runbook и эксплуатационные проверки. Внешняя
> команда-заказчик не участвовала, поэтому UAT оформлен как self-acceptance
> Product Owner и явно отделён от независимого приёма.
