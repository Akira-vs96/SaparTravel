"""Build the LZ8 submission from explicit assumptions, without accessing production.

Run: .venv/bin/python scripts/create_lab8_package.py
Dependencies: python-docx, openpyxl, python-pptx (document tooling only).
The financial workbook is recalculated and validated separately with LibreOffice.
"""

from __future__ import annotations

import csv
import html
import json
import math
import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as col
from pptx import Presentation
from pptx.dml.color import RGBColor as SlideColor
from pptx.util import Inches, Pt as SlidePt


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "lab-8"
OUT.mkdir(parents=True, exist_ok=True)
DATE = "23.10.2026"
MAU = [0, 0, 0, 100, 200, 400, 600, 800, 1000, 1300, 1600, 2000]
MONTHS = ["09.2026", "10.2026", "11.2026", "12.2026", "01.2027", "02.2027",
          "03.2027", "04.2027", "05.2027", "06.2027", "07.2027", "08.2027"]
SOURCES = [
    ("S01", "DigitalOcean: официальный калькулятор", "https://www.digitalocean.com/pricing/calculator", "Расчет без входа и платежей; параметры и снимок — evidence/"),
    ("S02", "DigitalOcean: Droplets", "https://www.digitalocean.com/pricing/droplets", "Basic Regular: 2 vCPU / 4 GiB / 80 GiB — $24; мониторинг 1 vCPU / 1 GiB — $6/мес."),
    ("S03", "DigitalOcean: Managed Databases", "https://www.digitalocean.com/pricing/managed-databases", "PostgreSQL Standard Basic Regular, 1 vCPU / 2 GiB, минимум 30 GiB, без standby: $30,45/мес."),
    ("S04", "DigitalOcean: Backups Pricing", "https://docs.digitalocean.com/products/backups/details/pricing/", "Daily Basic: 30% от стоимости Droplet; $24 × 30% = $7,20/мес."),
    ("S05", "DigitalOcean: Spaces", "https://www.digitalocean.com/pricing/spaces-object-storage", "$5/мес.: 250 GiB, 1 TiB исходящего трафика; сверх лимита $0,02/GiB хранения и $0,01/GiB трафика."),
    ("S06", "Hetzner: изменение тарифов с 15.06.2026", "https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/", "AX42-1, FSN/HEL: $117,10/мес., setup $59; без IPv4 и налогов. Берется обычный тариф, не limited offering."),
    ("S07", "Hetzner: IP pricing", "https://docs.hetzner.com/general/infrastructure-and-availability/ipv4-pricing/", "Primary IPv4 dedicated: $1,90/мес., setup $0."),
    ("S08", "Hetzner: AX42", "https://www.hetzner.com/dedicated-rootserver/ax42/", "Ryzen 7 PRO 8700GE, 64 GB ECC, 2 × 512 GB NVMe, 1 Gbit/s; конфигурация для открытого стека."),
    ("S09", "Google SRE: Implementing SLOs", "https://sre.google/workbook/implementing-slos/", "Методическая основа: пользовательский сценарий, SLI, измеримый SLO и пересмотр целей."),
    ("S10", "Google SRE: Error Budget Policy", "https://sre.google/workbook/error-budget-policy/", "Методическая основа: error budget = 1 − SLO; при исчерпании приоритет получают надежность и безопасность."),
]

INPUTS = [
    ("Стоимость разработки и настройки приложения", 18000, "USD, разово", "Бизнес-кейс ЛЗ3; top-down оценка, не 171 ч × $10"),
    ("Миграция/сверка данных", 1500, "USD, разово", "Бизнес-кейс ЛЗ3"),
    ("Обучение пользователей", 800, "USD, разово", "Бизнес-кейс ЛЗ3"),
    ("Вывод старого ручного процесса", 500, "USD, разово", "Бизнес-кейс ЛЗ3; перенос в месяц запуска"),
    ("Поддержка приложения и пользователей", 500, "USD/мес. после запуска", "6000/12 из ЛЗ3; без администрирования хостинга"),
    ("Продвижение", 100, "USD/мес. после запуска", "Учебное допущение ЛЗ8, не оферта"),
    ("Переменные расходы на активного туриста", 0.20, "USD/MAU/мес.", "Допущение: обработка и сверка операций; инфраструктура отдельно"),
    ("Средняя стоимость реализованного заказа", 500, "USD/заказ", "Допущение, не цена демонстрационного каталога"),
    ("Доля MAU с одним реализованным заказом/мес.", 0.03, "доля", "Допущение; уже после отмен и неявок"),
    ("Комиссия поставщика", 0.08, "доля GMV", "Гипотеза договора: ручное выставление счета, без онлайн-оплаты"),
    ("Ставка дополнительного администрирования", 10, "USD/ч", "Допущение ЛЗ3; полная стоимость часа с начислениями"),
    ("Часы администрирования cloud", 4, "ч/мес.", "Допущение, не круглосуточное дежурство"),
    ("Часы администрирования own", 12, "ч/мес.", "Допущение"),
    ("Часы администрирования rent", 8, "ч/мес.", "Допущение"),
    ("Домен/DNS", 1, "USD/мес.", "Сметный лимит $12/год, не подтвержденная оферта регистратора"),
    ("Риск-резерв RAID", 63.2, "ч", "docs/security/raid.md: сумма EMV"),
    ("Управленческий резерв", 16, "ч", "docs/security/raid.md: отдельно от EMV"),
    ("Плановый объем WBS", 171, "ч", "docs/plan/wbs.md"),
    ("Чистая емкость команды", 204, "ч", "docs/plan/wbs.md; 4 человека, учебный календарь"),
    ("Срок распределения разовых затрат", 36, "мес.", "Управленческий расчет, не бухгалтерская амортизация"),
    ("Собственный сервер", 2000, "USD, CAPEX", "Смета, не коммерческое предложение: 4+ ядра, 16+ GB, зеркальные SSD"),
    ("UPS и сеть", 500, "USD, CAPEX", "Сметное допущение"),
    ("Средняя мощность owned вместе с сетью/UPS", 0.08, "kW", "Допущение: измерить ваттметром"),
    ("Электроэнергия", 0.15, "USD/kWh", "Сметное допущение, не местный тариф"),
    ("Интернет с публичным IP owned", 30, "USD/мес.", "Сметное допущение"),
    ("Обслуживание/запчасти owned", 10, "USD/мес.", "Сметное допущение; утилизация без дохода от продажи"),
    ("Настройка cloud", 4, "ч, разово", "Дополнительно к настройке приложения в ЛЗ3"),
    ("Настройка own", 12, "ч, разово", "Допущение"),
    ("Настройка rent", 8, "ч, разово", "Допущение; setup провайдера добавляется отдельно"),
    ("Плата SLA за сопровождение", 500, "USD/мес.", "Та же статья поддержки; не добавляется к расходам второй раз"),
]
I = {name: row for row, (name, *_rest) in enumerate(INPUTS, 2)}


def money(value):
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def typeset(text):
    text = re.sub(r"(?<=[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі])(?=\d)", " ", str(text))
    return re.sub(r"(?<=\d)(?=(?:MAU|RPS|SP|Critical|High|ч\b|мин\b|месяц|тур|секрет))", " ", text)


def make_model():
    cloud = 24 + 30.45 + 7.20 + 5 + 6 + 1 + 40
    own = 120 + 0.08 * 24 * 365 / 12 * 0.15 + 30 + 5 + 6 + 1 + 10
    rent = 117.10 + 1.90 + 5 + 6 + 1 + 80
    months = []
    running = 0
    for n, (month, users) in enumerate(zip(MONTHS, MAU), 1):
        lines = [6000 if n <= 3 else 0, 1500 if n == 3 else 0,
                 800 if n == 3 else 0, 500 if n == 4 else 0,
                 40 if n == 1 else 0, cloud,
                 500 if n >= 4 else 0, 100 if n >= 4 else 0, users * 0.2]
        cost = round(sum(lines), 2)
        revenue = users * 500 * 0.03 * 0.08
        running = round(running + revenue - cost, 2)
        months.append(dict(month=n, calendar=month, mau=users, lines=lines,
                           cost=cost, revenue=revenue, profit=round(revenue-cost, 2),
                           cumulative=running, cpu=cost/users if users else None))
    base = round(sum(m["cost"] for m in months), 2)
    annual_revenue = sum(m["revenue"] for m in months)
    fixed = cloud + 500 + 100
    initial = 18000 + 1500 + 800 + 500 + 40
    cm = 500 * 0.03 * 0.08 - 0.20
    model = dict(cloud=cloud, own=own, rent=rent, months=months, base=base,
                 risk=632, management=160, baseline=base+632, funding=base+792,
                 revenue=annual_revenue, loss=base-annual_revenue,
                 user_months=sum(MAU), fixed=fixed, initial=initial,
                 contribution=cm, operating_be=math.ceil(fixed/cm),
                 full_be=math.ceil((fixed+initial/36)/cm),
                 reserved_be=math.ceil((fixed+(initial+792)/36)/cm),
                 tco_cloud=40+36*cloud, tco_own=2620+36*own,
                 tco_rent=139+36*rent,
                 common_tco=20300+500+18000,
                 peak_deficit=-min(m["cumulative"] for m in months))
    assert sum(MAU) == 8000
    assert round(model["base"], 2) == 29203.80
    assert round(model["tco_cloud"], 2) == 4131.40
    assert model["operating_be"] == 714 and model["full_be"] == 1293
    assert round(model["contribution"], 2) == 1
    return model


def input_ref(index):
    return f"Inputs!$B${index + 1}"


def write_workbook(model):
    wb = Workbook()
    wb.remove(wb.active)
    ws = {n: wb.create_sheet(n) for n in ["Guide", "Inputs", "Tariffs", "Hosting", "Budget12", "Unit", "Sensitivity", "SLO", "Checks", "Sources"]}
    for row in [
        ["ЛЗ8 SaparTravel", "Как использовать модель"],
        ["Версия / дата", f"1.0 / {DATE}"],
        ["Единицы", "USD; налоги и инфляция не включены; опубликованные USD-тарифы без валютной конвертации"],
        ["Статус", "Смета и гипотезы; фактические расходы и коммерческие договоры не подтверждены"],
        ["Горизонт бюджета", "09.2026–08.2027; M1–M3 разработка, запуск до 20.12.2026; первые 4 месяца также план, не факт"],
        ["Редактирование", "Синие значения Inputs, Tariffs и MAU в Budget12 — входы; остальные числа рассчитываются формулами"],
        ["Безубыточность", "Операционная отдельно от распределения разовых затрат на 36 месяцев; рост MAU не равен прибыли первого года"],
        ["Пересчет", "Открыть в Excel/LibreOffice с автоматическим пересчетом. Checks: все разности = 0, дефицит часов = 46,2"],
        ["Оплата", "Учетная запись и платные ресурсы облака не создавались; только публичный калькулятор и тарифы"],
        ["Резервы", "EMV 63,2 ч × $10 = $632; управление 16 ч × $10 = $160; не считаются фактическими расходами"],
        ["Поддержка", "$500/мес. — приложение и пользователи; 4/12/8 ч администрирования хостинга учтены в Hosting отдельно"],
        ["Ограничение мощности", "Прогноз до 2000 MAU, 500 туров, БД до 10 GiB, 20 RPS суммарно; подтвердить нагрузочным тестом"],
        ["TCO", "Hosting: 36 полных месяцев одинакового спроса. Budget12: проект с разработкой и постепенным ростом; горизонты различаются"],
    ]: ws["Guide"].append(row)
    ws["Inputs"].append(["Параметр", "Значение", "Единица", "Основание"])
    for row in INPUTS: ws["Inputs"].append(row)
    tariff_rows = [
        ["Тариф", "USD/мес.", "Источник", "Конфигурация / примечание"],
        ["Cloud application VM", 24, "S02", "Basic Regular 2 vCPU, 4 GiB, 80 GiB SSD"],
        ["Managed PostgreSQL", 30.45, "S03", "Standard Basic Regular 1 vCPU, 2 GiB, 30 GiB, 0 standby"],
        ["Daily backup fraction", .30, "S04", "Доля от application VM; не $0,30"],
        ["Offsite object storage", 5, "S05", "Spaces 250 GiB / 1 TiB; для own/rent вне основного сервера"],
        ["External monitoring VM", 6, "S02", "Basic 1 vCPU, 1 GiB; мониторинг, пробы и логи"],
        ["Rent AX42-1", 117.10, "S06/S08", "Обычный dedicated FSN1/HEL1; 64 GB ECC, 2×512 GB"],
        ["Rent primary IPv4", 1.90, "S07", "Setup $0"],
        ["Rent provider setup", 59, "S06", "Разово, не ежемесячный тариф"],
    ]
    for row in tariff_rows: ws["Tariffs"].append(row)
    H = ws["Hosting"]
    hosting = [
        ["Статья", "Cloud managed", "Собственное", "Open stack dedicated", "Правило"],
        ["Приложение / сервер", "=Tariffs!B2", 0, "=Tariffs!B7", "Доступен весь месяц; demand одинаковый, железо может быть избыточно"],
        ["Managed DB", "=Tariffs!B3", 0, 0, "Для own/rent PostgreSQL на своем узле; лицензия $0"],
        ["Backup VM", "=Tariffs!B2*Tariffs!B4", 0, 0, "Cloud daily image; отдельные логические копии БД — в Spaces"],
        ["Внешние копии / артефакты", "=Tariffs!B5", "=Tariffs!B5", "=Tariffs!B5", "Один лимит на вариант; 7 daily + 4 weekly + 3 monthly при dump ≤ 5 GiB"],
        ["Мониторинг", "=Tariffs!B6", "=Tariffs!B6", "=Tariffs!B6", "Отдельный узел; для cloud другой регион, для остальных другой провайдер"],
        ["Домен/DNS", f"={input_ref(15)}", f"={input_ref(15)}", f"={input_ref(15)}", "$12/год; равномерный accrual в смете"],
        ["Администрирование", f"={input_ref(11)}*{input_ref(12)}", f"={input_ref(11)}*{input_ref(13)}", f"={input_ref(11)}*{input_ref(14)}", "Не включает $500 поддержки приложения"],
        ["Электроэнергия", 0, f"={input_ref(23)}*24*365/12*{input_ref(24)}", 0, "80 W, 365 дней/год; для rent/cloud в цене"],
        ["Интернет / публичный IP", 0, f"={input_ref(25)}", "=Tariffs!B8", "Cloud IPv4 и исходящий трафик в лимите плана"],
        ["Запчасти / обслуживание", 0, f"={input_ref(26)}", 0, "У owned отдельная сметная статья"],
        ["Ежемесячно", "=SUM(B2:B11)", "=SUM(C2:C11)", "=SUM(D2:D11)", "OPEX размещения"],
        ["CAPEX", 0, f"={input_ref(21)}+{input_ref(22)}", 0, "Сервер $2000 + UPS/сеть $500"],
        ["Разовая настройка + setup", f"={input_ref(27)}*{input_ref(11)}", f"={input_ref(28)}*{input_ref(11)}", f"={input_ref(29)}*{input_ref(11)}+Tariffs!B9", "Разовые работы инфраструктуры сверх $18000 приложения"],
        ["TCO размещения, 36 мес.", "=B12*36+B13+B14", "=C12*36+C13+C14", "=D12*36+D13+D14", "Без дисконтирования, инфляции и остаточной стоимости; CAPEX не амортизируется повторно"],
        ["Общие затраты продукта", f"={input_ref(1)}+{input_ref(2)}+{input_ref(3)}+{input_ref(4)}+{input_ref(5)}*36", "=B16", "=B16", "20300 + 500 + 18000 = 38800; без маркетинга и переменной модели"],
        ["Сопоставимый TCO проекта", "=B15+B16", "=C15+C16", "=D15+D16", "Сравнение с ранним baseline ЛЗ3 $46000"],
        ["Разница с ЛЗ3", "=B17-46000", "=C17-46000", "=D17-46000", "Уточнены статьи инфраструктуры; не новый замер ROI"],
        ["Тарифы +30%: TCO размещения", "=(B2+B3+B4+B5+B6)*0.3*36+B15", "=(C5+C6)*0.3*36+C15", "=(D2+D5+D6+D10)*0.3*36+D15", "Стресс только опубликованных ежемесячных тарифов; труд и CAPEX без роста"],
    ]
    for row in hosting: H.append(row)
    B = ws["Budget12"]
    B.append(["Статья"] + [f"M{i} {m}" for i,m in enumerate(MONTHS,1)] + ["12 месяцев"])
    labels = ["MAU туристов", "Разработка", "Миграция данных", "Обучение", "Вывод старого процесса",
              "Разовая настройка hosting", "Размещение и его администрирование", "Поддержка приложения",
              "Продвижение", "Переменные расходы", "Плановые затраты без резервов", "Выручка: комиссия",
              "Поток до резервов", "Накопленный поток", "Стоимость на MAU", "Риск-резерв, распределение",
              "Baseline с рисками", "Управленческий резерв", "Лимит финансирования"]
    for name in labels: B.append([name])
    for j, users in enumerate(MAU, 2):
        c = col(j); n = j-1
        values = {2:users, 3:f"={input_ref(1)}/3" if n <=3 else 0,
                  4:f"={input_ref(2)}" if n==3 else 0, 5:f"={input_ref(3)}" if n==3 else 0,
                  6:f"={input_ref(4)}" if n==4 else 0, 7:"=Hosting!$B$14" if n==1 else 0,
                  8:"=Hosting!$B$12", 9:f"={input_ref(5)}" if n>=4 else 0,
                  10:f"={input_ref(6)}" if n>=4 else 0, 11:f"={c}2*{input_ref(7)}",
                  12:f"=SUM({c}3:{c}11)", 13:f"={c}2*{input_ref(8)}*{input_ref(9)}*{input_ref(10)}",
                  14:f"={c}13-{c}12", 15:f"={c}14" if n==1 else f"={col(j-1)}15+{c}14",
                  16:f'=IF({c}2=0,"N/A",{c}12/{c}2)',
                  17:(f"=ROUND({input_ref(16)}*{input_ref(11)}/3,2)" if n<=2 else
                      f"={input_ref(16)}*{input_ref(11)}-B17-C17" if n==3 else 0),
                  18:f"={c}12+{c}17", 19:f"={input_ref(17)}*{input_ref(11)}" if n==3 else 0,
                  20:f"={c}18+{c}19"}
        for r,value in values.items(): B.cell(r,j,value)
    for r in range(2,21):
        B.cell(r,14, "=M15" if r==15 else '=N12/N2' if r==16 else f"=SUM(B{r}:M{r})")
    U = ws["Unit"]
    unit = [
        ["Показатель", "Значение", "Пояснение"],
        ["Выручка на MAU", f"={input_ref(8)}*{input_ref(9)}*{input_ref(10)}", "$500 × 3% × 8% = $1,20, после отмен"],
        ["Переменные расходы на MAU", f"={input_ref(7)}", "$0,20/мес."],
        ["Вклад MAU", "=B2-B3", "Должен быть >0; иначе конечной точки безубыточности нет"],
        ["Постоянные затраты/мес.", f"=Hosting!B12+{input_ref(5)}+{input_ref(6)}", "Хостинг $113,65 + поддержка $500 + продвижение $100"],
        ["Разовые затраты", f"={input_ref(1)}+{input_ref(2)}+{input_ref(3)}+{input_ref(4)}+Hosting!B14", "$20840; в первом году уже включены в Budget12"],
        ["Разовые / 36", f"=B6/{input_ref(20)}", "Только для зрелой unit-модели; не добавлять повторно в бюджет"],
        ["Операционная безубыточность, MAU", '=IF(B4<=0,"Нет",ROUNDUP(B5/B4,0))', "Рост в пределах подтвержденной мощности"],
        ["Полная безубыточность, MAU", '=IF(B4<=0,"Нет",ROUNDUP((B5+B7)/B4,0))', "С распределением разовых затрат на 36 мес."],
        ["Полная с обоими резервами, MAU", f'=IF(B4<=0,"Нет",ROUNDUP((B5+(B6+{input_ref(16)}*{input_ref(11)}+{input_ref(17)}*{input_ref(11)})/{input_ref(20)})/B4,0))', "Резервы — лимит, не расход"],
        ["MAU для примера", 2000, "Зрелый месяц / M12"],
        ["Операционный CPU", "=B5/B11+B3", "(F + vN) / N"],
        ["Полный CPU", "=(B5+B7)/B11+B3", "(F + vN + I/36) / N"],
        ["Операционная прибыль/мес.", "=B11*B4-B5", "При 2000 MAU"],
        ["Полный результат/мес.", "=B14-B7", "Управленческий показатель"],
        ["Средний CPU первого года", "=Budget12!N12/Budget12!N2", "Деление на 8000 пользователь-месяцев, не на 2000 × 12"],
        ["Средний CPU с рисками", "=Budget12!N18/Budget12!N2", "Baseline / user-months"],
        ["Дефицит первого года", "=Budget12!N12-Budget12!N13", "Это результат, не максимальная потребность в оборотных средствах"],
        ["Пиковый кассовый разрыв", "=-MIN(Budget12!B15:M15)", "До резервов; при поступлении комиссии в том же месяце"],
        ["Чистое финансирование с резервами", f"=B19+{input_ref(16)}*{input_ref(11)}+{input_ref(17)}*{input_ref(11)}", "Gross лимит сметы Budget12!N20 отдельно, без зачета выручки"],
        ["Конверсия безубыточности при 2000 MAU", f"=(B5/B11+B3)/({input_ref(8)}*{input_ref(10)})", "Операционная, при неизменном среднем чеке и комиссии"],
        ["Ставка дисконтирования исходного кейса", 0.15, "Только справочно; TCO здесь недисконтированный"],
        ["Минимальный MAU для покрытия всех затрат за 12 мес.", '=IF(B4<=0,"Нет",ROUNDUP(Budget12!N12/(B2*12),0))', "Справочно: постоянный MAU с M1 при расходах базового прогноза, не точка роста и не динамический сценарий"],
    ]
    # The last row would mix a fixed baseline and a changed user-dependent cost.
    # A valid first-year recovery threshold instead derives from costs excluding vN.
    unit[-1] = ["MAU каждого из 9 рабочих месяцев для окупаемости за год",
                '=IF(B4<=0,"Нет",ROUNDUP((Budget12!N12-Budget12!N11)/(9*B4),0))',
                "Без резервов: N1–N3=0, одинаковый MAU M4–M12; выше 2000 — требует новой оценки мощности"]
    for row in unit: U.append(row)
    S = ws["Sensitivity"]
    for row in [
        ["Сценарий", "Конверсия", "Комиссия", "Расход/MAU", "Вклад/MAU", "Fixed/мес.", "MAU операц.", "MAU полный"],
        ["База", f"={input_ref(9)}", f"={input_ref(10)}", f"={input_ref(7)}"],
        ["Конверсия 2%", .02, f"={input_ref(10)}", f"={input_ref(7)}"],
        ["Конверсия 1%", .01, f"={input_ref(10)}", f"={input_ref(7)}"],
        ["Комиссия 5%", f"={input_ref(9)}", .05, f"={input_ref(7)}"],
        ["Расход/MAU $0,40", f"={input_ref(9)}", f"={input_ref(10)}", .4],
        ["Опубликованные cloud-тарифы +30%", f"={input_ref(9)}", f"={input_ref(10)}", f"={input_ref(7)}"],
        ["Конверсия 0% / комиссии не согласованы", 0, f"={input_ref(10)}", f"={input_ref(7)}"],
    ]: S.append(row)
    for r in range(2,9):
        S.cell(r,5,f"={input_ref(8)}*B{r}*C{r}-D{r}")
        S.cell(r,6,"=Unit!B5+(Hosting!B2+Hosting!B3+Hosting!B4+Hosting!B5+Hosting!B6)*0.3" if r==7 else "=Unit!B5")
        S.cell(r,7,f'=IF(E{r}<=0,"Нет",ROUNDUP(F{r}/E{r},0))')
        S.cell(r,8,f'=IF(E{r}<=0,"Нет",ROUNDUP((F{r}+Unit!B7)/E{r},0))')
    SL = ws["SLO"]
    for row in [
        ["Сценарий", "SLO availability/success", "SLA availability/success", "Минут в месяце", "SLO бюджет, мин.", "SLA бюджет, мин.", "Пример попыток N", "SLO ошибок, floor", "SLA ошибок, floor", "SLO p95 E2E, сек.", "SLA p95 E2E, сек.", "Бюджет медленных >2 сек."],
        ["C1 Каталог/карточка", .999, .995, 43200, None, None, 200000, None, None, 2, 3],
        ["C2 Вход/профиль", .998, .995, 43200, None, None, 20000, None, None, 2, 3],
        ["C3 Отправка заявки/результат", .997, .995, 43200, None, None, 4000, None, None, 2, 3],
    ]: SL.append(row)
    for r in range(2,5):
        for c,f in {5:f"=D{r}*(1-B{r})", 6:f"=D{r}*(1-C{r})", 8:f"=ROUNDDOWN(ROUND(G{r}*(1-B{r}),8),0)",9:f"=ROUNDDOWN(ROUND(G{r}*(1-C{r}),8),0)",12:f"=ROUNDDOWN(G{r}*0.05,0)"}.items(): SL.cell(r,c,f)
    for row in [
        ["Календарных дней", "Минут", "SLO99.9 budget", "SLO99.8 budget", "SLO99.7 budget", "SLA99.5 budget"],
        [28, "=A7*1440", "=B7*(1-$B$2)", "=B7*(1-$B$3)", "=B7*(1-$B$4)", "=B7*(1-$C$2)"],
        [30, "=A8*1440", "=B8*(1-$B$2)", "=B8*(1-$B$3)", "=B8*(1-$B$4)", "=B8*(1-$C$2)"],
        [31, "=A9*1440", "=B9*(1-$B$2)", "=B9*(1-$B$3)", "=B9*(1-$B$4)", "=B9*(1-$C$2)"],
    ]:
        if SL.max_row==4: SL.append([])
        SL.append(row)
    CH = ws["Checks"]
    for row in [
        ["Проверка", "Результат", "Ожидается"],
        ["Год по статьям минус месяцы", "=SUM(Budget12!N3:N11)-Budget12!N12", 0],
        ["Baseline минус план/EMV", f"=Budget12!N18-Budget12!N12-{input_ref(16)}*{input_ref(11)}", 0],
        ["Лимит минус baseline/управление", f"=Budget12!N20-Budget12!N18-{input_ref(17)}*{input_ref(11)}", 0],
        ["Поток = выручка − расходы", "=Budget12!N14-Budget12!N13+Budget12!N12", 0],
        ["Cloud TCO минус статьи", "=Hosting!B15-Hosting!B12*36-Hosting!B13-Hosting!B14", 0],
        ["Own TCO минус статьи", "=Hosting!C15-Hosting!C12*36-Hosting!C13-Hosting!C14", 0],
        ["Rent TCO минус статьи", "=Hosting!D15-Hosting!D12*36-Hosting!D13-Hosting!D14", 0],
        ["Разовые затраты не задвоены", "=SUM(Budget12!N3:N7)-Unit!B6", 0],
        ["Недостающие часы при полном резерве", f"=MAX(0,{input_ref(18)}+{input_ref(16)}+{input_ref(17)}-{input_ref(19)})", 46.2],
        ["Порог: N-1 убыточен", "=IF((Unit!B8-1)*Unit!B4<Unit!B5,0,1)", 0],
        ["Порог: N не убыточен", "=IF(Unit!B8*Unit!B4>=Unit!B5,0,1)", 0],
        ["Полный порог: N-1 убыточен", "=IF((Unit!B9-1)*Unit!B4<Unit!B5+Unit!B7,0,1)", 0],
        ["Полный порог: N не убыточен", "=IF(Unit!B9*Unit!B4>=Unit!B5+Unit!B7,0,1)", 0],
    ]: CH.append(row)
    ws["Sources"].append(["ID", "Источник", "URL", "Проверено", "Использование"])
    for sid,title,url,note in SOURCES: ws["Sources"].append([sid,title,url,DATE,note])
    for sh in wb:
        sh.freeze_panes = "B2"
        sh.sheet_view.showGridLines = False
        sh.auto_filter.ref = sh.dimensions
        sh.sheet_properties.pageSetUpPr.fitToPage = True
        sh.page_setup.orientation = "landscape"
        sh.page_setup.paperSize = sh.PAPERSIZE_A3 if sh.title=="Budget12" else sh.PAPERSIZE_A4
        sh.page_setup.fitToWidth = 1
        sh.page_setup.fitToHeight = 0
        for cell in sh[1]:
            cell.fill = PatternFill("solid", fgColor="123D4A")
            cell.font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        sh.row_dimensions[1].height = 36
        for row in sh.iter_rows(min_row=2):
            sh.row_dimensions[row[0].row].height = 36 if sh.title not in ("Budget12","SLO","Sensitivity") else 30
            for cell in row:
                cell.alignment=Alignment(vertical="center",wrap_text=True)
                is_input = (sh.title in ("Inputs","Tariffs") and cell.column==2) or (sh.title=="Budget12" and cell.row==2 and 2<=cell.column<=13)
                cell.font=Font(name="Calibri",size=10,color="1767B3" if is_input else "25333A")
                if cell.row % 2 == 0: cell.fill=PatternFill("solid",fgColor="EFF5F4")
                if cell.data_type=="f" or isinstance(cell.value,(float,int)): cell.number_format='#,##0.00;[Red]-#,##0.00;0.00'
        sh.column_dimensions["A"].width=48
        for c in range(2,sh.max_column+1): sh.column_dimensions[col(c)].width=21
        sh.print_title_rows="1:1"
    for name,widths in {"Guide":{"B":110},"Inputs":{"C":30,"D":95},"Tariffs":{"D":100},"Hosting":{"E":100},"Unit":{"C":105},"Sources":{"B":50,"C":100,"D":20,"E":110}}.items():
        for c,width in widths.items(): ws[name].column_dimensions[c].width=width
    for r in (4,7,12,16,17): ws["Inputs"].cell(r,2).number_format="0.00"  # numeric assumptions remain explicit
    for r in (10,11): ws["Inputs"].cell(r,2).number_format="0.0%"
    for r in range(2,5):
        SL.cell(r,2).number_format=SL.cell(r,3).number_format="0.0%"
    ws["Unit"]["B21"].number_format="0.00%"
    for r in range(2,9):
        ws["Sensitivity"].cell(r,2).number_format=ws["Sensitivity"].cell(r,3).number_format="0.0%"
    chart = LineChart()
    chart.title="Прогноз затрат и выручки / USD"
    chart.y_axis.title="USD/мес."
    chart.add_data(Reference(B,min_col=2,max_col=13,min_row=12,max_row=13),from_rows=True,titles_from_data=False)
    chart.set_categories(Reference(B,min_col=2,max_col=13,min_row=1,max_row=1))
    chart.width=27;chart.height=11;B.add_chart(chart,"A23")
    chart2=BarChart()
    chart2.title="TCO размещения за 36 месяцев / USD"
    chart2.add_data(Reference(H,min_col=2,max_col=4,min_row=15,max_row=15),from_rows=True)
    chart2.set_categories(Reference(H,min_col=2,max_col=4,min_row=1,max_row=1))
    chart2.width=25;chart2.height=10;H.add_chart(chart2,"A22")
    wb.save(OUT / "SaparTravel_LZ8_Financial_Model.xlsx")


BACKLOG = [
    ("ST-01","Каталог", "Видны опубликованные туры; скрытый тур отсутствует", "3"),
    ("ST-02","Поиск", "Название/направление находят тур; неизвестный запрос дает пустую выдачу", "5"),
    ("ST-03","Фильтры", "Цена и длительность включают границы; несовместимые условия не дают ложных результатов", "5"),
    ("ST-04","Карточка тура", "Есть программа, услуги, выезды и цена; неопубликованный slug недоступен туристу", "8"),
    ("ST-05","Выбор выезда", "Будущий выезд и число участников выбираются; нулевое/отрицательное число отклоняется", "3"),
    ("ST-06","Учет мест", "Последнее место получает одна из конкурентных заявок; переполнение запрещено", "8"),
    ("ST-07","Вход", "Регистрация дает traveler, верный пароль открывает профиль; неверный пароль/JWT отклоняется", "5"),
    ("ST-08","Туры поставщика", "Поставщик создает и редактирует свой тур; чужой изменить нельзя", "8"),
    ("ST-09","Решение по заявке", "Разрешенный статус сохраняется с историей; неверный переход/чужая заявка отклоняется", "8"),
    ("ST-10","История туриста", "Показаны только собственные заявки с суммой и статусом; чужие не раскрываются", "5"),
    ("ST-11","Отмена", "Отмена до поездки освобождает места; начавшийся/чужой тур отменить нельзя", "Не пересчитано"),
    ("ST-12","Публикация", "Снятый с публикации тур исчезает из каталога; турист не может публиковать", "Не пересчитано"),
    ("ST-13","Роли", "Назначение роли доступно admin; последний admin не лишается доступа", "Не пересчитано"),
    ("ST-14","RU/KK/EN", "Основные экраны переключают язык без потери сценария; ключи переводов не показываются", "Не пересчитано"),
    ("ST-15","Очередь поставщика", "Видны заявки только на свои туры; чужие заявки отсутствуют", "Не пересчитано"),
    ("ST-16","Онлайн-оплата", "Вне MVP; критерии задаются отдельным CR", "Вне оценки"),
    ("ST-17","Отзывы", "Вне MVP; критерии задаются отдельным CR", "Вне оценки"),
    ("ST-18","Внешняя синхронизация", "Вне MVP; критерии задаются отдельным CR", "Вне оценки"),
]

NFR = [
    ("NFR-01","Каталог API", "p95 ≤ 500 мс при суммарных 20 RPS и 500 турах", "C1 / 4.2", "Нагрузочный прогон 30 мин.; отчета нет"),
    ("NFR-02","Пользовательский отклик", "p95 ≤ 2 с для C1/C2/C3 на согласованной сети", "C1–C3 / 3.6", "E2E-тайминги; не измерено"),
    ("NFR-03","Мобильная загрузка", "p95 первоначальной загрузки ≤ 3 с, viewport 390 px, 4G 10 Mbps/100 ms RTT", "3.6", "30 холодных открытий; не измерено"),
    ("NFR-04","Доступность", "SLA ≥ 99,5% календарного месяца, каждый C1–C3", "4.2 / 5.4", "Минутные синтетические пробы; не подключены"),
    ("NFR-05","Восстановление приложения", "Обычный рестарт/rollback API ≤ 15 мин. при доступной БД", "5.2", "Замер восстановления; не измерено"),
    ("NFR-06","Резервное копирование", "RPO ≤ 24 ч; ежедневный dump, еженедельный restore-test; DR RTO ≤ 4 ч", "4.2 / 5.4", "Журнал restore; DR RTO — уточнение ЛЗ8"),
    ("NFR-07","Целостность мест", "0 перепродаж при 20 параллельных запросах на последний слот", "3.4", "PostgreSQL integration test; нужен протокол прогона"),
    ("NFR-08","Роли/владение", "100% негативной матрицы доступа дает 401/403/404 без утечки", "3.2 / 3.5", "API-тесты; наличие не равно свежему PASS"),
    ("NFR-09","Пароли", "100% паролей хранятся Argon2, открытых паролей нет", "3.2", "Проверка схемы и auth-тестов"),
    ("NFR-10","Секреты", "0 подтвержденных действующих секретов в репозитории и логах", "4.2", "Gitleaks, разбор 6 находок ЛЗ7"),
    ("NFR-11","Уязвимости", "0 неустраненных подтвержденных exploitable High/Critical к публичному пилоту", "4.2", "Повторный скан; ЛЗ7 содержит 1 Critical/5 High"),
    ("NFR-12","Аудит", "100% административных изменений имеют actor, UTC timestamp, объект и request/event ID", "3.5 / 4.2", "Выборка всех типов admin-операций; не подтверждено"),
    ("NFR-13","Локализация", "100% ключей основных экранов RU/KK/EN заполнены", "3.6", "UI checklist"),
    ("NFR-14","Доступность интерфейса", "360–1440 px без горизонтального скролла; контраст ≥4,5:1; ключевые действия с клавиатуры", "3.6", "Ручная UAT-проверка/инструмент контраста"),
    ("NFR-15","Сопровождение", "Развертывание по README, миграции на пустой БД, CI API/build/E2E успешен", "4.1 / 5.2", "URL CI + commit SHA + лог"),
    ("NFR-16","ПДн и ошибки", "Ошибки без stack trace/секретов; сроки хранения и основание обработки согласованы до реальных данных", "4.2 / 5.4", "Негативные тесты + решение ответственного за ПДн"),
]


def write_csvs(model):
    with (OUT/"budget_12_months.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f,delimiter=";")
        w.writerow(["Месяц","MAU","Разработка","Миграция","Обучение","Вывод старого","Hosting setup","Размещение","Поддержка","Продвижение","Переменные","Всего","Выручка","Поток","Накопленный поток","USD/MAU"])
        for m in model["months"]:
            w.writerow([m["calendar"],m["mau"],*m["lines"],m["cost"],m["revenue"],m["profit"],m["cumulative"],round(m["cpu"],4) if m["cpu"] else "N/A"])
    for filename,headers,rows in [
        ("backlog_baseline.csv",["ID","История","Критерии: позитивный/негативный","SP из ЛЗ6","Приоритет/статус"], [(*r,"Must / к приемке" if i<15 else "После MVP") for i,r in enumerate(BACKLOG)]),
        ("nfr_register.csv",["ID","Требование","Метрика","Трассировка","Проверка/статус"],NFR),
    ]:
        with (OUT/filename).open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f,delimiter=";");w.writerow(headers);w.writerows(rows)


class Report:
    def __init__(self):
        self.doc=Document()
        section=self.doc.sections[0]
        section.top_margin=Cm(1.7);section.bottom_margin=Cm(1.6)
        section.left_margin=Cm(1.8);section.right_margin=Cm(1.6)
        section.page_width=Cm(21);section.page_height=Cm(29.7)
        normal=self.doc.styles["Normal"]
        normal.font.name="DejaVu Sans";normal.font.size=Pt(9)
        normal.paragraph_format.space_after=Pt(5)
        normal.paragraph_format.line_spacing=1.08
        for name,size in [("Title",27),("Heading 1",18),("Heading 2",12),("Heading 3",10)]:
            self.doc.styles[name].font.name="DejaVu Sans"
            self.doc.styles[name].font.size=Pt(size)
            self.doc.styles[name].font.color.rgb=RGBColor.from_string("123D4A")
        header=section.header.paragraphs[0]
        header.text="SaparTravel  /  ЛЗ 8  /  версия 1.0  /  23.10.2026"
        header.style="Caption"
        footer=section.footer.paragraphs[0]
        footer.text="Учебный проект. Подготовлено к защите.  •  "
        fld=OxmlElement("w:fldSimple");fld.set(qn("w:instr"),"PAGE");footer._p.append(fld)
        self.parts=[]
        self.page_calls=0

    def title(self,text):
        text=typeset(text)
        self.doc.add_heading(text,0);self.parts.append(f"<h1>{html.escape(text)}</h1>")

    def h(self,text,level=1):
        text=typeset(text)
        self.doc.add_heading(text,level);self.parts.append(f"<h{level+1}>{html.escape(text)}</h{level+1}>")

    def p(self,text):
        text=typeset(text)
        self.doc.add_paragraph(text);self.parts.append(f"<p>{html.escape(text)}</p>")

    def bullets(self,items):
        items=[typeset(x) for x in items]
        for item in items: self.doc.add_paragraph(item,style="List Bullet")
        self.parts.append("<ul>"+"".join(f"<li>{html.escape(x)}</li>" for x in items)+"</ul>")

    def table(self,headers,rows):
        headers=[typeset(x) for x in headers]
        rows=[[typeset(x) for x in row] for row in rows]
        table=self.doc.add_table(rows=1,cols=len(headers));table.style="Light Shading Accent 1"
        for c,text in zip(table.rows[0].cells,headers): c.text=str(text)
        trPr=table.rows[0]._tr.get_or_add_trPr();repeat=OxmlElement("w:tblHeader");trPr.append(repeat)
        for row in rows:
            cells=table.add_row().cells
            for c,text in zip(cells,row): c.text=str(text)
        for row in table.rows:
            props=row._tr.get_or_add_trPr();avoid=OxmlElement("w:cantSplit");props.append(avoid)
            for c in row.cells:
                for p in c.paragraphs:
                    p.paragraph_format.space_after=Pt(3)
                    p.paragraph_format.space_before=Pt(2)
                    for run in p.runs: run.font.size=Pt(8)
        self.doc.add_paragraph().paragraph_format.space_after=Pt(0)
        self.parts.append("<table><thead><tr>"+"".join(f"<th>{html.escape(str(x))}</th>" for x in headers)+"</tr></thead><tbody>"+"".join("<tr>"+"".join(f"<td>{html.escape(str(x))}</td>" for x in row)+"</tr>" for row in rows)+"</tbody></table>")

    def page(self):
        self.page_calls += 1
        # Keep the cover separate; let the report flow to avoid nearly empty
        # continuation pages after large tables.
        if self.page_calls == 1: self.doc.add_page_break()
        self.parts.append('<div class="section-divider"></div>')

    def save(self):
        self.doc.core_properties.title="SaparTravel — ЛЗ8: SoW, SLA/SLO, бюджет и юнит-экономика"
        self.doc.core_properties.author="Абинсериков Нурасыл / команда SaparTravel"
        self.doc.save(OUT/"SaparTravel_LZ8_Report.docx")
        css="""body{font:15px/1.55 system-ui,sans-serif;color:#25333a;max-width:1150px;margin:40px auto;padding:0 24px}h1,h2,h3{color:#123d4a}h1{font-size:42px}h2{border-top:3px solid #2c8b80;padding-top:20px;margin-top:45px}table{width:100%;border-collapse:collapse;font-size:13px;margin:18px 0}th{background:#123d4a;color:white;text-align:left}td,th{padding:9px;border:1px solid #d4dfdf;vertical-align:top}tr:nth-child(even){background:#eff5f4}a{color:#1767b3}@media print{body{font-size:10pt;margin:0;padding:0}.pagebreak{break-before:page}table{font-size:8pt}tr{break-inside:avoid}h2,h3{break-after:avoid}}"""
        page='<!doctype html><html lang="ru"><meta charset="utf-8"><title>SaparTravel — ЛЗ8</title><style>'+css+'</style><body>'+'\n'.join(self.parts)+'</body></html>'
        (OUT/"SaparTravel_LZ8_Report.html").write_text(page,encoding="utf-8")


def write_report(m):
    r=Report()
    r.title("SaparTravel\nSoW, SLA/SLO и бюджет проекта")
    r.h("Лабораторная работа 8 и рубежный контроль 1",2)
    r.p("Проект: веб-платформа поиска и бронирования туров. Автор: Абинсериков Нурасыл. Команда: Айдар Елнара, Баекеева Бибінұр, Бердебек Әмір. Дата подготовки: 23 октября 2026 года. Версия: 1.0. Валюта: USD.")
    r.p("Статус: законченный учебный пакет для защиты, проект договорных условий и финансовый прогноз. Подписи заказчика, результаты UAT, коммерческие договоры и фактическое соблюдение SLO этим документом не подтверждаются.")
    r.table(["Результат расчета","Значение"],[
        ["Плановые затраты первого года без резервов",f"{money(m['base'])} USD"],
        ["Baseline с рисками / лимит с управленческим резервом",f"{money(m['baseline'])} / {money(m['funding'])} USD"],
        ["Пользователь-месяцев / средняя полная стоимость",f"8000 / {money(m['base']/8000)} USD за MAU-месяц"],
        ["Операционная / полная безубыточность",f"{m['operating_be']} / {m['full_be']} MAU"],
        ["Прогноз комиссии / дефицит первого года",f"{money(m['revenue'])} / {money(m['loss'])} USD"],
        ["TCO размещения, 36 месяцев: cloud / own / rent",f"{money(m['tco_cloud'])} / {money(m['tco_own'])} / {money(m['tco_rent'])} USD"],
    ])
    r.p("Навигация: 1 — исходные данные; 2 — SoW; 3 — SLO/SLA и error budget; 4 — бюджет; 5 — юнит-экономика; 6 — сравнение размещения; 7 — пакет недель 1–8 и защита; 8 — источники. Приложения: Excel с формулами, CSV бюджета/backlog/НФТ, презентация и доказательство расчета в калькуляторе.")
    r.page()
    r.h("1. Основание, допущения и согласование baseline")
    r.p("Основание — существующий репозиторий SaparTravel: README, ADR-002, устав от 25.09.2026, бизнес-кейс ЛЗ3, WBS ЛЗ5, Planning Poker и Monte Carlo ЛЗ6, RAID и результаты сканирования ЛЗ7. Стек: React/Vite, FastAPI, PostgreSQL 17, SQLAlchemy/Alembic, JWT/Argon2, Docker Compose и Nginx. Реальные партнеры и онлайн-платежи не подключены.")
    r.table(["Тип данных","Что принято и как проверять"],[
        ["Подтверждено содержимым репозитория","Есть каталог, роли, заявки, локализация и тесты; наличие кода не доказывает production-надежность."],
        ["Сохраненные исходные оценки","Разработка $18000, данные $1500, обучение $800, поддержка $6000/год, вывод старого процесса $500. Это top-down денежная оценка ЛЗ3, а не перевод WBS в часы по $10."],
        ["Новые допущения ЛЗ8","MAU, конверсия 3%, средний реализованный заказ $500, комиссия 8%, переменный расход $0,20/MAU, продвижение $100/мес. Проверить пилотом и договорами."],
        ["Публичные тарифы","Проверены 23.10.2026, источники S01–S08. Налоги, инфляция, скидки и free credits не включены; используются опубликованные USD-цены."],
        ["Финансовый горизонт","M1 = сентябрь 2026, M12 = август 2027. Весь ряд — план, включая уже прошедшие месяцы; расходов-факт в источниках нет. Запуск до 20.12.2026; декабрьские постоянные расходы заложены за полный месяц консервативно."],
        ["Спрос и мощность","До 2000 активных туристов/мес., 500 туров, БД до 10 GiB, суммарный peak 20 RPS; 70% каталог / 20% вход-профиль / 10% заявки. Это профиль приемочного теста, не доказанная мощность."],
    ])
    r.h("Решения об изменениях, включенные в пакет",2)
    r.table(["ID","Предложенное решение ЛЗ8","Статус"],[
        ["CR-08-01","Уточнить размещение и годовой бюджет по публичным тарифам; расходы hosting $113,65/мес. и разовая настройка $40 заменяют грубый лимит $2400/год.","Подготовлено к утверждению"],
        ["CR-08-02","Для демонстрации брать календарь WBS: 28.09–20.12.2026, инкременты 25.10, 22.11, 20.12. В старом уставе каталог/бронь привязаны к неделям 8/10; это расхождение явно вынесено на согласование.","Не считать старый устав автоматически измененным"],
        ["CR-08-03","Ввести измеримые C1–C3, RTO аварийного восстановления ≤4 ч; рестарт API ≤15 мин. при живой БД остается целью. В старом уставе URL /catalog заменить в проверках на существующий /api/v1/experiences.","Уточнение условий приемки"],
        ["CR-08-04","Комиссию поставщика считать только гипотезой коммерческого пилота с ручными счетами. Разработку биллинга, эквайринга и платежного API не добавлять в MVP.","До договора выручка $0"],
    ])
    r.page()
    r.h("2. Statement of Work — предмет и результаты")
    r.p("Заказчик — владелец продукта SaparTravel; уполномоченный внешний представитель назначается заказчиком. Исполнитель — учебная команда SaparTravel. Внутренний PO и backend: Абинсериков Нурасыл; анализ и Scrum: Айдар Елнара; frontend и БД: Баекеева Бибінұр; QA/Delivery: Бердебек Әмір. Внешний заказчик, владелец эксплуатации и ответственный за ПДн пока не названы: подписи не подменяются именами команды.")
    r.p("Цель: обеспечить путь «найти тур → изучить условия → выбрать выезд → отправить заявку → отследить статус», сократить ручную обработку с 30 до 8 минут и поднять долю обработки за рабочий день с 70% до 95% через 3 месяца после пилота. Эти бизнес-эффекты — гипотезы до замера, не SLA мгновенного ответа API.")
    r.table(["Поставка / WBS","Состав результата","Приемочное доказательство"],[
        ["D1. Baseline / 1.1–2.2","Устав, границы, 18-историйный backlog, НФТ, потоки и RU/KK/EN","PO подтверждает Must-срез ST-01–ST-15; у историй позитивные и негативные критерии"],
        ["D2. API и данные / 3.1–3.4","PostgreSQL, миграции, вход/роли, каталог, выезды, создание и отмена заявки","Миграции на пустой тестовой БД; API-тесты; сумма с сервера; конкурентная бронь без перепродажи"],
        ["D3. Интерфейс и кабинеты / 3.5–3.6","Турист, поставщик, администратор; адаптивность и три языка","E2E по трем ролям; чужие ресурсы недоступны; 360–1440 px"],
        ["D4. Качество / 4.1–4.3","CI, матрица тестов, проверка НФТ, безопасный демонстрационный каталог","Протоколы тестов/нагрузки/безопасности; перенос данных с количеством и контрольными выборками"],
        ["D5. Приемка и передача / 5.1–5.4","Релиз по commit SHA, образы, руководство, обучение, runbook, backup/restore и откат","UAT и акт передачи; владелец эксплуатации воспроизводит запуск и restore без передачи секретов в отчете"],
    ])
    r.h("Границы работ",2)
    r.p("Входят поиск и фильтры, карточки, будущие выезды и остаток мест, регистрация/вход/профиль, избранное, заявка с расчетом суммы на сервере, история/отмена, управление собственными турами и заявками поставщика, управление ролями/каталогом администратором, RU/KK/EN, проверки и эксплуатационная документация. Миграция — согласованный seed/CSV-набор без разработки универсального ETL.")
    r.p("Вне SoW: онлайн-оплата, эквайринг, возвраты денег, реальные API отелей/туроператоров, email/SMS и почтовое восстановление пароля, мобильное приложение, отзывы, рекомендательная система, расширенная аналитика и круглосуточная коммерческая поддержка. Создание заявки не является покупкой или списанием денег; подтверждение поставщиком — отдельное человеческое действие.")
    r.h("План и стоимость поставки",2)
    r.table(["Веха","Дата по WBS","Объем / условие"],[
        ["I1. Каталог и доступ","25.10.2026","74 ч; каталог, фильтры, карточка, вход и миграции"],
        ["I2. Заявки и кабинеты","22.11.2026","52 ч; создание/отмена, статусы, роли, CI"],
        ["I3. Качество и передача","20.12.2026","45 ч; данные, НФТ, UAT, обучение и эксплуатация"],
        ["Цена предмета разработки","$20300","$18000 разработка + $1500 данные + $800 обучение; оплата/приемка по согласованным этапам"],
    ])
    r.p("Финансовая раскладка разработки: $6000 в M1, $6000 в M2, $6000 в M3; данные $1500 и обучение $800 в M3. Вывод старого процесса $500 в M4, настройки хостинга $40 в M1, эксплуатация и продвижение показаны отдельно. Оплата сама по себе не заменяет приемку вехи.")
    r.page()
    r.h("2.1. Порядок приемки и Definition of Done")
    r.bullets([
        "Исполнитель передает релиз-кандидат: commit SHA, версии образов, миграции, перечень выполненных историй, результаты CI и UAT, известные ограничения, инструкции запуска/отката и протокол восстановления.",
        "Заказчик/уполномоченный PO в течение 5 рабочих дней выполняет UAT на отдельном стенде и письменно принимает результат либо возвращает замечания с ID истории, шагами, ожидаемым и фактическим результатом и серьезностью. Молчание не означает приемку.",
        "Блокирующие дефекты: потеря/утечка данных, обход ролей, перепродажа мест, неверная сумма, невозможность входа/заявки. Не должно оставаться открытых Critical/High дефектов; найденные уязвимости анализируются и устраняются/документируются до публичного пилота.",
        "Исполнитель устраняет подтвержденные блокирующие дефекты в согласованный срок, ориентир 3 рабочих дня; повторная приемка за 2 рабочих дня включает затронутые проверки и критический регресс. Изменение согласованных требований проходит через CR.",
        "Общий DoD: все Must-критерии пройдены, PostgreSQL-тесты/сборка/E2E успешны, НФТ проверены протоколами, данные сверены, backup/restore и откат показаны, команда и владелец эксплуатации приняли документацию. Нельзя заменить эти доказательства локальным запуском.",
        "Неблокирующие замечания допускаются только с подписанным списком, владельцем, сроком и отсутствием влияния на основной сценарий. Подписываются акт UAT и акт передачи. Гарантийное исправление отклонений от SoW — 30 календарных дней после приемки, включено в цену разработки; новые функции оплачиваются по CR.",
    ])
    r.table(["Приемочный кейс","Проверяемый ожидаемый результат"],[
        ["UAT-01. Каталог C1","На 500 турах поиск/фильтр возвращают нужный опубликованный тур; скрытый отсутствует, карточка содержит условия"],
        ["UAT-02. Вход C2","Новый пользователь становится traveler; верный пароль открывает профиль, неверный не выдает JWT"],
        ["UAT-03. Заявка C3","Для будущего выезда создается 201 + reference и серверная сумма; заявка видна в своих GET /bookings"],
        ["UAT-04. Конкуренция","20 параллельных запросов на последнее место: не более одного успеха; остальные корректно получают конфликт; мест не меньше нуля"],
        ["UAT-05. Владение и статусы","Турист не видит чужих заявок; поставщик — чужих туров; отмена освобождает места, история содержит изменения"],
        ["UAT-06. Передача","Владелец запускает релиз, восстанавливает отдельную БД из копии, выполняет smoke и демонстрирует откат"],
    ])
    r.h("2.2. Порядок изменений и права на результат",2)
    r.p("Любая сторона оформляет CR с причиной, новой границей/критерием, влиянием на сроки, WBS, бюджет, безопасность и SLO. Аналитик регистрирует запрос, команда оценивает за 2 рабочих дня. PO принимает приоритет и обмен равноценным объемом; изменение денег/финальной даты/обязательств SLA утверждает внешний заказчик/спонсор. После письменного решения обновляются версия baseline, backlog, план, смета и журнал. До решения действует предыдущий согласованный объем. Любой рост суммы требует решения заказчика; отклонение прогноза более 15% дополнительно эскалируется спонсору по уставу.")
    r.p("Неотложные исправления P1/безопасности разрешены владельцу сервиса в пределах согласованного резерва с журналом и последующим разбором на следующий рабочий день. Это правило не разрешает добавлять платежи или внешние интеграции без CR.")
    r.p("Предлагаемые условия прав: после подписания акта и оплаты созданные специально для проекта исходники, схемы БД, миграции, тесты, дизайн и документация передаются заказчику с правом использования, изменения и передачи сопровождения; исполнитель обеспечивает необходимые согласия авторов. До передачи предоставляется право тестирования для UAT. Предшествующие наработки исполнителя перечисляются отдельно и лицензируются в объеме, необходимом для эксплуатации. Сторонние компоненты и изображения остаются под своими лицензиями; к передаче прикладывается реестр зависимостей/лицензий. Данные пользователей не переходят в собственность исполнителя. Публикация проекта или реальных данных в портфолио требует отдельного согласия заказчика. Секреты передаются через защищенный канал, в отчет не включаются.")
    r.p("Поля акта: версия/SHA; D1–D5; результаты UAT-01–06 и НФТ; открытые замечания; дата; ФИО и полномочия принимающего; решение «принято/возврат»; подписи. В текущем учебном пакете эти поля намеренно не подписаны за заказчика.")
    r.page()
    r.h("3. Три сценария: SLI, SLO и SLA")
    r.p("SLO — внутренняя цель команды; SLA — предложенная внешняя граница обязательств, ниже внутренней цели. Окно — календарный месяц по Asia/Almaty; первые неполные дни считаются по фактическому числу минут. Для защиты ниже показан 30-дневный месяц: 43200 минут. Начало SLA — после приемки и включения наблюдаемости, первый полный отчет планируется за январь 2027. На 23.10.2026 ни один показатель не заявлен как достигнутый.")
    r.table(["Сценарий и граница","Успех пользовательского действия","SLO / SLA"],[
        ["C1. Найти и открыть тур\nST-01–04\nGET /api/v1/experiences и /experiences/{slug}","От клика «поиск/фильтр» до корректного списка; от клика карточки до программы/цены/выездов. Обе стадии измеряются, ошибка любой — неуспех C1.","Доступность и доля корректных попыток ≥99,9% / ≥99,5%; p95 E2E ≤2 / ≤3 с; p95 API ≤0,5 / ≤0,75 с"],
        ["C2. Войти и открыть профиль\nST-07\nPOST /auth/login + GET /auth/me","От отправки валидных учетных данных до профиля traveler и успешного чтения /me. Пароли и токены не логируются.","Доступность/корректность ≥99,8% / ≥99,5%; p95 E2E ≤2 / ≤3 с; p95 API ≤0,5 / ≤0,75 с"],
        ["C3. Отправить заявку и получить результат\nST-05/06/10\nPOST /bookings + GET /bookings","От клика подтверждения до reference, верной суммы и заявки в кабинете; либо корректный 409 при реально исчерпанных местах. Для синтетики используются гарантированно доступные тестовые места: ожидается 201 и чтение, затем отмена.","Доступность/корректность ≥99,7% / ≥99,5%; p95 E2E ≤2 / ≤3 с; p95 API ≤0,5 / ≤0,75 с; 0 перепродаж/утечек как отдельный инвариант"],
    ])
    r.h("Как именно считать показатели",2)
    r.bullets([
        "A_i = 1 − bad_minutes_i / eligible_minutes. Каждую минуту отдельный монитор выполняет C1–C3. Неуспешная синтетическая попытка делает эту минуту плохой; шаги идут последовательно, hard timeout всего сценария 10 с. Доступность включает DNS, TLS, frontend, API и БД; один /health не заменяет сценарий.",
        "Q_i = good_attempts_i / eligible_attempts_i. Отдельная метрика реальных попыток: валидные действия в согласованном профиле нагрузки; шаги связаны случайным trace ID без ПДн. Успех включает корректный ожидаемый бизнес-результат. 5xx, timeout, потерянная запись, неверная сумма и 429 для валидного действия в пределах лимита считаются ошибками.",
        "Неверный пароль, невалидный ввод, бот-сканирование, отдельные согласованные нагрузочные тесты и известный отказ сети на устройстве не входят в eligible-метрику основного сценария; причины исключения и количества публикуются. 409 по остаткам не становится успешной продажей и не входит в конверсию 3%, даже если технически корректен. Не исключать все 4xx без разбора.",
        "L_i — распределение времени от действия в браузере до проверенного результата; API измеряется на Nginx от входа запроса до окончания ответа. p95 — nearest rank ceil(0,95N), по всем eligible-попыткам, включая ошибки; timeout учитывается как 10 с. Качество UI подтверждается E2E-метрикой, серверная задержка — отдельным histogram.",
        "Синтетика запускается из внешнего узла, а не из контейнера приложения. Тестовый tenant и выезды исключены из MAU/GMV; после C3 заявка отменяется. Ротация будущих дат и очистка обязательны. Отсутствующую пробу/телеметрию консервативно считать плохой минутой до доказательства, что сбой был только в мониторинге.",
        "Плановые работы, ошибки релиза и отказ облачного провайдера включаются в downtime. Изменение списка исключений требует CR. При N=0 request-метрика не вычисляется, статус N/A; минутная синтетическая метрика продолжает действовать. Проценты и p95 не усредняются между сценариями.",
    ])
    r.p("SLA по доступности считается выполненным, только если каждый A_i и каждый определенный Q_i ≥99,5%; по задержке — если каждый p95 укладывается в свою границу. Для credit берется худший сценарий/метрика; общий инцидент не суммируется трижды. Пример: остановка на 30 минут расходует по 30 минут бюджета C1, C2, C3, а не 90 минут общего сервиса.")
    r.page()
    r.h("3.1. Error budget и управление надежностью")
    r.p("Бюджет времени B_t = (1 − SLO) × T. Бюджет некорректных попыток B_e = floor((1 − SLO) × N). Это два разных знаменателя; число ошибок не переводится автоматически в минуты простоя. N ниже — иллюстрация, не прогноз выручки и не число пользователей.")
    r.table(["Сценарий","Внутренний бюджет / 30 дней","Пример request budget","Внешняя граница SLA"],[
        ["C1, SLO 99,9%","43,2 мин. (43 мин. 12 с)","N=200000 → ≤200 ошибок","99,5% → 216 мин.; при том же N ≤1000 ошибок"],
        ["C2, SLO 99,8%","86,4 мин. (1 ч. 26 мин. 24 с)","N=20000 → ≤40 ошибок","99,5% → 216 мин.; ≤100 ошибок"],
        ["C3, SLO 99,7%","129,6 мин. (2 ч. 9 мин. 36 с)","N=4000 → ≤12 ошибок","99,5% → 216 мин.; ≤20 ошибок"],
    ])
    r.p("При минутных пробах сравнивают без округления процента: допустимы не более floor(B_t) плохих минут — 43, 86 и 129. Для 28 дней SLO-бюджеты равны 40,32 / 80,64 / 120,96 мин., SLA 201,60 мин.; для 31 дня — 44,64 / 89,28 / 133,92 и 223,20 мин. Лист SLO позволяет менять длительность и N.")
    r.p("Latency-budget отдельный: не более floor(0,05N) eligible-попыток дольше 2 с для SLO и дольше 3 с для SLA. Например, при N=4000 — не более 200 медленных попыток на соответствующей границе. Плохая попытка может одновременно расходовать бюджеты успеха и задержки; их нельзя складывать. Нулевая перепродажа, неверные суммы и утечки не имеют разрешенной квоты: любой такой случай — P1 независимо от остатка error budget.")
    r.table(["Состояние","Действие и владелец"],[
        ["Остаток >50%","Обычные релизы по DoD; Бердебек Әмір еженедельно публикует A/Q/p95 и остаток по C1–C3"],
        ["Остаток 20–50%","Не менее половины доступной capacity спринта на надежность; PO пересматривает приоритеты"],
        ["Остаток <20% или budget исчерпан","Заморозить функциональные релизы; разрешены исправления P1 и безопасности до возвращения показателей в цель. Решение владельца сервиса фиксируется в журнале"],
        ["Один инцидент расходует >20% бюджета","Разбор за 2 рабочих дня, причина, меры, владелец и срок; Нурасыл отвечает за backlog исправлений"],
        ["Быстрое сгорание","Алерт burn rate ≥14,4 на окнах 1 ч + 5 мин. либо ≥6 на 6 ч + 30 мин.; 2 подряд проваленные пробы дополнительно создают инцидент"],
    ])
    r.p("Burn rate = фактическая доля плохих минут / (1 − SLO) конкретного сценария. Если плохих минут C1 уже 30, из 43,2 остается 13,2 минуты: SLO еще соблюдается, но новые рисковые релизы останавливаются при переходе ниже 20%. Месячный отчет выдается к 3-му рабочему дню следующего месяца; сырые обезличенные метрики хранятся 90 дней.")
    r.h("3.2. Инциденты, ответственность и компенсация SLA",2)
    r.table(["Приоритет","Регламент поддержки","Владелец"],[
        ["P1: нет входа/заявки, потеря данных, обход ролей","Регистрация автоматически 24×7; подтверждение ≤1 рабочего часа; обход/восстановление ≤4 рабочих часов как целевой регламент. Обновление статуса каждый рабочий час","Нурасыл; координация Әмір; при безопасности — ответственный ИБ"],
        ["P2: частичная деградация, основной путь доступен","Подтверждение ≤4 рабочих часов, план исправления ≤2 рабочих дней","Бибінұр / Нурасыл по компоненту"],
        ["P3: некритичный дефект/консультация","Подтверждение ≤1 рабочего дня; согласование ближайшего спринта","Елнара / PO"],
    ])
    r.p("Рабочее окно: понедельник–пятница 09:00–18:00 Asia/Almaty по согласованному календарю команды; 24×7 дежурство не куплено. Минуты простоя вне рабочего окна продолжают расходовать SLA-budget. Автоперезапуск API ≤15 минут при исправной БД, backup RPO ≤24 ч, аварийный restore RTO ≤4 календарных часов — технические цели, проверяемые до запуска. Авария на 4 часа уже превышает 216 минут SLA; это признанный риск, не исключение. Для более жестких обязательств нужен отдельный CR на репликацию и дежурство.")
    r.p("Компенсация предлагается заказчику за сопровождение платформы, не бесплатному туристу: credit от фактически оплаченной месячной платы $500. Худшее A_i/Q_i: ≥99,5% — 0%; [99,0%;99,5%) — 5% ($25); [95%;99%) — 10% ($50); <95% — 20% ($100). Нарушение любого SLA p95 — credit минимум 5%; берется максимум по основаниям, месячный предел 20%. При бесплатном учебном стенде денежный credit равен $0, сохраняются отчет и исправления. Потребительские права по туру в этот технический SLA не включены.")
    r.p("Заказчик направляет расхождение по отчету в течение 10 рабочих дней; исполнитель сверяет trace/метрики за 5 рабочих дней и применяет credit к следующему счету, либо возвращает согласованную сумму при завершении договора. Кредит за SLO при соблюденном SLA не начисляется. В бюджете это уменьшение выручки исполнителя сопровождения; при расчете расходов владельца продукта кредит консервативно не вычтен заранее.")
    r.page()
    r.h("4. Бюджет на 12 месяцев")
    r.p("Выбран расчетный вариант cloud managed. Все затраты рассматриваются с позиции владельца продукта как экономическая стоимость; бесплатный труд студентов не обнуляет бюджет. Налоги и инфляция вне базовой учебной модели. Регистрация, платежи и создание облачных ресурсов не выполнялись. Домен, электричество, зарплатные ставки, собственное железо и маркетинг — явно помеченные сметные допущения, а не найденные оферты.")
    totals=[sum(x["lines"][j] for x in m["months"]) for j in range(9)]
    names=["Разработка и настройка приложения","Миграция/сверка данных","Обучение","Вывод старого процесса","Настройка cloud","Размещение и его администрирование","Поддержка приложения","Продвижение","Переменные расходы"]
    r.table(["Статья","Правило распределения","За 12 месяцев, USD"],[[name,rule,money(total)] for name,rule,total in zip(names,["$6000 × M1–M3","$1500 в M3","$800 в M3","$500 в M4","4 ч × $10 в M1","$113,65 × 12","$500 × 9, M4–M12","$100 × 9, M4–M12","$0,20 × 8000 MAU-месяцев"],totals)]+[
        ["План без резервов","Сумма статей",money(m["base"])],
        ["Риск-резерв","63,2 ч RAID × $10; M1/M2 $210,67, M3 $210,66",money(m["risk"])],
        ["Baseline с рисками","План + EMV",money(m["baseline"])],
        ["Управленческий резерв","16 ч × $10; зарезервирован M3",money(m["management"])],
        ["Лимит финансирования","Baseline + управление, без зачета выручки",money(m["funding"])],
    ])
    r.p("Риск-резерв $632 распределен с точностью до цента: $210,67 + $210,67 + $210,66. В исходной WBS труд разработки оценен отдельно от цены подрядчика: 171 ч не умножаются на ставку резерва $10. Расход резерва требует записи события/часов, не считается автоматически понесенным расходом.")
    r.table(["Месяц","MAU","Затраты, USD","Комиссия, USD","Поток, USD","USD/MAU"],[
        [x["calendar"],x["mau"],money(x["cost"]),money(x["revenue"]),money(x["profit"]),money(x["cpu"]) if x["cpu"] else "N/A"] for x in m["months"]
    ]+[["Итого","8000 MAU-мес.",money(m["base"]),money(m["revenue"]),money(-m["loss"]),money(m["base"]/8000)]])
    r.p("Разбивка каждой статьи по всем 12 месяцам приведена в Budget12 и budget_12_months.csv. При нулевом MAU стоимость на пользователя не определяется, а затраты разработки остаются в годовом числителе. Средняя стоимость = $29203,80 / 8000 = $3,650475 за пользователь-месяц; с рисками $3,729475; с обоими резервами $3,749475. Среднее арифметическое месячных CPU применять нельзя.")
    r.h("Контроль ресурсов и кассового разрыва",2)
    r.p(f"171 + 63,2 + 16 = 250,2 ч против 204 ч net capacity: дефицит 46,2 ч при полном использовании обоих резервов. Только известные риски дают дефицит 30,2 ч. План реагирования — привлечь до 46,2 ч дополнительной помощи по предположительной ставке $10/ч (до $462 внутри уже заложенных $792, не второй раз поверх сметы) либо уменьшить объем/сдвинуть срок через CR. Наличие денег не подтверждает доступность помощника; до согласования ресурсный baseline не обеспечен.")
    r.p(f"Прогноз выручки — $9600, дефицит первого года без резервов — ${money(m['loss'])}. При поступлении комиссии в том же месяце максимальный кассовый разрыв ${money(m['peak_deficit'])}; с обоими резервами нужно ${money(m['peak_deficit']+792)} чистого финансирования. Это отличается от валового лимита ${money(m['funding'])}. Задержка оплаты поставщиком на месяц увеличивает разрыв: требуется отдельный сценарий оборотного капитала. Без подписанных комиссионных договоров выручка считается нулевой и финансируется весь лимит.")
    r.page()
    r.h("5. Юнит-экономика и точка безубыточности")
    r.p("Единица — один активный турист в календарном месяце (MAU): уникальный авторизованный traveler, совершивший минимум одно осмысленное действие в каталоге/карточке/кабинете. Администраторы, поставщики, тестовые пробы и боты исключаются. В коде полноценной MAU-аналитики пока нет: ниже плановый ряд, который нужно подтвердить обезличенным счетчиком. MAU не равно зарегистрированной базе и не равно числу покупателей.")
    r.p("Монетизация — гипотеза комиссии от поставщика за реально состоявшийся заказ с ручным счетом после сверки. Нет оплаты внутри приложения, а одна только заявка pending не создает дохода. Средний реализованный заказ $500 — сумма всего заказа, а не цена на человека. Конверсия 3% означает ровно один состоявшийся заказ у 3% MAU за месяц и уже учитывает отмены/неявки. GMV не является выручкой SaparTravel.")
    r.table(["Переменная","Расчет","Результат"],[
        ["Выручка на MAU, r","$500 × 0,03 × 0,08","$1,20/мес."],
        ["Переменный расход, v","Допущение обработки/сверки на туриста","$0,20/мес."],
        ["Маржинальный вклад, c","r − v","$1,00/MAU-месяц"],
        ["Постоянные расходы, F","$113,65 hosting + $500 поддержка + $100 продвижение","$713,65/мес."],
        ["Разовые расходы, I","18000 + 1500 + 800 + 500 + 40","$20840"],
        ["Распределение I на 36 месяцев","20840 / 36","$578,888889/мес."],
        ["Операционная безубыточность","ceil(F/c)","714 MAU"],
        ["Полная безубыточность","ceil((F + I/36)/c)","1293 MAU"],
        ["Полная с обоими резервами","ceil((F + (I+792)/36)/c)","1315 MAU"],
    ])
    r.p("Контроль границы: при 713 MAU операционный результат −$0,65, при 714 +$0,35. Полная модель: 1292 MAU дают −$0,538889, 1293 — +$0,461111. Операционная прибыль π(N)=N(r−v)−F; операционный CPU(N)=F/N+v; полный CPU(N)=(F+I/36)/N+v. Если r≤v, конечной точки безубыточности нет. Порог действителен только пока рост не требует увеличения мощности/персонала.")
    r.p("При N=2000: GMV = 2000 × 3% × $500 = $30000; комиссия $2400, переменные расходы $400, постоянные $713,65. Операционная прибыль $1286,35/мес.; CPU $0,556825. С распределением разработки полный CPU $0,846269, полный результат $707,461111/мес. Это не означает окупаемость уже потраченной разработки: годовой денежный результат остается отрицательным.")
    r.p("В прогнозе первый устойчивый операционно прибыльный месяц — M8 (апрель 2027, 800 MAU), полная модель становится положительной в M10 (июнь 2027, 1300 MAU). Для покрытия всех затрат первого года при одинаковом MAU в девяти рабочих месяцах нужно ceil((29203,80 − 1600)/(9 × $1)) = 3068 MAU каждый месяц M4–M12. Это выше принятого профиля 2000 MAU и требует новой сметы инфраструктуры, поэтому не выдается как гарантированный план окупаемости.")
    r.h("Чувствительность",2)
    r.table(["Сценарий","Вклад/MAU","Порог операц.","Порог полный"],[
        ["База: конверсия 3%, комиссия 8%","$1,00","714","1293"],
        ["Конверсия 2%","$0,60","1190","2155"],
        ["Конверсия 1%","$0,20","3569","6463"],
        ["Комиссия 5%","$0,55","1298","2351"],
        ["Переменные $0,40/MAU","$0,80","893","1616"],
        ["Cloud-тарифы +30% (труд/домен без роста)","$1,00","736","1315"],
        ["Нет комиссионного договора / конверсия 0%","−$0,20","Нет","Нет"],
    ])
    r.p("Для 2000 MAU минимальная операционная конверсия = (713,65/2000+0,20)/(500×0,08) = 1,3920625%. Порог 2% в полной модели требует 2155 MAU и выходит за текущий лимит: нужна переоценка. CAC и LTV не объявляются измеренными: нет retention/cohort-данных и платных экспериментов. Лимит продвижения $100/мес. не доказывает привлечение планового MAU.")
    r.p("Исходный бизнес-кейс ЛЗ3 описывает эффект внутренней автоматизации $21700/год, а не комиссионную выручку. Его нельзя прибавлять к комиссии без проверки разных получателей выгоды и отсутствия двойного счета. Старые ROI 41,5% и NPV $9632 относятся к прежним $46000 TCO. После нового размещения и гипотезы монетизации их нельзя переносить как текущие результаты без отдельного пересчета кейса.")
    r.page()
    r.h("6. Три варианта размещения: сопоставимый TCO")
    r.p("Сравниваются 36 полных месяцев эксплуатации при одинаковом спросе: до 2000 MAU, 20 RPS peak, 500 туров, основная БД до 10 GiB, исходящий трафик до 100 GiB/мес., резервные копии/артефакты до 250 GiB. Это demand-профиль, а не утверждение одинаковой производительности железа. Каждый вариант должен пройти один нагрузочный тест и restore-test. Везде есть HTTPS, внешние пробы, копии вне основного узла и самостоятельное сопровождение приложения. HA не заложена ни в одном варианте.")
    r.table(["Вариант","Конфигурация","Ограничения"],[
        ["A. Публичное облако managed","DigitalOcean FRA1: VM Basic Regular 2 vCPU/4 GiB/80 GiB $24; PostgreSQL 1 vCPU/2 GiB/30 GiB $30,45 без standby; daily VM backup; Spaces; внешний monitor VM $6 в другом регионе","Managed DB снижает труд эксплуатации, но не означает HA; доступность/версию PG17 и ресурсы проверять до договора. В модели самый дешевый приемлемый по спросу cloud-профиль, мощность еще не доказана"],
        ["B. Собственная инфраструктура","Сервер ≥4 ядер, ≥16 GB, 2 SSD в зеркале; UPS и сеть; Linux + Nginx + FastAPI + PostgreSQL + Compose; внешний backup и мониторинг","CAPEX $2500 — оценка, не поставка. Нужны пригодное помещение, интернет с IP, питание и персонал. Место в помещении считается предоставленным без добавочной аренды; при ее появлении TCO растет"],
        ["C. Открытый стек на арендованном физическом сервере","Hetzner AX42-1 FSN1/HEL1, 64 GB ECC, 2×512 GB NVMe RAID1, Linux, Nginx, FastAPI, PostgreSQL, Compose, open-source мониторинг/backup","Обычный тариф $117,10 + IPv4 $1,90, setup $59. Для малого пилота железо избыточно; этот вариант именно dedicated, а не еще одна VM публичного облака. Администрирование своими силами"],
    ])
    r.h("Публичный калькулятор и воспроизведение оценки A",2)
    r.p("Открыть S01 без регистрации. Добавить Virtual Machines → Basic → Regular → 2 vCPU / 4 GiB, количество 1 ($24); PostgreSQL Standard → Basic Regular → 1 vCPU / 2 GiB, 30 GiB storage, additional nodes 0, количество 1 ($30,45); Spaces Object Storage, 250 GiB storage и до 1 TiB transfer ($5); отдельную Basic VM 1 vCPU / 1 GiB для внешнего мониторинга ($6). Базовые ресурсы дают $65,45/мес.; daily backup приложения $7,20 рассчитывается отдельно как 30% × $24 по S04. Итого счет провайдера $72,65/мес. до налогов. Домен $1 и труд $40 — собственные статьи, калькулятор провайдера их не оценивает.")
    r.p("В проверенном калькуляторе переключатель backup описывает weekly-копии. Он оставлен выключенным: базовый итог $65,45 подтвержден прямой выгрузкой evidence/DigitalOcean Estimate Cart.csv, daily-backup $7,20 добавлен отдельно по S04. Файл evidence/calculator-inputs.json фиксирует параметры, digitalocean-estimate.png — снимок, calculator-cart-url.txt — ссылка для воспроизведения корзины. Вход в аккаунт и создание ресурсов для расчета не нужны.")
    r.table(["Статья, USD/мес.","A: Cloud","B: Own","C: Rent"],[
        ["VM/аренда сервера","24,00","0,00","117,10"],
        ["Managed DB","30,45","0,00","0,00"],
        ["Daily VM backup","7,20","0,00","0,00"],
        ["Внешние логические backup/артефакты","5,00","5,00","5,00"],
        ["Внешний монитор","6,00","6,00","6,00"],
        ["Домен/DNS","1,00","1,00","1,00"],
        ["Администрирование, $10/ч","40,00 (4 ч)","120,00 (12 ч)","80,00 (8 ч)"],
        ["Электричество","Включено","8,76","Включено"],
        ["Интернет/IPv4","Включено","30,00","1,90"],
        ["Обслуживание железа","Включено","10,00","Включено"],
        ["Всего в месяц",money(m['cloud']),money(m['own']),money(m['rent'])],
    ])
    r.p("Энергия own: 0,08 kW × 24 × 365 / 12 × $0,15 = $8,76/мес. Лицензии приложения/БД/контейнеризации приняты $0 для всех вариантов; открытый стек не делает бесплатными аренду и труд. Backup: 7 daily + 4 weekly + 3 monthly копии при сжатом dump ≤5 GiB занимают ≤70 GiB, остальные артефакты укладываются в 250 GiB. При превышении лимитов storage/traffic применяется опубликованный overage и CR. HTTPS — автоматизированный бесплатный сертификат; установка/продление учтены в часах администрирования.")
    r.page()
    r.h("6.1. Стоимость за три года и решение")
    r.table(["Показатель, USD","Cloud","Own","Rent"],[
        ["CAPEX оборудования","0,00","2500,00","0,00"],
        ["Разовая настройка/провайдерский setup","40,00","120,00","139,00 (80+59)"],
        ["Эксплуатация × 36",money(m['cloud']*36),money(m['own']*36),money(m['rent']*36)],
        ["TCO размещения",money(m['tco_cloud']),money(m['tco_own']),money(m['tco_rent'])],
        ["Общие затраты продукта (20300+500+18000)","38800,00","38800,00","38800,00"],
        ["Сопоставимый TCO проекта",money(m['tco_cloud']+38800),money(m['tco_own']+38800),money(m['tco_rent']+38800)],
        ["Изменение к раннему TCO $46000",money(m['tco_cloud']+38800-46000),money(m['tco_own']+38800-46000),money(m['tco_rent']+38800-46000)],
    ])
    r.p(f"Решение учебной сметы: вариант A дает наименьший TCO размещения ${money(m['tco_cloud'])}; экономия относительно own ${money(m['tco_own']-m['tco_cloud'])}, rent ${money(m['tco_rent']-m['tco_cloud'])} за 36 месяцев. Причины — отсутствие CAPEX, меньший объем администрирования БД и отсутствие лишних физических ресурсов для малого спроса. Это выбор по модели, не оплаченный заказ и не гарантия выполнения SLO.")
    r.p("В hosting TCO не включены общие разработка, маркетинг и переменные затраты MAU, потому что они не определяют выбор размещения. Сопоставимый TCO проекта добавляет общие $38800 без повторного счета настройки приложения, миграции, обучения и поддержки. Маркетинг и переменная коммерческая модель присутствуют в бюджете ЛЗ8; их нет в старом ЛЗ3 и в этой строке сравнения. Поэтому $42931,40 нельзя отождествлять с трехлетним бюджетом растущего бизнеса.")
    r.p("TCO — недисконтированная сумма денежных затрат. CAPEX own включен один раз; начислять поверх него бухгалтерскую амортизацию как дополнительный расход нельзя. Доход от продажи оборудования принят $0. Замена/обслуживание покрывается $10/мес., полная замена сервера за 36 месяцев не планируется. Долговременное хранение данных, HA, круглосуточная смена и поддержка premium не заложены.")
    r.h("Проверка устойчивости выбора",2)
    r.p("При росте опубликованных ежемесячных тарифов на 30% cloud TCO размещения = $4916,02; own = $9246,16; rent = $9139,00. Труд, домен, CAPEX и разовый setup в этом сценарии не меняются. При удвоении ставки труда до $20/ч cloud TCO = $5611,40, own = $13567,36, rent = $10695,00. В обоих случаях cloud остается самым дешевым из трех заданных профилей.")
    r.p("Остаточные риски: single point of failure; SLO 99,9% для C1 остается напряженной целью при одиночных узлах и рабочем, а не круглосуточном дежурстве. Иностранное размещение и правовые условия реальных ПДн должны быть согласованы ответственным до публичного пилота; сравнение разрешает только работу с синтетическими данными до такого решения. При требовании локального размещения выбрать допустимый регион/провайдера и пересчитать тарифы. Изменение часов обслуживания на ±4 ч меняет TCO на ±$1440, поэтому после пилота нужен учет фактических часов.")
    r.page()
    r.h("7. Рубежный контроль 1: пакет недель 1–8")
    r.p("Номера недель здесь — порядок лабораторных артефактов. Они не равны номерам календарных недель реализации в WBS. Поэтому ЛЗ8 подготовлена 23.10.2026, а веха второй части MVP по проектному календарю планируется на 22.11.2026. Подготовка пакета к защите не означает, что все вехи проекта уже приняты.")
    r.table(["Неделя / артефакт","Файл в репозитории","Что защищать / честный статус"],[
        ["1. Инициация и устав","docs/project-charter.md; SaparTravel_Charter_V1.0.docx","Цель, спонсор, границы, роли. Документы есть; внешний заказчик не подписан; команда уточнена в WBS"],
        ["2. Организация и метод работы","docs/adr/ADR-001.md; docs/project-board-workflow.md; README.md","Scrum 2 недели, роли, DoD, репозиторий и CI. Конфигурация есть; актуальный удаленный GitHub Project не подтвержден этим пакетом"],
        ["3. Бизнес-кейс","SaparTravel_Business_Case_LZ3.docx; docs/finmodel.ods","30→8 минут, 70→95%, исходный TCO $46000, ROI/NPV со статусом допущений. Не путать эффект и комиссию"],
        ["4. Backlog и НФТ","docs/requirements/story-map.md и PNG; docs/requirements/non-functional-requirements.md; приложения backlog_baseline.csv / nfr_register.csv","15 Must + 3 вне MVP; 16 проверяемых НФТ в консолидированном реестре. Старый story-map ссылается на отсутствующий docs/labs-3-4.md: локальный полный срез восстановлен в приложении"],
        ["5. План и зависимости","docs/plan/wbs.md; docs/plan/dependencies.md; sapartravel-models.drawio","171 ч, 3 инкремента, RACI, внешние зависимости. Сроки расходятся со старым уставом — CR-08-02"],
        ["6. Оценка","docs/lab-6-planning-poker.md; notebooks/lab-6-monte-carlo.ipynb; data/throughput.csv; docs/lab-6-customer-slide.pptx","10 историй = 58 SP; другие 11 незавершенных = 57 SP; 10000 прогонов, seed42; P85 06.11.2026, P95 13.11.2026. Учебный throughput, не фактическая velocity и не полный релиз с UAT"],
        ["7. Риски и безопасность","docs/security/raid.md; threat-model.md/json; security-scan-report.md; security-backlog.md","20 рисков, EMV63,2ч, управление16ч; отчет от16.10 содержит 1 Critical/5 High и 6 секретоподобных находок. Закрытие не подтверждено свежим сканом"],
        ["8. Договоренности и деньги","docs/lab-8/SaparTravel_LZ8_Report.docx/pdf/html; Financial_Model.xlsx; defense.pptx","SoW, C1–C3, SLA/credits, error budgets, 12 месяцев, unit и 3 TCO; арифметика проверяется формулами"],
    ])
    r.h("Что показано и что еще должен подтвердить заказчик",2)
    r.table(["Готово как артефакт","Открыто как реальное решение/проверка","Владелец / контроль"],[
        ["Результаты, границы, приемка и CR","ФИО принимающего, подписание CR и актов","Внешний заказчик + Нурасыл / до UAT"],
        ["Измеримые SLO и SLA","Инструментирование, месячная телеметрия, внешние пробы","Әмір / до запуска"],
        ["Бюджет и резервы","46,2 ч дополнительного ресурса либо пересогласование объема/срока","Нурасыл + спонсор / до обещания финальной даты"],
        ["Комиссионная unit-модель","Договор поставщика, реальная конверсия и MAU","Елнара + PO / до учета выручки"],
        ["План quality gate","Устранение/разбор High/Critical, повторный скан, нагрузка, backup/restore, аудит","Әмір + Бибінұр / до публичного пилота"],
    ])
    r.p("Решение для протокола РК1: учебные артефакты недель 1–8 подготовлены и трассируются к проекту; фактическая оценка преподавателя, подпись заказчика и разрешение production-запуска не проставляются за внешних участников. Публичный пилот до quality gate и решения по ПДн не объявляется. Наличие этих открытых пунктов не скрывается за выполненной арифметикой бюджета.")
    r.page()
    r.h("7.1. Полный локальный срез backlog и НФТ")
    r.p("Backlog восстановлен по story-map, Planning Poker и текущим API/QA-сценариям, без утверждения актуальности удаленных Issues. ST-01–ST-15 — Must-срез MVP, ST-16–ST-18 — после MVP. Для последних пяти Must-историй новая SP-оценка не выдумывается; суммарные 171 ч WBS и SP не переводятся друг в друга.")
    r.table(["ID / история","Позитивный и негативный критерии"],[[f"{x[0]} {x[1]}",x[2]] for x in BACKLOG])
    r.p("Приложение backlog_baseline.csv содержит SP там, где они действительно есть в протоколе ЛЗ6. Все Must-сценарии перед релизом связываются с результатом UAT/CI и SHA. Наличие функции в коде не считается автоматически принятой историей.")
    r.table(["НФТ","Ключевая измеримая граница"],[[x[0]+" "+x[1],x[2]] for x in NFR])
    r.p("Подробные методы проверки и статус доказательств — nfr_register.csv. Часть границ уточняет общие формулировки старого файла НФТ; эти уточнения входят в CR-08-03. Тесты приложения при создании этого документального пакета не выдаются за выполненный нагрузочный или месячный SLA-прогон.")
    r.page()
    r.h("7.2. Сценарий защиты на 7–8 минут")
    r.table(["Слайд / время","Тезис доклада и демонстрируемое доказательство"],[
        ["1 / 45 с","SaparTravel закрывает путь от поиска до статуса. Цель бизнеса: 30→8 минут, 70→95%; показать устав и README. Цена каталога демонстрационная, онлайн-оплаты нет"],
        ["2 / 60 с","SoW: пять поставок, четкая граница MVP, роли, 171 ч WBS, финальная передача 20.12.2026. Результат принимается по UAT, а не по устному обещанию"],
        ["3 / 60 с","Сценарии C1/C2/C3 и метрики: внутренние 99,9/99,8/99,7%, внешняя граница 99,5%; p95 измеряется от действия до результата. Мониторинг пока цель, не доказанный факт"],
        ["4 / 45 с","При 30 днях бюджеты 43,2 / 86,4 / 129,6 минут; SLA 216 минут. Не смешивать минуты и ошибки. При исчерпании замораживаются функциональные релизы"],
        ["5 / 60 с","Открыть Budget12 и Checks: $29203,80 без резервов; $29995,80 лимит; 8000 пользователь-месяцев; средняя стоимость $3,65. Риски стоят отдельно, дефицит ресурсов 46,2ч показан"],
        ["6 / 60 с","Показать Unit: $1,20 выручки − $0,20 = $1 вклад/MAU. F=$713,65; пороги714/1293. На2000MAU операционная прибыль$1286,35, но первый год убыточен$19603,80"],
        ["7 / 60 с","Показать калькулятор и Hosting: одинаковый спрос, облако$4131,40, own$9127,36, dedicated$7735 за36мес. Деньги провайдерам не перечислялись; труд и резервные копии включены"],
        ["8 / 60 с","Трассировка восьми недель и открытые решения: подписи, качество, MAU/комиссионные договоры, 46,2ч. Пакет подготовлен; фактическую приемку и SLA не выдумываем"],
    ])
    r.h("Ответы на контрольные вопросы",2)
    r.bullets([
        "Почему не 99,99%? В одиночной конфигурации и без 24×7 дежурства такая обязанность не обеспечена бюджетом; 99,5% — внешний минимум старого НФТ, внутренние цели жестче.",
        "Почему 409 может быть корректным? Пользователь получает честный результат об отсутствии мест; он не считается состоявшейся продажей. Синтетическая бронь на свободном тестовом выезде обязана вернуть201.",
        "Почему первый год убыточен при 714 MAU? 714 покрывают ежемесячные расходы зрелого сервиса; стартовые $20840 и период без выручки остаются в денежном потоке первого года.",
        "Почему собственный сервер не бесплатный? В TCO включены CAPEX, электричество, интернет, копии, ремонт и 12 ч администрирования; уже имеющееся железо потребовало бы отдельного incremental-сценария.",
        "Почему $18000 разработки не равны171×$10? Это сохраненная top-down цена поставки ЛЗ3.171ч — учебная WBS; $10/ч используется для добавочных ресурсов и эксплуатации. Пересчет всей цены требует нового коммерческого предложения, не скрытой замены чисел.",
        "Что реально выполнено сейчас? Подготовлены документы и проверены вычисления; подключение production-мониторинга, договоры, UAT и исправления приложения не подменяются этой лабораторной работой.",
    ])
    r.page()
    r.h("8. Источники, воспроизводимость и комплект")
    r.p("Дата проверки официальных веб-источников: 23.10.2026. Тарифы не являются обещанием неизменной цены на36месяцев; это прогноз при текущих ценах. Расчетный cloud не оплачивался. На страницах тарифов может быть кнопка регистрации, но чтение калькулятора и прайсов регистрации не требует.")
    for sid,title,url,note in SOURCES:
        r.h(f"{sid}. {title}",2)
        r.p(url)
        r.p(note)
    r.h("Локальные источники и воспроизведение",2)
    r.p("Устав/бизнес-кейс: docs/project-charter.md; SaparTravel_Business_Case_LZ3.docx; docs/finmodel.ods. Требования: docs/requirements/story-map.md и non-functional-requirements.md. План/оценка: docs/plan/wbs.md; docs/lab-6-planning-poker.md; docs/lab-6-insight.md; notebooks/lab-6-monte-carlo.ipynb. Риски: docs/security/raid.md и security-scan-report.md. Архитектура/границы: README.md, docs/adr/ADR-002.md, backend/app/api/routes.py, docs/qa/test-plan.md. Старый раздел Supabase в runbook противоречит текущему ADR-002: в расчете используется обычный PostgreSQL, Supabase не включен.")
    r.p("Генератор: scripts/create_lab8_package.py, зависимости python-docx/openpyxl/python-pptx. Запуск: .venv/bin/python scripts/create_lab8_package.py. Затем пересчитать XLSX в LibreOffice и проверить формулы по scripts/validate_lab8_package.py; PDF экспортируется из DOCX через LibreOffice. В XLSX — 10 листов, формулы не заменены скриншотами. budget_12_months.csv — контрольный статический экспорт, XLSX — редактируемый источник финансовых расчетов.")
    r.p("Комплект: SaparTravel_LZ8_Report.docx, .pdf и .html; SaparTravel_LZ8_Financial_Model.xlsx; SaparTravel_LZ8_defense.pptx; budget_12_months.csv; backlog_baseline.csv; nfr_register.csv; assumptions_and_results.json; evidence/ с параметрами и снимками калькулятора; validation.json с проверками. Архив SaparTravel_LZ8_Submission.zip дополнительно включает существующие артефакты недель1–7 и manifest.json; .env, персональные данные и node_modules в него не входят.")
    r.save()


def write_slides(m):
    prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5)
    slides=[
        ("SaparTravel / ЛЗ 8", "SoW • SLA/SLO • бюджет • рубежный контроль 1", ["Найти тур → выбрать выезд → заявка → статус", "Бизнес-цель: 30 → 8 минут на обработку, 70% → 95% за рабочий день", "React / FastAPI / PostgreSQL • RU / KK / EN", "Абинсериков Нурасыл и команда • 23.10.2026"],"45 секунд. Цели бизнеса — гипотезы. Платежей и реальных партнерских API в MVP нет."),
        ("SoW: что передаем", "5 поставок • 171 ч WBS • финальная веха 20.12.2026", ["D1: baseline требований, backlog и НФТ", "D2–D3: API, база, интерфейс и кабинеты трех ролей", "D4–D5: качество, UAT, обучение, backup/restore и передача", "Приемка: 5 рабочих дней, письменное решение; изменения — через CR", "Онлайн-оплата, SMS, реальные интеграции — после MVP"],"60 секунд. Покажите раздел2 отчета. Молчание не приемка. Права на заказной результат передаются после акта и оплаты, лицензии зависимостей сохраняются."),
        ("SLO привязаны к действию", "Внешний SLA: ≥99,5% для каждого сценария", ["C1: поиск + карточка → SLO 99,9%", "C2: вход + профиль → SLO 99,8%", "C3: заявка + результат в кабинете → SLO 99,7%", "p95 E2E: SLO ≤2 с / SLA ≤3 с; API ≤0,5 / ≤0,75 с", "Минутные внешние пробы + реальные попытки; цели еще не подтверждены"],"60 секунд. Разделяйте A по минутам и Q по попыткам.409 только при реальном бизнес-конфликте.201 обязательно для подготовленного тестового выезда."),
        ("Error budget управляет релизами", "Для 30 дней = 43 200 минут", ["C1: 43,2 мин. • C2: 86,4 мин. • C3: 129,6 мин.", "SLA 99,5%: 216 мин. для каждого сценария", "На 4000 попыток C3: не более12 ошибок по SLO", "Остаток <20%: остановка функциональных релизов", "Credits: 5 / 10 / 20% от платы сопровождения, максимум $100/мес."],"45 секунд. Формула(1−SLO)×T или floor((1−SLO)×N), разные знаменатели. Плановые работы учитываются.24×7 дежурства нет."),
        ("Бюджет первого года", "09.2026–08.2027 • все значения — план", [f"Затраты без резервов: ${money(m['base'])}", f"С рисками: ${money(m['baseline'])} • общий лимит: ${money(m['funding'])}", "8000 MAU-месяцев → $3,65 за пользователь-месяц", "$9600 комиссии → дефицит года $19603,80", "171 + 63,2 +16ч >204ч: требуется еще46,2ч или CR"],"60 секунд. Откройте Budget12 и Checks. Резервы$632+$160 не расходы-факт. Дополнительные46,2ч по$10 укладываются в резерв, но доступность исполнителя не подтверждена."),
        ("Когда экономика сходится", "Операционная безубыточность ≠ окупаемость первого года", ["$500 × 3% × 8% = $1,20 выручки на MAU", "$1,20 − $0,20 = $1,00 маржинального вклада", "$713,65 постоянных расходов →714 MAU", "С распределением разовых затрат на36месяцев →1293 MAU", "При2000MAU: $1286,35 операционной прибыли/мес.; комиссия — гипотеза"],"60 секунд. Нет комиссионных договоров — выручка0. GMV не равно доходу платформы. Порог только в пределах подтвержденной мощности. При конверсии1% операционный порог3569MAU."),
        ("TCO размещения / 36 месяцев", "Одинаковый спрос: до2000MAU, 20RPS, 500туров", [f"Cloud managed: ${money(m['tco_cloud'])}", f"Собственный сервер: ${money(m['tco_own'])}", f"Открытый стек / dedicated: ${money(m['tco_rent'])}", "Учтены труд, backup, мониторинг, сеть и CAPEX", "Выбор по смете: cloud; калькулятор и официальные тарифы, без оплаты"],"60 секунд. Покажите Hosting и evidence. Калькулятор базовых ресурсов$65,45 плюс daily backup$7,20; счет$72,65, домен$1, администрирование$40. Сравнение без HA; мощность требует проверки."),
        ("Пакет недель1–8", "Артефакты подготовлены; внешняя приемка не подменяется отчетом", ["Устав → бизнес-кейс → backlog/НФТ → план/оценка → риски → бюджет", "Приложения: 18историй, 16НФТ, Excel с формулами и сценариями", "До пилота: UAT, нагрузка, restore, повторный security scan", "Открытые решения: заказчик,46,2ч ресурсов, ПДн и комиссионные договоры", "Защита: показать арифметику и объяснить ограничения модели"],"60 секунд. Отчет ЛЗ7 не чистый PASS:1Critical/5High и6секретоподобных находок. Исправления могли быть начаты в рабочем дереве, но свежего результата в пакет не выдумываем."),
    ]
    for idx,(title,subtitle,points,notes) in enumerate(slides,1):
        slide=prs.slides.add_slide(prs.slide_layouts[6])
        bg=slide.background.fill;bg.solid();bg.fore_color.rgb=SlideColor(244,248,247)
        stripe=slide.shapes.add_shape(1,0,0,Inches(.16),prs.slide_height)
        stripe.fill.solid();stripe.fill.fore_color.rgb=SlideColor(44,139,128);stripe.line.fill.background()
        def box(text,x,y,w,h,size,color,bold=False):
            text=typeset(text)
            tf=slide.shapes.add_textbox(Inches(x),Inches(y),Inches(w),Inches(h)).text_frame
            tf.word_wrap=True
            for j,line in enumerate(text.split("\n")):
                p=tf.paragraphs[0] if j==0 else tf.add_paragraph()
                p.text=line;p.font.name="DejaVu Sans";p.font.size=SlidePt(size);p.font.bold=bold;p.font.color.rgb=SlideColor(*color)
                p.space_after=SlidePt(16)
            return tf
        box(title,.65,.45,12,1,32,(18,61,74),True)
        box(subtitle,.7,1.5,12,.8,18,(44,139,128))
        box("\n".join("• "+p for p in points),.8,2.4,11.8,4.5,22,(37,51,58))
        box(f"SaparTravel  /  ЛЗ8  /  23.10.2026                                      {idx:02d} /08",.7,7.05,12,.3,10,(88,110,115))
        slide.notes_slide.notes_text_frame.text=notes
    prs.save(OUT/"SaparTravel_LZ8_defense.pptx")


def main():
    m=make_model()
    write_workbook(m);write_csvs(m);write_report(m);write_slides(m)
    (OUT/"assumptions_and_results.json").write_text(json.dumps({"date":DATE,"currency":"USD","status":"forecast, not actuals","inputs":INPUTS,"sources":SOURCES,"results":m},ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"evidence"/"calculator-inputs.json").parent.mkdir(exist_ok=True)
    (OUT/"evidence"/"calculator-inputs.json").write_text(json.dumps({"as_of":"2026-10-23","url":SOURCES[0][2],"registration":False,"paid_resources_created":False,"region":"FRA1; monitor in another region","items":[{"product":"Basic Regular Droplet","vcpu":2,"ram_gib":4,"ssd_gib":80,"quantity":1,"monthly_usd":24},{"product":"PostgreSQL Standard Basic Regular","vcpu":1,"ram_gib":2,"storage_gib":30,"standby":0,"quantity":1,"monthly_usd":30.45},{"product":"Spaces","storage_gib":250,"transfer_tib":1,"quantity":1,"monthly_usd":5},{"product":"Basic Regular monitor Droplet","vcpu":1,"ram_gib":1,"ssd_gib":25,"quantity":1,"monthly_usd":6}],"calculator_base_monthly_usd":65.45,"daily_backup_separate_official_formula":"24 * 0.30 = 7.20 USD/month","provider_monthly_usd":72.65,"domain_allowance_usd":1,"administration_usd":40,"total_monthly_usd":113.65},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:round(v,6) if isinstance(v,float) else v for k,v in m.items() if k!="months"},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    # The original USD functions remain the traceable source estimate. The
    # user's current submission currency is KZT, including on this entry point.
    from create_lab8_kzt import main as build_current_package
    build_current_package()
