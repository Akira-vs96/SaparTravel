"""Convert the existing LZ8 USD model into a formula-preserving KZT model.

Example:
    .venv/bin/python scripts/convert_lab8_workbook_kzt.py --rate 447.94 \
        --input /tmp/original-model.xlsx --output /tmp/model-kzt.xlsx \
        --date 2026-10-23 --source https://nationalbank.kz/

The conversion establishes fixed KZT project assumptions at the supplied rate.
Only the published foreign-currency hosting tariffs remain linked to the FX
sheet afterwards. Opening the result in Excel or LibreOffice recalculates all
formulas; openpyxl does not calculate or cache formula results itself.
"""

from __future__ import annotations

import argparse
from copy import copy
from decimal import Decimal
import math
from pathlib import Path
import re

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.properties import CalcProperties


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "docs/lab-8/SaparTravel_LZ8_Financial_Model.xlsx"
DEFAULT_SOURCE = (
    "https://nationalbank.kz/ru/exchangerates/"
    "ezhednevnye-oficialnye-rynochnye-kursy-valyut"
)
FX_REF = "FX!$B$4"
MONEY_FORMAT = '#,##0.00;[Red]-#,##0.00;0.00'
FINE_FORMAT = '#,##0.0000;[Red]-#,##0.0000;0.0000'
INPUT_COLOR = "1767B3"
HEADER_COLOR = "123D4A"


def _scale(value: float, rate: float) -> float:
    """Avoid introducing an extra binary-rounding step in stored inputs."""
    return float(Decimal(str(value)) * Decimal(str(rate)))


def _style_row(sheet, row: int, *, header: bool = False) -> None:
    for cell in sheet[row]:
        cell.font = Font(
            name="Calibri", size=11 if header else 10,
            bold=header, color="FFFFFF" if header else "25333A",
        )
        cell.fill = PatternFill(
            "solid", fgColor=HEADER_COLOR if header else
            ("EFF5F4" if row % 2 == 0 else "FFFFFF"),
        )
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        if cell.data_type == "f" or isinstance(cell.value, (float, int)):
            cell.number_format = MONEY_FORMAT
    sheet.row_dimensions[row].height = 36 if header else 42


def convert_workbook(
    input_path: str | Path,
    output_path: str | Path,
    fx_rate: float,
    *,
    rate_date: str = "2026-10-23",
    source_url: str = DEFAULT_SOURCE,
) -> Path:
    """Convert a baseline USD workbook; preserve formulas and chart series.

    ``fx_rate`` is KZT per one USD. Monetary assumptions on Inputs are converted
    once and remain editable KZT values. Provider prices retain their original
    USD source values on Tariffs, with KZT equivalents calculated through FX.
    Re-running against an already converted workbook is rejected deliberately.
    """
    if not math.isfinite(fx_rate) or fx_rate <= 0:
        raise ValueError("fx_rate must be a finite positive number of KZT per USD")
    input_path, output_path = Path(input_path), Path(output_path)
    wb = load_workbook(input_path)
    required = {"Guide", "Inputs", "Tariffs", "Hosting", "Budget12", "Unit",
                "Sensitivity", "SLO", "Checks", "Sources"}
    if not required.issubset(wb.sheetnames):
        raise ValueError(f"Missing baseline sheets: {sorted(required - set(wb.sheetnames))}")
    if "FX" in wb.sheetnames:
        raise ValueError("Workbook already has an FX sheet; use the original USD baseline")
    inputs, tariffs = wb["Inputs"], wb["Tariffs"]
    if not any("USD" in str(inputs.cell(r, 3).value) for r in range(2, 32)):
        raise ValueError("Input workbook must be the original USD financial model")

    fx = wb.create_sheet("FX", 1)
    for row in [
        ["Валютный параметр", "Значение", "Правило использования"],
        ["Валюта бюджета", "KZT / казахстанский тенге", "Все итоговые затраты, выручка и стоимость на MAU — в тенге"],
        ["Валюта опубликованных тарифов", "USD", "Исходные тарифы провайдеров сохранены на Tariffs, колонка B"],
        ["Курс: тенге за 1 USD", fx_rate, "Редактируемый курс; пересчитывает опубликованные валютные тарифы, колонка E Tariffs"],
        ["Дата курса", rate_date, "Дата котировки/применения, зафиксированная при подготовке расчета"],
        ["Источник курса", source_url, "Проверяемый источник; ставка курса передана в конвертер явно"],
        ["Местные сметные допущения", "Фиксированы в тенге после перевода", "Inputs и ранний baseline переведены однократно по курсу на дату подготовки; менять в тенге по фактическим предложениям"],
        ["Что означает валютный стресс", "Меняются только опубликованные валютные тарифы", "Курс не индексирует местный чек, зарплаты, CAPEX и прочие фиксированные тенговые допущения"],
        ["Точность", "Формулы сохраняют полную точность; вывод денег — 2 знака", "Малые удельные ставки показаны с 4 знаками; остаток резерва переносится на M3"],
        ["Налоги, инфляция и банковская конвертация", "Не включены", "Перевод валюты сохраняет исходную методику, не является налоговым или банковским расчетом"],
    ]:
        fx.append(row)
    for row in range(1, fx.max_row + 1):
        _style_row(fx, row, header=row == 1)
    for coordinate in ("B4", "B5", "B6"):
        fx[coordinate].font = Font(name="Calibri", size=10, color=INPUT_COLOR)
    fx["B4"].number_format = '0.00" тг/USD"'
    fx["B6"].hyperlink = source_url
    positive_rate = DataValidation(type="decimal", operator="greaterThan", formula1=0)
    positive_rate.errorTitle = "Курс должен быть положительным"
    positive_rate.error = "Укажите число тенге за 1 USD больше нуля."
    positive_rate.showErrorMessage = True
    positive_rate.errorStyle = "stop"
    fx.add_data_validation(positive_rate)
    positive_rate.add(fx["B4"])
    fx.freeze_panes = "B2"
    fx.sheet_view.showGridLines = False
    fx.column_dimensions["A"].width = 47
    fx.column_dimensions["B"].width = 67
    fx.column_dimensions["C"].width = 110
    fx.print_title_rows = "1:1"
    fx.page_setup.orientation = "landscape"
    fx.page_setup.paperSize = fx.PAPERSIZE_A3
    fx.page_setup.fitToWidth = 1
    fx.page_setup.fitToHeight = 0
    fx.sheet_properties.pageSetUpPr.fitToPage = True

    monetary_input_rows = []
    for row in range(2, inputs.max_row + 1):
        unit_cell, value_cell = inputs.cell(row, 3), inputs.cell(row, 2)
        if "USD" not in str(unit_cell.value):
            continue
        if not isinstance(value_cell.value, (float, int)):
            raise ValueError(f"Expected a numeric original monetary input at {value_cell.coordinate}")
        original = value_cell.value
        value_cell.value = _scale(original, fx_rate)
        value_cell.number_format = FINE_FORMAT if original < 1 else MONEY_FORMAT
        unit_cell.value = unit_cell.value.replace("USD", "тг")
        monetary_input_rows.append(row)
    # The comparison baseline is also a fixed KZT assumption, rather than an
    # unconverted monetary constant hidden inside three Hosting formulas.
    inputs.append([
        "Ранний baseline ЛЗ3 для сравнения", _scale(46000, fx_rate), "тг, справочно",
        "Архивная смета ЛЗ3, приведенная к тенге по начальному курсу FX; не новая оценка затрат",
    ])
    baseline_row = inputs.max_row
    _style_row(inputs, baseline_row)
    inputs.cell(baseline_row, 2).font = Font(name="Calibri", size=10, color=INPUT_COLOR)
    inputs["D2"] = "Бизнес-кейс ЛЗ3; top-down оценка. Трудоемкость WBS оценивается отдельно, ставки указаны в тенге"
    inputs["D16"] = "Сметный лимит годового домена / 12, переведенный в тенге; не оферта регистратора"
    inputs.auto_filter.ref = inputs.dimensions

    tariffs["B1"] = "Исходный тариф USD / доля"
    tariffs["E1"] = "Тариф в тенге / доля"
    for row in range(2, tariffs.max_row + 1):
        tariffs.cell(row, 5, f"=B{row}" if row == 4 else f"=B{row}*{FX_REF}")
        tariffs.cell(row, 5)._style = copy(tariffs.cell(row, 2)._style)
        tariffs.cell(row, 5).font = Font(name="Calibri", size=10, color="25333A")
    tariffs["E1"]._style = copy(tariffs["B1"]._style)
    tariffs["B4"].number_format = tariffs["E4"].number_format = "0.0%"
    tariffs["D4"] = "Безразмерная доля от application VM; не денежная сумма"
    tariffs["D8"] = "Ежемесячная цена; разовая настройка IPv4 — 0 тг"
    tariffs["D9"] = "Разовый setup провайдера; исходный USD переведен в колонке E, не ежемесячный платеж"
    tariffs.column_dimensions["B"].width = 27
    tariffs.column_dimensions["E"].width = 27
    tariffs.auto_filter.ref = tariffs.dimensions
    tariff_ref_pattern = re.compile(r"Tariffs!(\$?)B(\$?)(\d+)")
    # Named groups are unnecessary, but the callback keeps absolute markers.
    for sheet in wb:
        if sheet.title in {"Tariffs", "FX"}:
            continue
        for row in sheet:
            for cell in row:
                if cell.data_type == "f" and "Tariffs!" in cell.value:
                    def replace_ref(match):
                        col = "B" if match.group(3) == "4" else "E"
                        return f"Tariffs!{match.group(1)}{col}{match.group(2)}{match.group(3)}"
                    cell.value = tariff_ref_pattern.sub(replace_ref, cell.value)

    hosting = wb["Hosting"]
    for column in "BCD":
        hosting[f"{column}18"] = f"={column}17-Inputs!$B${baseline_row}"
    hosting["A1"] = "Статья, тенге"
    hosting["E3"] = "Для own/rent PostgreSQL на своем узле; лицензия — 0 тг"
    hosting["E7"] = "Годовой домен распределен на 12 месяцев; ставка Inputs указана в тенге"
    hosting["E8"] = "Дополнительные часы администрирования; поддержка приложения учитывается отдельно"
    hosting["E13"] = "Сервер + UPS/сеть; сметные CAPEX в тенге из Inputs"
    hosting["E14"] = "Разовые работы инфраструктуры сверх разработки приложения; все суммы в тенге"
    hosting["E16"] = "Разработка, миграция, обучение, переход и поддержка за 36 месяцев; без маркетинга и переменных расходов"
    hosting["E17"] = "Сопоставление с архивным baseline ЛЗ3, приведенным к тенге в Inputs"

    guide = wb["Guide"]
    guide["B2"] = "1.1 KZT / 23.10.2026"
    guide["B3"] = "Тенге (KZT). Курс и дата — FX; опубликованные валютные тарифы переведены формулами. Налоги и инфляция не включены"
    guide["B6"] = "Синие значения Inputs, исходные тарифы Tariffs B, FX B4:B6 и MAU Budget12 — входы; остальные суммы рассчитываются формулами"
    guide["B10"] = "EMV 63,2 ч и управление 16 ч умножаются на ставку часа в тенге из Inputs; резервы — лимиты, не фактические расходы"
    guide["B11"] = "Поддержка приложения и пользователей — ставка Inputs в тенге; 4/12/8 ч администрирования размещения учитываются отдельно"

    budget = wb["Budget12"]
    budget["A1"] = "Статья / суммы в тенге"
    budget["A16"] = "Стоимость на MAU, тг/мес."
    for row in range(2, budget.max_row + 1):
        for column in range(2, 15):
            budget.cell(row, column).number_format = "#,##0" if row == 2 else MONEY_FORMAT
    # Four decimals expose the formerly fractional currency inputs rather than
    # silently rounding the underlying 0.20-unit variable cost to whole tiyn.
    unit = wb["Unit"]
    unit["B1"] = "Значение, тг / MAU / доля"
    unit["C2"] = "Средний чек в тенге × 3% × 8%; после отмен"
    unit["C3"] = "Тенге / активный турист / месяц; ставка из Inputs"
    unit["C5"] = "Размещение и его администрирование + поддержка приложения + продвижение, тг/мес."
    unit["C6"] = "Сумма разовых затрат в тенге; в первом году уже включена в Budget12"
    for row in (8, 9, 10, 11, 23):
        unit.cell(row, 2).number_format = "#,##0"
    unit["B22"].number_format = "0.0%"

    sensitivity = wb["Sensitivity"]
    sensitivity["D1"] = "Расход/MAU, тг"
    sensitivity["E1"] = "Вклад/MAU, тг"
    sensitivity["F1"] = "Fixed/мес., тг"
    sensitivity["A6"] = "Переменные расходы на MAU × 2"
    sensitivity["D6"] = "=Inputs!$B$8*2"
    for row in range(2, 9):
        sensitivity.cell(row, 7).number_format = "#,##0"
        sensitivity.cell(row, 8).number_format = "#,##0"
    # FX stress applies to the published cloud tariffs alone. KZT wages, the
    # assumed ticket price, local costs and one-time works remain fixed.
    for row in [
        ["Валютный сценарий", "Изменение курса", "Курс валюты, тг/ед.", "Cloud OPEX, тг/мес.", "F, тг/мес.", "Cloud TCO 36 мес., тг", "MAU операц.", "MAU полный"],
        ["Курс −20%", -.2],
        ["Курс базовый", 0],
        ["Курс +20%", .2],
    ]:
        # Start at row 11 with a single empty row separating scenarios.
        if sensitivity.max_row < 10:
            sensitivity.cell(10, 1, "Курс меняет только валютные тарифы; местные сметные значения в тенге фиксированы")
        sensitivity.append(row)
    for row in range(12, 15):
        sensitivity.cell(row, 3, f"={FX_REF}*(1+B{row})")
        sensitivity.cell(row, 4, f"=Hosting!B12+SUM(Hosting!B2:B6)*B{row}")
        sensitivity.cell(row, 5, f"=Unit!B5+SUM(Hosting!B2:B6)*B{row}")
        sensitivity.cell(row, 6, f"=D{row}*36+Hosting!B13+Hosting!B14")
        sensitivity.cell(row, 7, f'=IF(Unit!B4<=0,"Нет",ROUNDUP(E{row}/Unit!B4,0))')
        sensitivity.cell(row, 8, f'=IF(Unit!B4<=0,"Нет",ROUNDUP((E{row}+Unit!B7)/Unit!B4,0))')
    _style_row(sensitivity, 11, header=True)
    for row in range(12, 15):
        _style_row(sensitivity, row)
        sensitivity.cell(row, 2).number_format = "0.0%"
        sensitivity.cell(row, 7).number_format = sensitivity.cell(row, 8).number_format = "#,##0"
    sensitivity.auto_filter.ref = "A1:H8"

    checks = wb["Checks"]
    checks.append(["Курс положителен", '=IF(FX!B4>0,0,1)', 0])
    checks.append(["Тариф VM переведен в тенге", "=ROUND(Tariffs!E2-Tariffs!B2*FX!B4,8)", 0])
    checks.append(["Backup fraction без валютной конвертации", "=Tariffs!E4-Tariffs!B4", 0])
    checks.append(["Базовый валютный сценарий: OPEX", "=ROUND(Sensitivity!D13-Hosting!B12,8)", 0])
    checks.append(["Базовый валютный сценарий: TCO", "=ROUND(Sensitivity!F13-Hosting!B15,8)", 0])
    checks.append(["Распределение риск-резерва в тенге", "=ROUND(SUM(Budget12!B17:M17)-Inputs!B17*Inputs!B12,8)", 0])
    for row in range(15, checks.max_row + 1):
        _style_row(checks, row)
    checks.auto_filter.ref = checks.dimensions

    sources = wb["Sources"]
    sources.append(["FX01", "Курс перевода в тенге", source_url, rate_date,
                    "Курс на FX; исходные тарифы сохраняются в валюте публикации, финансовые результаты показаны в тенге"])
    _style_row(sources, sources.max_row)
    sources.auto_filter.ref = sources.dimensions

    for chart in budget._charts:
        chart.title = "Прогноз затрат и выручки / тенге"
        chart.y_axis.title = "тг/мес."
    for chart in hosting._charts:
        chart.title = "TCO размещения за 36 месяцев / тенге"
        chart.y_axis.title = "тг"
    # Source citations intentionally retain quoted foreign prices; no result
    # sheet may retain USD output labels or dollar-valued prose.
    allowed_foreign_currency = {"Tariffs", "Sources", "FX"}
    for sheet in wb:
        if sheet.title in allowed_foreign_currency:
            continue
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str) and cell.data_type != "f":
                    if "USD" in cell.value or "$" in cell.value:
                        raise ValueError(f"Unconverted currency label: {sheet.title}!{cell.coordinate}: {cell.value}")
    wb.calculation = CalcProperties(calcId=191029, fullCalcOnLoad=True,
                                    forceFullCalc=True, calcMode="auto")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate", type=float, required=True, help="KZT per one USD")
    parser.add_argument("--input", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--date", default="2026-10-23", help="Rate quotation date (YYYY-MM-DD)")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Verified exchange-rate source URL")
    args = parser.parse_args()
    path = convert_workbook(args.input, args.output, args.rate,
                            rate_date=args.date, source_url=args.source)
    print(f"KZT workbook saved: {path}. Recalculate with Excel/LibreOffice before validation.")


if __name__ == "__main__":
    main()
