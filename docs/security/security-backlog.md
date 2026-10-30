# Security backlog — меры ЛЗ 7

30.10.2026 три меры перенесены в настоящий GitHub Project. Статус Review:
код и доказательства подготовлены, независимая проверка ещё не завершена.
Owner для triage — Akira-vs96; назначения других участников не выдуманы.
Исторические сроки 23–30.10 заменены предлагаемым сроком проверки 06.11.2026;
это не подтверждение своевременного завершения первоначального плана.

| ID / задача | Мера и критерий завершения | Owner / срок | Статус | Риск |
|---|---|---|---|---|
| [B-01](https://github.com/Akira-vs96/SaparTravel/issues/32) | Trivy/Gitleaks: JSON, отказ при секрете/HIGH/CRITICAL, точные исключения | Akira-vs96 / 06.11.2026 | Review | R-03, R-16 |
| [B-02](https://github.com/Akira-vs96/SaparTravel/issues/33) | Аудит: actor, action, object, timestamp и request ID; тест двух операций | Akira-vs96 / 06.11.2026 | Review | R-13 / Repudiation |
| [B-03](https://github.com/Akira-vs96/SaparTravel/issues/34) | Auth 429 и нагрузка 500 туров / 20 RPS / 600 с / p95 ≤500 мс; указать пределы limiter | Akira-vs96 / 06.11.2026 | Review | R-08, R-20 / DoS |

[Доска](https://github.com/users/Akira-vs96/projects/2) закрыта; наличие ссылок не
доказывает доступ преподавателя. [Машинный реестр передачи](../labs/evidence/handoff.json)
сохраняет IDs карточек. До Done нужны зелёный CI и второй проверяющий.
Распределённый rate limit и внешняя эксплуатационная инфраструктура ещё не
реализованы. Текущий [отчёт сканирования](security-scan-report.md) указывает
точную область и сохранённые находки.
