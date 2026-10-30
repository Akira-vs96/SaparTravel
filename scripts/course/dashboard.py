"""Build a standalone project dashboard from recorded evidence, never invented metrics."""
import argparse
from collections import Counter
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative):
    path = ROOT / relative
    return json.loads(path.read_text()) if path.is_file() else None


def render():
    project = read("docs/projects/evidence/current.json") or {}
    facts = project or read("docs/labs/evidence/github-2026-10-30.json") or {}
    items = project.get("items", [])
    features = [row for row in items if row.get("kind") == "Feature"]
    project_audit = project.get("audit", {})
    audit = read("docs/labs/evidence/audit.json") or {}
    flow = read("docs/labs/lab-09/evidence/flow.json") or {}
    dora = read("docs/labs/lab-10/evidence/dora.json") or {}
    security = read("docs/labs/lab-07/evidence/2026-10-31/summary.json") or {}
    planning = read("docs/labs/evidence/planning.json") or {}
    finance = read("docs/labs/lab-08/evidence/finance-validation.json") or {}
    exercises = read("docs/labs/evidence/practice-audit.json") or {}
    panels = [
        ("Вехи", "Заказчик", {"лабораторных": audit.get("labs"), "требований": audit.get("requirements"),
                              "функций в Project": len(features) if items else None,
                              "реализовано функций": sum(row.get("implementation") == "Implemented" for row in features) if items else None,
                              "закрытых историй функций": sum(row.get("status") == "Done" for row in features) if items else None,
                              "полнота Project проверена": project_audit.get("passed"),
                              "весь курс принят": audit.get("course_complete"), "UAT заказчика": "ожидается",
                              "учебных разборов": exercises.get("labs"), "шагов в учебном комплекте": exercises.get("requirements"),
                              "учебные разборы не подтверждают участие людей": True}),
        ("Поток", "Команда", {"периоды": [{"throughput": r["throughput"], "cycle mean": r["cycle_mean_days"],
                                           "cycle p85": r["cycle_p85_days"]} for r in flow.get("periods", [])],
                               "текущие статусы Project": project_audit.get("status_counts"),
                               "Review ≤3": project_audit.get("review_limit_passed"),
                               "источник периодов": "исторические переходы GitHub; история неполная",
                               "сверка статусов": "административная; не измерение скорости спринта"}),
        ("DORA", "Команда", {"частота деплоев/неделю": dora.get("deployment_frequency_per_week"),
                              "lead time, часы": dora.get("lead_time_median_hours"),
                              "доля неудачных изменений, %": dora.get("change_failure_rate_percent"),
                              "восстановление, минуты": dora.get("recovery_median_minutes"),
                              "CI в историческом расчёте": dora.get("ci_runs"),
                              "последний проверенный CI": project.get("ci_url")}),
        ("Бюджет", "Заказчик", {"план, KZT / 12 месяцев": finance.get("annual_base_kzt"),
                                 "лимит с резервами, KZT": finance.get("funding_limit_kzt"),
                                 "факт затрат": None, "факт трудозатрат": None,
                                 "источник": "финансовая модель ЛЗ8; допущения не являются платежами"}),
        ("Риски", "Заказчик", {"EMV известных рисков, часы": planning.get("risk_emv_hours"),
                                "резерв WBS, часы": planning.get("baseline_risk_reserve_hours"),
                                "разрыв резерва, часы": planning.get("risk_reserve_gap_hours"),
                                "проверка сканеров": security.get("passed"), "проверка внешнего SLA": "ожидается"}),
        ("Зависимости", "Заказчик", {"открытых задач GitHub на дату снимка": sum(r["state"] == "open" for r in facts.get("issues", [])),
                                      "зарегистрировано работ": len(items) if items else None,
                                      "виды работ": dict(Counter(row.get("kind", "Unknown") for row in items)),
                                      "внешние зависимости": [row["title"] for row in items if row.get("kind") == "Dependency"],
                                      "внешние точки и HTTPS": "нужна инфраструктура",
                                      "календарь/приёмка/разметка": "нужны решения людей"}),
    ]
    cards = "".join(f'<section class="panel" data-audience="{audience}"><h2>{escape(title)}</h2><p>{audience}</p><pre>{escape(json.dumps(data,ensure_ascii=False,indent=2).replace("null", "\"нет данных\""))}</pre></section>' for title, audience, data in panels)
    labs = "".join(f'<a href="lab-{i:02d}/README.md">ЛЗ {i:02d}</a>' for i in range(1,16))
    project_url = project.get("project", {}).get("url", "https://github.com/users/Akira-vs96/projects/2")
    views = "".join(f'<a href="{escape(project_url)}/views/{row["number"]}">{escape(row["name"])}</a>' for row in project.get("views", []))
    feature_rows = "".join(f'<tr><td><a href="https://github.com/Akira-vs96/SaparTravel/issues/{row["content"]["number"]}">{escape(row["title"])}</a></td>'
                           f'<td>{escape(row.get("area", ""))}</td><td>{escape(row.get("implementation", ""))}</td><td>{escape(row.get("verification", ""))}</td>'
                           f'<td>{escape(row.get("status", ""))}</td></tr>' for row in features)
    captured = project.get("captured_at_utc", "30.10.2026 — исторический снимок")
    return f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SaparTravel — лабораторные и факты</title><style>
body{{font:16px system-ui;margin:auto;max-width:1200px;padding:24px;color:#15332e;background:#f7f7f1}}h1{{font-size:32px}}
nav{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}}a,button{{color:#075c50;background:white;border:1px solid #b5ccc5;padding:10px;border-radius:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:16px}}.panel{{min-width:0;background:white;border:1px solid #d4dfdb;border-radius:12px;padding:20px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 monospace}}button{{cursor:pointer}}button:focus,a:focus{{outline:3px solid #ea9f35}}.feature-register{{margin-top:24px;background:white;padding:16px;border-radius:12px}}.table-scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:12px;border-bottom:1px solid #d4dfdb}}td a{{border:0;padding:0;background:transparent}}summary{{cursor:pointer;font-weight:700}}
</style><h1>SaparTravel: 15 лабораторных и функции сайта</h1><p>Снимок GitHub: {escape(captured)}. Исторические измерения потока приведены отдельно. «Нет данных» сохраняется явно.</p>
<nav aria-label="Лабораторные">{labs}</nav><nav aria-label="Учебный комплект"><a href="course-completion.md">15 учебных разборов</a><a href="submission.md">Настоящая сдача и подтверждения</a></nav><nav aria-label="Адресат"><button onclick="filter('all')">Все панели</button><button onclick="filter('Заказчик')">Заказчику</button><button onclick="filter('Команда')">Команде</button></nav>
<nav aria-label="GitHub Project">{views}</nav><main class="grid">{cards}</main>
<details class="feature-register" open><summary>Функции сайта: {len(features)} карточек</summary><div class="table-scroll"><table><thead><tr><th>Функция</th><th>Область</th><th>Реализация</th><th>Проверка</th><th>Этап</th></tr></thead><tbody>{feature_rows}</tbody></table></div></details>
<script>function filter(a){{document.querySelectorAll('.panel').forEach(p=>p.hidden=a!=='all'&&p.dataset.audience!==a)}}</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=18088)
    args = parser.parse_args()
    directory = ROOT / "docs/labs"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "dashboard.html").write_text(render())
    print("Dashboard written to docs/labs/dashboard.html", flush=True)
    if args.serve:
        from functools import partial
        server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(SimpleHTTPRequestHandler, directory=str(directory)))
        server.serve_forever()


if __name__ == "__main__":
    main()
