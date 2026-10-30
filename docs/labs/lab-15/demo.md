# Резервная демонстрация

[Скачать и открыть видео](evidence/browser-demo.webm) — 20,08 с, WebM,
1440×1000, около 2,4 MB. Запись реально получена из Chromium на отдельном
PostgreSQL 17 стенде. Пользователи и карточные реквизиты синтетические;
деньги не списывались. Видео воспроизводится локально без сервера и интернета.

Показан автоматизированный smoke: языки и фильтр → регистрация → избранное →
заявка с услугами и проверкой суммы → тестовая оплата → отмена/возврат →
административные сценарии → мобильная навигация и ошибка API. Переходы быстрые;
для объяснения можно ставить видео на паузу. Это резерв фактического запуска,
а не запись человеческой речи или проведённой защиты.

[Протокол](evidence/demo-run.json) содержит SHA исходного теста, commit,
SHA-256 видео и проверку воспроизведения. Использован неизменённый
[сквозной сценарий](../../../tests/browser_smoke.py). Главный прогон всех восьми
сценариев сохранён отдельно в [ЛЗ11](../lab-11/evidence/browser.json).

## Повторная запись

Сначала запустить отдельный синтетический стенд по шагам browser job
[CI](../../../.github/workflows/ci.yml) и передать его актуальные
E2E_ADMIN_EMAIL/E2E_ADMIN_PASSWORD через окружение. Повторный seed намеренно
не заменяет пароль существующего администратора. Нужен Chromium Playwright.

Из корня проекта, для стенда http://127.0.0.1:5173:

```bash
.venv/bin/python - <<'RECORDER'
from pathlib import Path
import runpy
from playwright.sync_api import Browser, BrowserType
output = Path('test-results/video').resolve()
output.mkdir(parents=True, exist_ok=True)
new_context, launch, close = Browser.new_context, BrowserType.launch, Browser.close
def recorded(self, **kwargs):
    kwargs.update(record_video_dir=str(output), record_video_size={'width': 1440, 'height': 1000})
    return new_context(self, **kwargs)
def paced(self, **kwargs):
    kwargs['slow_mo'] = 200
    return launch(self, **kwargs)
def finish(self, **kwargs):
    for context in self.contexts:
        context.close()
    return close(self, **kwargs)
Browser.new_context, BrowserType.launch, Browser.close = recorded, paced, finish
runpy.run_path('tests/browser_smoke.py')['run']('http://127.0.0.1:5173')
RECORDER
```

Публиковать запись только после успешного сценария и проверки её содержимого.
Живая командная репетиция, 90-секундный рассказ и защита ещё не проведены.
