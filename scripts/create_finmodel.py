import os
import subprocess
import time

import uno
from com.sun.star.beans import PropertyValue


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(ROOT, "docs", "finmodel.ods")


def prop(name, value):
    item = PropertyValue()
    item.Name = name
    item.Value = value
    return item


def set_row(sheet, row, values):
    for column, value in enumerate(values):
        cell = sheet.getCellByPosition(column, row)
        if isinstance(value, str) and value.startswith("="):
            cell.Formula = value
        elif isinstance(value, (int, float)):
            cell.Value = value
        else:
            cell.String = str(value)


def format_sheet(sheet, widths):
    for column, width in enumerate(widths):
        sheet.getColumns().getByIndex(column).Width = width
    header = sheet.getCellRangeByPosition(0, 0, len(widths) - 1, 0)
    header.CharWeight = 150


def connect():
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            return resolver.resolve(
                "uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext"
            )
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("LibreOffice UNO listener did not start")


def main():
    if os.path.exists(OUTPUT):
        os.remove(OUTPUT)

    process = subprocess.Popen(
        [
            "libreoffice",
            "--headless",
            "--norestore",
            "--nofirststartwizard",
            "--accept=socket,host=localhost,port=2002;urp;StarOffice.ComponentContext",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        context = connect()
        desktop = context.ServiceManager.createInstanceWithContext(
            "com.sun.star.frame.Desktop", context
        )
        document = desktop.loadComponentFromURL("private:factory/scalc", "_blank", 0, ())
        sheets = document.Sheets
        names = ["Inputs", "Baseline", "TCO", "CashFlow", "Sensitivity", "Sources"]
        sheets.getByIndex(0).Name = names[0]
        for name in names[1:]:
            sheets.insertNewByName(name, sheets.getCount())

        inputs = sheets.getByName("Inputs")
        input_rows = [
            ["Параметр", "Значение", "Единица", "Статус"],
            ["Входящие заявки", 60, "заявок/неделю", "Допущение"],
            ["Ручная обработка одной заявки", 30, "минут", "Допущение"],
            ["Стоимость часа сотрудника", 10, "USD/час", "Допущение"],
            ["Годовой эффект от ошибок", 4000, "USD/год", "Допущение"],
            ["Годовой эффект конверсии", 6000, "USD/год", "Допущение"],
            ["Снижение ручной работы", 0.75, "доля", "Допущение"],
            ["Ставка дисконтирования", 0.15, "доля", "Допущение"],
            ["Горизонт", 3, "года", "Учебное решение"],
            ["Текущая ручная стоимость", "=B2*52*B3/60*B4", "USD/год", "Формула"],
            ["Годовой эффект", "=B10*B7+B5+B6", "USD/год", "Формула"],
        ]
        for row, values in enumerate(input_rows):
            set_row(inputs, row, values)
        format_sheet(inputs, [9000, 4000, 4500, 5000])

        baseline = sheets.getByName("Baseline")
        baseline_rows = [
            ["День", "Заявки", "Минуты ручной работы", "Среднее минут/заявку", "Статус"],
            ["День 1", 0, 0, "=IF(B2=0;0;C2/B2)", "Заполнить заказчиком"],
            ["День 2", 0, 0, "=IF(B3=0;0;C3/B3)", "Заполнить заказчиком"],
            ["День 3", 0, 0, "=IF(B4=0;0;C4/B4)", "Заполнить заказчиком"],
            ["День 4", 0, 0, "=IF(B5=0;0;C5/B5)", "Заполнить заказчиком"],
            ["День 5", 0, 0, "=IF(B6=0;0;C6/B6)", "Заполнить заказчиком"],
            ["День 6", 0, 0, "=IF(B7=0;0;C7/B7)", "Заполнить заказчиком"],
            ["День 7", 0, 0, "=IF(B8=0;0;C8/B8)", "Заполнить заказчиком"],
            ["Итого/среднее", "=SUM(B2:B8)", "=SUM(C2:C8)", "=IF(B9=0;0;C9/B9)", "После замера заменить Inputs.B2:B3"],
        ]
        for row, values in enumerate(baseline_rows):
            set_row(baseline, row, values)
        format_sheet(baseline, [6500, 3500, 6000, 6500, 9500])

        tco = sheets.getByName("TCO")
        tco_rows = [
            ["Статья", "Год 0", "Год 1", "Год 2", "Год 3", "Итого"],
            ["Разработка и настройка", 18000, 0, 0, 0, "=SUM(B2:E2)"],
            ["Миграция данных", 1500, 0, 0, 0, "=SUM(B3:E3)"],
            ["Обучение пользователей", 800, 0, 0, 0, "=SUM(B4:E4)"],
            ["Поддержка и исправления", 0, 6000, 6000, 6000, "=SUM(B5:E5)"],
            ["Инфраструктура", 0, 2400, 2400, 2400, "=SUM(B6:E6)"],
            ["Вывод старого решения", 0, 500, 0, 0, "=SUM(B7:E7)"],
            ["Итого", "=SUM(B2:B7)", "=SUM(C2:C7)", "=SUM(D2:D7)", "=SUM(E2:E7)", "=SUM(F2:F7)"],
        ]
        for row, values in enumerate(tco_rows):
            set_row(tco, row, values)
        format_sheet(tco, [9000, 3000, 3000, 3000, 3000, 3500])

        cash = sheets.getByName("CashFlow")
        cash_rows = [
            ["Показатель", "Год 0", "Год 1", "Год 2", "Год 3"],
            ["Выгоды", 0, "=Inputs.B11", "=Inputs.B11", "=Inputs.B11"],
            ["Затраты", "=TCO.B8", "=TCO.C8", "=TCO.D8", "=TCO.E8"],
            ["Чистый поток", "=B2-B3", "=C2-C3", "=D2-D3", "=E2-E3"],
            ["Накопленный поток", "=B4", "=B5+C4", "=C5+D4", "=D5+E4"],
            ["ROI за 3 года", "=(SUM(B2:E2)-SUM(B3:E3))/SUM(B3:E3)", "", "", ""],
            ["NPV при ставке Inputs.B8", "=B4+NPV(Inputs.B8;C4:E4)", "", "", ""],
            ["Срок окупаемости, лет", "=1+(-B5/C4)", "", "", ""],
            ["Стоимость задержки/месяц", "=Inputs.B11/12", "", "", ""],
        ]
        for row, values in enumerate(cash_rows):
            set_row(cash, row, values)
        format_sheet(cash, [11000, 4000, 4000, 4000, 4000])

        sensitivity = sheets.getByName("Sensitivity")
        sensitivity_rows = [
            ["Сценарий", "Эффект за 3 года", "TCO", "ROI"],
            ["Базовый", "=Inputs.B11*3", "=TCO.F8", "=(B2-C2)/C2"],
            ["Затраты +30%", "=B2", "=C2*1.3", "=(B3-C3)/C3"],
            ["Эффект 50%", "=B2*0.5", "=C2", "=(B4-C4)/C4"],
            ["Оба фактора", "=B2*0.5", "=C2*1.3", "=(B5-C5)/C5"],
            ["Безубыточный эффект/год", "=C2/3", "", "=B6/Inputs.B11"],
        ]
        for row, values in enumerate(sensitivity_rows):
            set_row(sensitivity, row, values)
        format_sheet(sensitivity, [9000, 5000, 4000, 4000])

        sources = sheets.getByName("Sources")
        source_rows = [
            ["Показатель", "Значение", "Источник/пометка", "Дата", "Ответственный"],
            ["Входящие заявки", 60, "Допущение; заменить недельным журналом заказчика", "2026-09-25", "PO"],
            ["Ручная обработка", 30, "Допущение; заменить хронометражом за 7 дней", "2026-09-25", "Заказчик"],
            ["Стоимость часа", 10, "Допущение; запросить у финансовой службы", "2026-09-25", "Финансы"],
            ["Эффект ошибок", 4000, "Допущение; подтвердить журналом инцидентов", "2026-09-25", "PO"],
            ["Эффект конверсии", 6000, "Допущение; подтвердить аналитикой пилота", "2026-09-25", "PO"],
            ["Ставка дисконтирования", 0.15, "Допущение; заменить ставкой финансовой службы", "2026-09-25", "Финансы"],
            ["Инфраструктура", 2400, "Допущение; подтвердить публичным калькулятором после выбора размещения", "2026-09-25", "DevOps"],
        ]
        for row, values in enumerate(source_rows):
            set_row(sources, row, values)
        format_sheet(sources, [8000, 3500, 14000, 3500, 5000])

        document.storeAsURL(uno.systemPathToFileUrl(OUTPUT), (prop("FilterName", "calc8"),))
        document.close(True)
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    main()