# Расчёты проекта

[ЛЗ6 notebook](lab-6-monte-carlo.ipynb) исполнен с чистого ядра на фактических
закрытиях issues Flask за 26 полных недель. [Источник](../data/labs/lab-06/provenance.json)
содержит период, IDs и hashes; 11 нулевых недель сохранены. Это внешний темп,
не измеренная скорость SaparTravel. Старый учебный notebook сохранён в
[архиве](../docs/labs/lab-06/archive/lab-6-monte-carlo-2026-10-09.ipynb).

10 000 прогонов, seed 42, два графика, даты и ограничения; расчёт также
доступен CLI в scripts.course.forecast. Сравнение с SP ждёт фактического покера.
Воспроизведение: из корня проекта запустить nbconvert --execute либо Restart
Kernel / Run All. Зависимости документов/графиков отделены в
[scripts/course/requirements.txt](../scripts/course/requirements.txt).
