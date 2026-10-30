"""Build a standalone project dashboard from recorded evidence, never invented metrics."""
import argparse
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative):
    path = ROOT / relative
    return json.loads(path.read_text()) if path.is_file() else None


def render():
    facts = read("docs/labs/evidence/github-2026-10-30.json") or {}
    audit = read("docs/labs/evidence/audit.json") or {}
    flow = read("docs/labs/lab-09/evidence/flow.json") or {}
    dora = read("docs/labs/lab-10/evidence/dora.json") or {}
    security = read("docs/labs/lab-07/evidence/2026-10-30/summary.json") or {}
    planning = read("docs/labs/evidence/planning.json") or {}
    finance = read("docs/labs/lab-08/evidence/finance-validation.json") or {}
    panels = [
        ("Вехи", "Заказчик", {"лабораторных": audit.get("labs"), "требований": audit.get("requirements"),
                              "весь курс принят": audit.get("course_complete"), "UAT заказчика": "ожидается"}),
        ("Поток", "Команда", {"периоды": [{"throughput": r["throughput"], "cycle mean": r["cycle_mean_days"],
                                           "cycle p85": r["cycle_p85_days"]} for r in flow.get("periods", [])],
                               "источник": "переходы GitHub; история неполная"}),
        ("DORA", "Команда", {"частота деплоев/неделю": dora.get("deployment_frequency_per_week"),
                              "lead time, часы": dora.get("lead_time_median_hours"),
                              "доля неудачных изменений, %": dora.get("change_failure_rate_percent"),
                              "восстановление, минуты": dora.get("recovery_median_minutes"),
                              "CI отдельно": dora.get("ci_runs")}),
        ("Бюджет", "Заказчик", {"план, KZT / 12 месяцев": finance.get("annual_base_kzt"),
                                 "лимит с резервами, KZT": finance.get("funding_limit_kzt"),
                                 "факт затрат": None, "факт трудозатрат": None,
                                 "источник": "финансовая модель ЛЗ8; допущения не являются платежами"}),
        ("Риски", "Заказчик", {"EMV известных рисков, часы": planning.get("risk_emv_hours"),
                                "резерв WBS, часы": planning.get("baseline_risk_reserve_hours"),
                                "разрыв резерва, часы": planning.get("risk_reserve_gap_hours"),
                                "проверка сканеров": security.get("passed"), "проверка внешнего SLA": "ожидается"}),
        ("Зависимости", "Заказчик", {"открытых задач GitHub на дату снимка": sum(r["state"] == "open" for r in facts.get("issues", [])),
                                      "внешние точки и HTTPS": "нужна инфраструктура",
                                      "календарь/приёмка/разметка": "нужны решения людей"}),
    ]
    cards = "".join(f'<section class="panel" data-audience="{audience}"><h2>{escape(title)}</h2><p>{audience}</p><pre>{escape(json.dumps(data,ensure_ascii=False,indent=2).replace("null", "\"нет данных\""))}</pre></section>' for title, audience, data in panels)
    labs = "".join(f'<a href="lab-{i:02d}/README.md">ЛЗ {i:02d}</a>' for i in range(1,16))
    return f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SaparTravel — лабораторные и факты</title><style>
body{{font:16px system-ui;margin:auto;max-width:1200px;padding:24px;color:#15332e;background:#f7f7f1}}h1{{font-size:32px}}
nav{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}}a,button{{color:#075c50;background:white;border:1px solid #b5ccc5;padding:10px;border-radius:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:16px}}.panel{{min-width:0;background:white;border:1px solid #d4dfdb;border-radius:12px;padding:20px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 monospace}}button{{cursor:pointer}}button:focus,a:focus{{outline:3px solid #ea9f35}}
</style><h1>SaparTravel: 15 лабораторных</h1><p>Снимок 30.10.2026. Источники и ограничения доступны в отчётах. «Нет данных» сохраняется явно.</p>
<nav aria-label="Лабораторные">{labs}</nav><nav aria-label="Адресат"><button onclick="filter('all')">Все панели</button><button onclick="filter('Заказчик')">Заказчику</button><button onclick="filter('Команда')">Команде</button></nav>
<main class="grid">{cards}</main><script>function filter(a){{document.querySelectorAll('.panel').forEach(p=>p.hidden=a!=='all'&&p.dataset.audience!==a)}}</script></html>'''


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
