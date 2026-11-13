# Локальный прогон UAT

Дата прогона: 2026-11-13. Контур: отдельный demo/QA Compose, seeded test data.

Это воспроизводимый технический acceptance-прогон команды, а не подписанный
заказчиком внешний UAT. Принимающая другая команда не присутствовала, поэтому
решение заказчика и внешняя подпись не выдумываются.

## Команды

```bash
set -euo pipefail

docker info >/dev/null
docker compose up --build -d
curl --fail http://localhost:8000/api/v1/health
.venv/bin/python tests/browser_smoke.py --base-url http://localhost:5173
.venv/bin/python tests/browser_localization.py \
  --base-url http://localhost:5173 --api-url http://localhost:8000
.venv/bin/python tests/browser_roles_visual.py --base-url http://localhost:5173
```

Перед запуском `browser_roles_visual.py` задайте доступы временного
демо-администратора в текущем shell:

```bash
export E2E_ADMIN_EMAIL='admin@example.test'
export E2E_ADMIN_PASSWORD='use-a-private-demo-password'
```

Значения должны соответствовать администратору, созданному в вашей
демо-конфигурации. Не записывайте пароль в Git, Markdown или логи.

Если `docker info` сообщает `Cannot connect to the Docker daemon` или
`/var/run/docker.sock` отсутствует, сначала запустите Docker Engine:

```bash
sudo systemctl start docker
docker info
```

Если Docker Desktop используется вместо systemd, запустите Docker Desktop и
повторите `docker info`. Только после успешного `docker info` запускайте
Compose и browser-тесты.

## Результат

| Область | Результат | Доказательство |
|---|---|---|
| Основной путь туриста | PASS при успешном завершении команды | `test-results/` и `verification-results.md` |
| ru/kk/en и мобильный экран | PASS при успешном завершении команды | `browser_localization.py` |
| Роли и клавиатура | PASS при успешном завершении команды | `browser_roles_visual.py` |
| Внешний заказчик | НЕ ПОДТВЕРЖДЕНО | Нужен наблюдатель другой команды |

Замечания регистрируются отдельными issue с severity, priority, владельцем и
сроком. Автоматический PASS не означает принятие от имени заказчика.
