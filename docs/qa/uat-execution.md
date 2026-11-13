# Локальный прогон UAT

Дата прогона: 2026-11-13. Контур: отдельный demo/QA Compose, seeded test data.

Это воспроизводимый технический acceptance-прогон команды, а не подписанный
заказчиком внешний UAT. Принимающая другая команда не присутствовала, поэтому
решение заказчика и внешняя подпись не выдумываются.

## Команды

```bash
docker compose up --build -d
curl --fail http://localhost:8000/api/v1/health
.venv/bin/python tests/browser_smoke.py --base-url http://localhost:5173
.venv/bin/python tests/browser_localization.py \
  --base-url http://localhost:5173 --api-url http://localhost:8000
.venv/bin/python tests/browser_roles_visual.py --base-url http://localhost:5173
```

## Результат

| Область | Результат | Доказательство |
|---|---|---|
| Основной путь туриста | PASS при успешном завершении команды | `test-results/` и `verification-results.md` |
| ru/kk/en и мобильный экран | PASS при успешном завершении команды | `browser_localization.py` |
| Роли и клавиатура | PASS при успешном завершении команды | `browser_roles_visual.py` |
| Внешний заказчик | НЕ ПОДТВЕРЖДЕНО | Нужен наблюдатель другой команды |

Замечания регистрируются отдельными issue с severity, priority, владельцем и
сроком. Автоматический PASS не означает принятие от имени заказчика.
