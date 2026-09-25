from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "requirements" / "story-map.png"
WIDTH, HEIGHT = 2400, 1500
BACKGROUND = (247, 244, 238)
INK = (32, 42, 51)
MUTED = (91, 105, 112)
MVP = (225, 239, 232)
RELEASE_2 = (232, 237, 247)
POST_MVP = (245, 232, 218)
LINE = (151, 162, 165)


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(name, size)


def centered(draw, box, text, fill=INK, text_font=None):
    left, top, right, bottom = box
    bounds = draw.multiline_textbbox((0, 0), text, font=text_font, spacing=8, align="center")
    x = left + (right - left - (bounds[2] - bounds[0])) / 2
    y = top + (bottom - top - (bounds[3] - bounds[1])) / 2
    draw.multiline_text((x, y), text, fill=fill, font=text_font, spacing=8, align="center")


def main():
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    margin = 70
    title_font = font(52, True)
    subtitle_font = font(25)
    header_font = font(30, True)
    card_font = font(24)
    small_font = font(21)

    draw.text((margin, 42), "SaparTravel Story Map", fill=INK, font=title_font)
    draw.text(
        (margin, 112),
        "Сквозной путь туриста: найти тур → изучить условия → выбрать выезд → отправить заявку → отследить статус",
        fill=MUTED,
        font=subtitle_font,
    )

    labels = ["Найти тур", "Изучить условия", "Выбрать выезд", "Отправить заявку", "Отследить статус"]
    cards = [
        [("Каталог опубликованных туров", "ST-01"), ("Поиск по направлению", "ST-02"), ("Фильтры цены и длительности", "ST-03")],
        [("Карточка тура", "ST-04"), ("Программа и цена", "ST-04"), ("Условия поставщика", "ST-04")],
        [("Дата выезда", "ST-05"), ("Свободные места", "ST-06"), ("Количество участников", "ST-05")],
        [("Регистрация и вход", "ST-07"), ("Расчёт стоимости", "ST-07"), ("Создание заявки", "ST-10")],
        [("Кабинет и статусы", "ST-10"), ("Отмена заявки", "ST-11"), ("Подтверждение поставщика", "ST-09")],
    ]
    release_2 = ["Сохранённые фильтры", "Сравнение", "Уведомление", "Email/SMS", "Уведомления"]
    post_mvp = ["Рекомендации", "Отзывы", "Внешняя синхронизация", "Онлайн-оплата", "Возвраты и аналитика"]

    gap = 20
    column_width = (WIDTH - 2 * margin - 4 * gap) // 5
    header_top, header_bottom = 185, 285
    card_top, card_height, card_gap = 315, 125, 18
    release2_top, release2_height = 795, 125
    post_top, post_height = 955, 125

    for index, label in enumerate(labels):
        left = margin + index * (column_width + gap)
        right = left + column_width
        draw.rounded_rectangle((left, header_top, right, header_bottom), radius=14, fill=INK)
        centered(draw, (left + 14, header_top + 12, right - 14, header_bottom - 12), label, (255, 255, 255), header_font)

        for card_index, (text, story_id) in enumerate(cards[index]):
            top = card_top + card_index * (card_height + card_gap)
            draw.rounded_rectangle((left, top, right, top + card_height), radius=12, fill=MVP, outline=LINE, width=2)
            centered(draw, (left + 16, top + 16, right - 16, top + 75), text, INK, card_font)
            centered(draw, (left + 16, top + 78, right - 16, top + 112), story_id, MUTED, small_font)

        draw.rounded_rectangle((left, release2_top, right, release2_top + release2_height), radius=12, fill=RELEASE_2, outline=LINE, width=2)
        centered(draw, (left + 16, release2_top + 18, right - 16, release2_top + 105), release_2[index], INK, card_font)

        draw.rounded_rectangle((left, post_top, right, post_top + post_height), radius=12, fill=POST_MVP, outline=LINE, width=2)
        centered(draw, (left + 16, post_top + 18, right - 16, post_top + 105), post_mvp[index], INK, card_font)

    line_y = 760
    draw.line((margin - 20, line_y, WIDTH - margin + 20, line_y), fill=(178, 65, 52), width=7)
    draw.text((WIDTH - margin - 330, line_y - 48), "MVP-срез", fill=(178, 65, 52), font=header_font)
    draw.text((margin, 1320), "MVP: полный путь от каталога до статуса заявки. Цвета: MVP / Release 2 / после MVP.", fill=MUTED, font=subtitle_font)
    image.save(OUTPUT, "PNG", optimize=True)


if __name__ == "__main__":
    main()