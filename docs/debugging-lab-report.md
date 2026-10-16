# Debugging есебі: бронь сомасын есептеу

Бұл есеп оқу мақсатындағы оқшауланған мысал үшін дайындалды. Негізгі
SaparTravel кодына әдейі қате енгізілген жоқ.

## Файлдар

- Бағдарлама: [`backend/debugging_lab/booking_total.py`](../backend/debugging_lab/booking_total.py)
- Тесттер: [`backend/debugging_lab/test_booking_total.py`](../backend/debugging_lab/test_booking_total.py)

## 1. Бастапқы іске қосу

Тестті файлды тікелей `python` арқылы емес, `pytest` модулі арқылы іске қосу
керек. Себебі `debugging_lab` импорты үшін жұмыс каталогы `backend` болуы тиіс.

```bash
cd /home/akira/IdeaProjects/SaparTravel/backend
/home/akira/IdeaProjects/SaparTravel/.venv/bin/python \
  -m pytest debugging_lab/test_booking_total.py -q
```

Бастапқы нәтиже:

```text
FF.   [100%]
2 failed, 1 passed
```

Егер `python test_booking_total.py` командасы қолданылса, `ModuleNotFoundError:
No module named 'debugging_lab'` шығуы мүмкін. Бұл есептелетін бағдарлама қатесі
емес, тестті қате іске қосу тәсілі.

## 2. Бірінші қате: қате есептеу

### Қатені жеке қайта шығару

Бірінші тестті ғана іске қосыңыз:

```bash
cd /home/akira/IdeaProjects/SaparTravel/backend
/home/akira/IdeaProjects/SaparTravel/.venv/bin/python \
  -m pytest debugging_lab/test_booking_total.py::test_calculate_booking_total_includes_service_fee -q
```

Нәтиже:

```text
AssertionError: assert Decimal('255.00') == Decimal('260.00')
```

### Талдау

Қате жол: [`booking_total.py:25`](../backend/debugging_lab/booking_total.py:25).

```python
total = subtotal + (service_fee / tickets)
```

`tickets=2` болғанда:

```text
subtotal = 125.00 * 2 = 250.00
service_fee / tickets = 10.00 / 2 = 5.00
total = 250.00 + 5.00 = 255.00
```

Күтілетін бизнес-ереже бойынша сервис ақысы билет санына бөлінбейді:

```text
250.00 + 10.00 = 260.00
```

### Debug әрекеттері

1. [booking_total.py:25](../backend/debugging_lab/booking_total.py:25)
   жолына breakpoint қойыңыз.
2. VS Code-та `Python Debugger: Debug Python File` емес, pytest конфигурациясы
   арқылы бірінші тестті Debug режимінде іске қосыңыз.
3. **Step Into** арқылы `calculate_booking_total` функциясына кіріңіз.
4. **Step Over** арқылы логтау және `subtotal` жолдарынан өтіңіз.
5. Variables панелінде мына мәндерді бақылаңыз:
   `price_per_ticket=125.00`, `tickets=2`, `service_fee=10.00`,
   `subtotal=250.00`.
6. `total=255.00` болғанын белгілеңіз.
7. **Step Out** арқылы тестке оралып, Call Stack-ті талдаңыз:
   `test_calculate_booking_total_includes_service_fee` →
   `calculate_booking_total`.

### Бірінші қатені түзету

`booking_total.py` файлындағы 26-жолды мынаған ауыстырыңыз:

```python
total = subtotal + service_fee
```

Бірінші тестті қайта іске қосыңыз:

```bash
/home/akira/IdeaProjects/SaparTravel/.venv/bin/python \
  -m pytest debugging_lab/test_booking_total.py::test_calculate_booking_total_includes_service_fee -q
```

Күтілетін нәтиже:

```text
1 passed
```

## 3. Екінші қате: нөлге бөлу

Бұл қатені көрсету үшін бірінші қатені түзеткеннен кейін демонстрациялық жолды
уақытша қайта қойыңыз:

```python
total = subtotal + (service_fee / tickets)
```

Екінші тестті ғана іске қосыңыз:

```bash
cd /home/akira/IdeaProjects/SaparTravel/backend
/home/akira/IdeaProjects/SaparTravel/.venv/bin/python \
  -m pytest debugging_lab/test_booking_total.py::test_zero_tickets_still_returns_service_fee -q
```

Нәтиже:

```text
decimal.DivisionByZero: [<class 'decimal.DivisionByZero'>]
```

Stack Trace:

```text
test_zero_tickets_still_returns_service_fee
→ calculate_booking_total
→ service_fee / tickets
```

Variables:

```text
price_per_ticket = Decimal("125.00")
tickets = 0
service_fee = Decimal("10.00")
subtotal = Decimal("0.00")
```

Себеп: `Decimal("10.00") / 0` орындалып жатыр. Бұл жерде де дұрыс түзету —
сервис ақысын бөлмей, бір рет қосу:

```python
total = subtotal + service_fee
```

Екінші тестті қайта іске қосыңыз:

```bash
/home/akira/IdeaProjects/SaparTravel/.venv/bin/python \
  -m pytest debugging_lab/test_booking_total.py::test_zero_tickets_still_returns_service_fee -q
```

Күтілетін нәтиже:

```text
1 passed
```

## 4. Үшінші тест және regression тексеруі

Теріс билет саны үшін `ValueError` күтіледі:

```bash
/home/akira/IdeaProjects/SaparTravel/.venv/bin/python \
  -m pytest debugging_lab/test_booking_total.py::test_negative_ticket_count_is_rejected -q
```

Күтілетін нәтиже:

```text
1 passed
```

Барлық тесттерді қайта іске қосыңыз:

```bash
/home/akira/IdeaProjects/SaparTravel/.venv/bin/python \
  -m pytest debugging_lab/test_booking_total.py -q
```

Соңғы нәтиже:

```text
...   [100%]
3 passed
```

## 5. Logging

Функция кіріс параметрлерін және есептелген нәтижені `logger.info` арқылы жазады:

- [booking_total.py:15](../backend/debugging_lab/booking_total.py:15)
- [booking_total.py:26](../backend/debugging_lab/booking_total.py:26)

Логты көру үшін:

```bash
cd /home/akira/IdeaProjects/SaparTravel/backend
/home/akira/IdeaProjects/SaparTravel/.venv/bin/python debugging_lab/booking_total.py
```

Күтілетін есеп:

```text
subtotal=250.00 total=260.00
260.00
```

## 6. 20 қадамның қорытындысы

1. Қате коды бар оқшауланған бағдарлама таңдалды.
2. Бірінші қате жеке тест арқылы қайта шығарылды.
3. `AssertionError` Error Message анықталды.
4. Оның Stack Trace талданды.
5. Қате [booking_total.py:25](../backend/debugging_lab/booking_total.py:25)
   жолынан табылды.
6. Осы жолға breakpoint қойылды.
7. Тест Debug режимінде іске қосылды.
8. Variables мәндері бақыланды.
9. Step Over қолданылды.
10. Step Into қолданылды.
11. Step Out қолданылды.
12. Call Stack талданды.
13. Logging кодта бар және іске қосылды.
14. Root cause анықталды: сервис ақысы қате бөлінген.
15. Код `subtotal + service_fee` түріне түзетілді.
16. Бірінші тест қайта орындалды.
17. Барлық regression тесттер орындалды.
18. `255.00`/`DivisionByZero` нәтижелері `260.00`/`10.00` нәтижелерімен
    салыстырылды.
19. Defect report осы есепте тіркелді.
20. Debugging есебі, командалар және файл сілтемелері рәсімделді.
