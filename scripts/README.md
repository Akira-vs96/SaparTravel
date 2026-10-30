# Автоматизация SaparTravel

Команды запускать из корня репозитория; секреты передаются через приватное
окружение. Общие инструкции: [README](../README.md).

| Область | Инструменты | Документ |
|---|---|---|
| Приложение | setup_env.py, backup_db.sh | [runbook](../docs/ops/runbook.md) |
| SLI/эксплуатация | availability_probe/report, catalog_load, database_recovery, ops_jobs, monthly_service_report | [SLI](../docs/ops/service-levels.md) |
| Курс | course.github_facts/metrics/forecast/finance/ai/weekly_status/prioritize/audit/dashboard | [15 лабораторных](../docs/labs/README.md) |
| Исторический пакет ЛЗ8 | create_lab8_package/create_lab8_kzt/convert/validate | [история и исправления](../docs/labs/lab-08/corrections.md) |

Текущая исправленная модель: python -m scripts.course.finance. Старые генераторы
содержат baseline 23.10.2026 и воспроизводят исторический пакет, включая выявленные
вручную заданные значения; не использовать их результат как исправленную версию.

Дополнительные зависимости графиков/документов — [course/requirements.txt](course/requirements.txt).
Рабочее приложение их не импортирует. Команды курса читают факты и создают
артефакты; не отправляют отчёты и не меняют рабочую БД. Голоса/подписи/UAT
автоматически не создаются.
