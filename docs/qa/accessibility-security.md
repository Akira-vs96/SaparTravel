# НФТ: accessibility и security evidence

## Accessibility

Проверяемый минимум для инкремента:

1. `tests/browser_visual.py` проверяет 45 сочетаний публичного интерфейса:
   ru/kk/en и 360/768/1440 px, отсутствие горизонтального скролла и ошибок JS.
2. `tests/browser_roles_visual.py` проверяет 9 сочетаний кабинетов и размеров.
3. В модальных окнах проверяется порядок `Tab`/`Shift+Tab` и закрытие через
   `Escape`.
4. `tests/browser_localization.py` проверяет, что переключение языка не теряет
   заполненную форму, а ошибки и документы локализованы.

Это автоматизированный smoke-контур, а не заявление о полном WCAG-аудите.
Перед публичным запуском нужен ручной проход клавиатурой и проверка скринридером.

## Security

- API-права и доступ к чужим ресурсам покрыты `backend/tests/` и browser
  management/engagement сценариями.
- `npm audit --audit-level=high` выполняется в CI.
- PAN/CVC не сохраняются в storage, БД или логах; это проверяет
  `browser_localization.py`.
- Секреты берутся из окружения и не попадают в коллекции Bruno, отчёты или
  публичный frontend.

Команда проверки:

```bash
python -m unittest discover -s tests -p 'test_*.py' -q
npm --prefix frontend audit --audit-level=high
```
