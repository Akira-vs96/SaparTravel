# Передача в эксплуатацию

## Условия передачи

| Gate | Обязательное доказательство | Решение |
|---|---|---|
| G1 Код | backend tests, frontend build, migrations check | Release owner |
| G2 Приёмка | заполненный UAT-протокол и список открытых замечаний | Заказчик |
| G3 Надёжность | load/recovery JSON и backup restore | Infrastructure owner |
| G4 Наблюдаемость | Uptime Kuma monitor, логи API/worker, health endpoint | Operations |
| G5 Поддержка | календарь, канал заявок, P1/P2/P3 SLA и escalation | Support owner |

Незакрытый блокирующий дефект или отсутствие решения заказчика переводит
релиз в `blocked`; зелёный CI сам по себе не является актом приёмки.

## Что передаётся

- [runbook](runbook.md): запуск, диагностика, backup/restore, обновление и
  откат;
- [service-levels](service-levels.md): SLI/SLO, error budget и календарь
  поддержки;
- [monitoring-setup](monitoring-setup.md): Uptime Kuma для демо-стенда;
- API Swagger на `/docs` и коллекция [Bruno](../../api/bruno/);
- приватные доступы, секреты и DSN — только через согласованный менеджер
  секретов, не через Git или учебные отчёты.

## Обучение и дежурство

Перед активацией SLA ответственный оператор должен выполнить health-check,
просмотреть логи, найти текущий release SHA и пройти backup/restore drill в
отдельной базе. Дежурный использует runbook, регистрирует инцидент и назначает
Incident Commander для P1/P2. После восстановления проводится безвинный
postmortem, а действия заносятся в tracker с владельцем и сроком.

Дата передачи, участники, ссылки на подтверждённые мониторы и решение
заказчика заполняются фактическими сторонами; разработчик не подписывает их
за заказчика.
