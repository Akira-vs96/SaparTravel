# Мониторинг демо-стенда

## Uptime Kuma

В Compose добавлен сервис `uptime-kuma` с постоянным volume
`uptime_kuma_data`. Запуск:

```bash
python3 scripts/setup_env.py --demo
docker compose up --build -d
docker compose ps
```

Открыть http://localhost:3001, создать локального администратора и добавить
монитор типа HTTP(s):

- URL: `http://api:8000/api/v1/health` (если монитор создан внутри Compose);
- интервал: 60 секунд;
- timeout: 5 секунд;
- ожидаемый HTTP-код: 200.

Для проверки frontend добавьте второй монитор с URL
`http://web/` или публичным HTTPS URL. Данные Uptime Kuma хранятся только в
его volume и не коммитятся в Git.

Uptime Kuma подтверждает доступность, но не заменяет логи, метрики, трейсы,
нагрузочные тесты и внешние независимые точки SLI-A.

## Доказательство настройки

После создания мониторов сохраните скриншот dashboard и дату последнего
successful check в передаче эксплуатации. Не сохраняйте пароль или cookie.
