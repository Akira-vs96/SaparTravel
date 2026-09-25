# Служебные команды

- `python3 scripts/setup_env.py` — создаёт `.env` с уникальными секретами, сохраняя уже существующий файл.
- `bash scripts/backup_db.sh` — резервная копия PostgreSQL из Docker Compose в `backups/`.

Запускать из корня проекта. Секреты в вывод команд не попадают. Восстановление и эксплуатация описаны в [runbook](../docs/ops/runbook.md).
