"""Render lab navigation and step traceability from the reviewed manifest."""
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LABELS = {"verified": "Проверено", "documented": "Документ готов", "partial": "Частично",
          "requires-human": "Нужны люди", "blocked": "Нужны внешние данные"}


def main():
    manifest = json.loads((ROOT / "docs/labs/manifest.json").read_text())
    index = ["# 15 лабораторных SaparTravel", "",
             "Аудит по исходной методичке от 30.10.2026. У каждой работы собственный раздел; общие документы имеют один основной экземпляр.", "",
             "[Архитектура документов и сайта](../architecture.md) · [Машинный реестр](manifest.json) · [Дашборд](dashboard.html) · [Проверка полноты](evidence/audit.json)", "",
             "«Документ готов» означает наличие результата проектирования, а не проведённое интервью, согласование или приёмку. Отсутствующие факты не заменяются примерами.", "",
             "| ЛЗ | Результат | Проверено / документ готов | Осталось подтверждений |", "|---|---|---:|---:|"]
    for lab in manifest["labs"]:
        counts = Counter(r["status"] for r in lab["steps"])
        ready = counts["verified"] + counts["documented"]
        index.append(f"| {lab['number']:02d} | [{lab['title']}](lab-{lab['number']:02d}/README.md) | {ready}/{len(lab['steps'])} | {len(lab['steps'])-ready} |")
        path = ROOT / lab["report"]
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# ЛЗ {lab['number']}. {lab['title']}", "", "[Все лабораторные](../README.md) · [Архитектура](../../architecture.md)", "",
                 "## Результат и границы", "", lab["findings"], "", "## Артефакты", ""]
        for entry in lab["artifacts"]:
            import os
            relative = Path(os.path.relpath(ROOT / entry["path"], path.parent)).as_posix()
            lines.append(f"- [{entry['label']}](<{relative}>)")
        heading = "Каждый шаг методички — реальные подтверждения" if lab.get("simulation") else "Каждый шаг методички"
        trace_note = ("Учебный вариант полностью разобран в [отдельном отчёте](simulation/README.md). Ниже сохранён аудит фактической истории; модельные события не заменяют реальные подтверждения."
                      if lab.get("simulation") else "Полная формулировка, номер абзаца источника и доказательства находятся в реестре. Нумерация сохранена.")
        lines += ["", "## Воспроизведение", "", "```bash", *lab["commands"], "```", "",
                  "## " + heading, "", trace_note, "",
                  "| ID | Требование | Состояние | Результат / что осталось |", "|---|---|---|---|"]
        for row in lab["steps"]:
            brief = row["text"][:100].replace("|", "/") + ("…" if len(row["text"]) > 100 else "")
            lines.append(f"| {row['id']} | {brief} | {LABELS[row['status']]} | {row['note'].replace('|','/')} |")
        lines += ["", "## Передача", "", "Использование ИИ: Codex подготовил код, расчёты и черновики документов; источники и реальные запуски перечислены выше. Люди проверяют исходные допущения, личный вклад и принимают результат самостоятельно."]
        path.write_text("\n".join(lines) + "\n")
    index += ["", "## Команды", "", "```bash", ".venv/bin/python -m scripts.course.audit --output docs/labs/evidence/audit.json",
              ".venv/bin/python -m scripts.course.audit --require-complete --output test-results/course-complete.json",
              ".venv/bin/python -m scripts.course.dashboard --serve", "```", "",
              "Первый запуск проверяет целостность комплекта. Второй требует закрытия всех действий и возвращает ненулевой код при неподтверждённых человеческих событиях. Дашборд открывается на http://127.0.0.1:18088.", "",
              "Общие внешние зависимости: конкретный заказчик, кейсы преподавателя, интервью/покер/ретроспективы, ручные замеры, независимая разметка и внешний UAT. Доступ преподавателя и публичность ссылок подтверждаются отдельно от проверки локальных файлов."]
    (ROOT / "docs/labs/README.md").write_text("\n".join(index) + "\n")


if __name__ == "__main__":
    main()
