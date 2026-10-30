# GitHub Project SaparTravel

[Открыть Project](https://github.com/users/Akira-vs96/projects/2) ·
[Политики работы](../project-board-workflow.md) ·
[Реестр работ](plan.json) · [Повторное чтение API](evidence/current.json) ·
[CSV, 81 работа](evidence/items-2026-10-31.csv) ·
[Результаты проверки](evidence/verification-2026-10-31.json)

Реестр связывает функции сайта с исходными issues, реализацией, проверками
и лабораторными. Он описывает состояние на 31.10.2026. Исторические снимки
ЛЗ9 сохраняются отдельно и не переписываются при актуализации доски.

## Представления

| Представление | Для чего |
|---|---|
| [Kanban Dashboard](https://github.com/users/Akira-vs96/projects/2/views/1) | Функции, дефекты и технические задачи текущей проверки по статусам |
| [Функции — реализовано](https://github.com/users/Akira-vs96/projects/2/views/2) | Добавленные возможности сайта с Implementation=Implemented |
| [Приёмка и проверки](https://github.com/users/Akira-vs96/projects/2/views/3) | FOR TEST/Review, основания проверки и следующий шаг |
| [Ошибки](https://github.com/users/Akira-vs96/projects/2/views/4) | Дефекты с критериями воспроизведения и текущим состоянием |
| [Лабораторные 1–15](https://github.com/users/Akira-vs96/projects/2/views/5) | Отчёт каждой ЛЗ и оставшиеся требования исходной методички |
| [Внешние зависимости](https://github.com/users/Akira-vs96/projects/2/views/6) | SMTP, банковский шлюз, UAT, инфраструктура и эксплуатация |
| [Портфель WSJF](https://github.com/users/Akira-vs96/projects/2/views/7) | Десять инициатив ЛЗ14 с числовым рейтингом и исходными компонентами в описании |
| [Бэклог](https://github.com/users/Akira-vs96/projects/2/views/8) | Возможности и инициативы, которые ещё не выбраны в активную работу |
| [Реестр всех работ](https://github.com/users/Akira-vs96/projects/2/views/9) | Все карточки и заполненные поля без фильтра |

## Что означает готовность

`Implementation`: Implemented — реализация существует; Partial — готова часть;
Not started — реализации нет; Prepared — подготовлен комплект документов ЛЗ.
`Verification`: Automated — выполнены приведённые автоматические проверки;
Documented — проверены документы/артефакты; Needs check — нужна отдельная
проверка; External — нужны доступы, решение или участие внешней стороны.
Закрытие issue не выводится автоматически из результата тестов.

Числовое поле WSJF округляется только при публикации до восьми знаков
после запятой: больший масштаб GitHub отклоняет. Исходные компоненты и
полный результат формулы сохраняются в реестре и расчёте ЛЗ14.

У восстановленного после сверки статуса нет выдуманной исторической даты.
Изменения статусов фиксируются GitHub в момент операции. Переклассификация
карточек не означает проведённый спринт, review или рост скорости команды.
Поля Owner/Size/Review date относятся к передаче и плану проверки, а не
измеренным трудозатратам или подтверждённой доступности участников.

## Обновление

Сначала изменить реестр по фактическому коду, тестам или решению принимающего.
Для новой работы использовать уникальный key; существующую историю сохранять
через issue. Указать положительный и отрицательный/ограничивающий критерии.
Источники должны существовать внутри репозитория.

```bash
# Чтение и список расхождений без изменений в GitHub
.venv/bin/python -m scripts.course.project_sync --output test-results/project-preview.json

# Применение явного реестра и повторная проверка
.venv/bin/python -m scripts.course.project_sync --apply --check --output docs/projects/evidence/current.json

# Только проверка уже опубликованного состояния
.venv/bin/python -m scripts.course.project_sync --check --output test-results/project-check.json

# Пересобрать локальный дашборд из актуального снимка
.venv/bin/python -m scripts.course.dashboard
```

Нужен авторизованный GitHub CLI с доступом к репозиторию и Project.
Доступы остаются внутри gh. Скрипт сохраняет исходный текст issue и меняет
только свой отмеченный раздел; повторный запуск использует существующую
карточку по issue/key. Дубликат идентификатора или неполный API-ответ
останавливает операцию. Автоматические удаления, смена приватности и
массовое закрытие issues не выполняются.

## Графики Insights

Сохранённые представления выше создаются через API самого GitHub Project.
Графики Insights настраиваются отдельно в авторизованном веб-интерфейсе:
[создание](https://docs.github.com/en/issues/planning-and-tracking-with-projects/viewing-insights-from-your-project/creating-charts)
и [конфигурация](https://docs.github.com/en/issues/planning-and-tracking-with-projects/viewing-insights-from-your-project/configuring-charts).
Для графиков подходят Area с группировкой Implementation, Kind со Status,
Priority с Implementation, Lab со Status и Owner с текущей очередью.
Отсутствующая веб-авторизация не заменяется публичным доступом к приватному Project.
