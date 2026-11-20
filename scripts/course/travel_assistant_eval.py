"""Evaluate the deployed travel-filter extraction prompt against a provisional JSONL set."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals/travel-assistant/dataset.jsonl"
OUTPUT = ROOT / "docs/labs/lab-12/travel-assistant-evidence"
PRICE_DATE = "2026-11-20"
INPUT_USD_PER_MILLION = 0.30
OUTPUT_USD_PER_MILLION = 2.50
SELF_HOST_FIXED_USD = 64.0
FIELDS = ("budget", "category", "duration_max", "travelers", "destination_slug", "date_from", "date_to")

DESTINATIONS = {
    "argentina": ("аргентин", "argentina", "патагон"),
    "australia": ("австрали", "australia", "квинсленд"),
    "brazil": ("бразил", "brazil", "рио"),
    "canada": ("канад", "canada", "банф"),
    "costa-rica": ("коста-рик", "costa rica"),
    "egypt": ("егип", "egypt", "луксор"),
    "france": ("франц", "france", "прованс", "париж", "paris"),
    "georgia": ("грузи", "georgia", "тбилиси", "кахет"),
    "iceland": ("исланд", "iceland"),
    "india": ("инд", "india", "джайпур"),
    "indonesia": ("индонез", "indonesia", "бали", "bali"),
    "italy": ("итал", "italy", "тоскана"),
    "japan": ("япони", "japan", "киото", "kyoto"),
    "kazakhstan": ("казахстан", "алматы", "kazakhstan"),
    "mexico": ("мексик", "mexico", "оахака"),
    "morocco": ("марокк", "morocco", "марракеш"),
    "new-zealand": ("новую зеланди", "новая зеланди", "new zealand", "куинстаун"),
    "peru": ("перу", "peru", "куско"),
    "south-africa": (r"южн\w+ африк", "south africa", "кейптаун"),
    "spain": ("испан", "spain", "севиль"),
    "tanzania": ("танзани", "tanzania", "аруша"),
    "thailand": ("таиланд", "тайланд", "thailand", "чиангмай"),
    "turkey": ("турци", "турцию", "турция", "түркия", "turkey", "каппадок"),
    "usa": ("сша", "usa", "юта", "моаб"),
}

CATEGORY_RULES = {
    "Beach": ("пляж", "море", "берег", "жағажай", "beach"),
    "Adventure": ("приключ", "активн", "поход", "adventure", "hiking"),
    "Culture": ("культур", "музей", "историческ", "архитектур", "culture", "history"),
    "City": ("city break", "городск", "городской тур", "city trip"),
    "Food": ("гастроном", "гастротур", "кухн", "еда", "food", "culinary"),
    "Nature": ("природ", "горы", "горный", "водопад", "nature", "mountain"),
}

NUMBER_WORDS = {
    "один": 1, "одна": 1, "одному": 1, "one": 1, "бір": 1,
    "двое": 2, "двоих": 2, "двух": 2, "двумя": 2, "two": 2, "екі": 2,
    "трое": 3, "троих": 3, "трёх": 3, "три": 3, "three": 3, "үш": 3,
    "четверо": 4, "четверых": 4, "четыре": 4, "four": 4, "төрт": 4,
    "пятеро": 5, "пять": 5, "five": 5,
}

MONTHS = {
    "январе": 1, "января": 1, "феврале": 2, "февраля": 2,
    "марте": 3, "марта": 3, "апреле": 4, "апреля": 4,
    "мае": 5, "май": 5, "июне": 6, "июня": 6,
    "июле": 7, "июля": 7, "августе": 8, "августа": 8,
    "сентябре": 9, "сентября": 9, "октябре": 10, "октября": 10,
    "ноябре": 11, "ноября": 11, "декабре": 12, "декабря": 12,
}


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("'\""))


def _number(raw: str) -> int | None:
    cleaned = raw.replace("\u00a0", "").replace(" ", "")
    million = bool(re.search(r"млн|миллион\w*|million|m\b", raw, re.I))
    thousand = bool(re.search(r"тыс|тысяч|мың|k\b|к\b", raw, re.I))
    cleaned = re.sub(r"млн\.?|миллион\w*|million|тыс\.?|тысяч\w*|мың\w*|тенге\w*|теңге\w*|тг|kzt|₸|(?<=\d)[mkк]\b", "", cleaned, flags=re.I)
    if re.search(r",\d{3}$", cleaned):
        cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if million:
        return round(value * 1_000_000)
    return round(value * (1000 if value < 10000 and thousand else 1))


def _text(messages: list[dict]) -> str:
    return " ".join(row["content"] for row in messages if row["role"] == "user").casefold()


def rules_baseline(row: dict) -> dict:
    """Transparent keyword/regex baseline; unrecognized values stay empty."""
    text = _text(row["messages"])
    budget = None
    budget_patterns = (
        r"(?:бюджет|лимит|максимум|максимально|\bдо\b|не дороже|не больше|under|below|maximum|max(?:imum)?|бюджеті|аспасын)\s*(?:до\s*)?([\d][\d\s,.]*)\s*(млн\.?|миллион\w*|million|m\b|тыс\.?|тысяч|мың\w*|k\b|к\b)?",
        r"([\d][\d\s,.]*)\s*(млн\.?|миллион\w*|million|m\b|тыс\.?|тысяч\w*|мың\w*|k\b|к\b)?\s*(?:₸|тг\b|тенге\w*|теңге\w*|kzt)",
    )
    budget_matches = []
    for pattern in budget_patterns:
        for match in re.finditer(pattern, text, re.I):
            raw = match.group(1) + (match.group(2) or "")
            parsed_budget = _number(raw)
            if parsed_budget is not None:
                budget_matches.append((match.start(), parsed_budget, match.group(0)))
    if budget_matches:
        total_matches = [item for item in budget_matches
                         if re.search(r"всего|на всех|total|whole group", text[max(0, item[0]-24):item[0]+80], re.I)]
        budget = (total_matches or budget_matches)[-1][1]

    travelers = None
    numeric_person = re.search(r"(?:нас|для|едем|мы|we are|for)\s*(\d{1,2})\s*(?:человек\w*|взросл\w*|путешественник\w*|адам\w*|people|travelers|persons)?", text)
    numeric_person_with_noun = re.search(r"\b(\d{1,2})\s*(?:человек\w*|взросл\w*|путешественник\w*|people|travelers|persons)\b", text)
    if numeric_person:
        travelers = int(numeric_person.group(1))
    elif numeric_person_with_noun:
        travelers = int(numeric_person_with_noun.group(1))
    else:
        group_forms = (("вдвоём", 2), ("вдвоем", 2), ("едем вдвоём", 2), ("я один", 1),
                       ("втроём", 3), ("втроем", 3), ("вчетвером", 4),
                       ("одна путешественница", 1), ("один путешественник", 1))
        for phrase, number in group_forms:
            if phrase in text:
                travelers = number
                break
        for phrase, number in sorted(NUMBER_WORDS.items(), key=lambda item: -len(item[0])):
            if travelers is None and (re.search(rf"(?:нас|едем|на|для|we are|for)\s+{re.escape(phrase)}\b", text)
                                      or re.search(rf"{re.escape(phrase)}\s+(?:адам\w*|человек\w*|взросл\w*|people|travelers?)", text)):
                travelers = number
                break
        if travelers is None:
            bare_group = re.search(r"\b(двое|двоих|двух|двумя|трое|трёх|троих|четверо|четверых|четыре|пятеро)\b", text)
            if bare_group:
                travelers = NUMBER_WORDS.get(bare_group.group(1), {"троих": 3}.get(bare_group.group(1)))
        if travelers is None:
            standalone = re.search(r"\b(один|одна|одному|one|двое|двух|двумя|трое|трёх|три|четверо|четыре|пятеро|пять)\s+(?:взросл\w*|человек\w*|путешественник\w*|person|people|travelers?)\b", text)
            if standalone:
                travelers = NUMBER_WORDS.get(standalone.group(1))

    duration = None
    duration_match = re.search(r"(?:(?:на|до|for)\s*)?(\d{1,2})\s*(?:дн\w*|день|days?|күн\w*)", text)
    if duration_match:
        duration = int(duration_match.group(1))
    else:
        duration_word = re.search(r"\b(один|одна|два|две|три|четыре|пять|шесть|семь|восемь|десять|one|two|three|four|five|six|seven|eight|ten)\s+(?:дн\w*|дней|день|days?)\b", text)
        duration_values = {"один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
                           "шесть": 6, "семь": 7, "восемь": 8, "десять": 10, "one": 1, "two": 2,
                           "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "ten": 10}
        if duration_word:
            duration = duration_values[duration_word.group(1)]
        elif re.search(r"недел\w*|week", text):
            duration = 7
    if duration is None and re.search(r"выходн\w*|weekend", text):
        duration = 3

    category = None
    for code, words in CATEGORY_RULES.items():
        if any(word in text for word in words):
            category = code
            break

    destination = None
    for slug, words in DESTINATIONS.items():
        if any(re.search(word, text) for word in words):
            destination = slug
            break

    date_from = date_to = None
    exact = re.search(r"(20\d{2}-\d{2}-\d{2})\s*(?:по|to|-)\s*(20\d{2}-\d{2}-\d{2})", text)
    if exact:
        date_from, date_to = exact.groups()
    else:
        month_match = re.search(r"\b(" + "|".join(MONTHS) + r")\s*(?:20\d{2})?", text)
        if month_match:
            month = MONTHS[month_match.group(1)]
            year_match = re.search(r"20\d{2}", text)
            year = int(year_match.group()) if year_match else 2027
            last_day = (31 if month in {1, 3, 5, 7, 8, 10, 12} else
                        30 if month in {4, 6, 9, 11} else
                        29 if year % 4 == 0 else 28)
            date_from, date_to = f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"

    filters = {
        "budget": budget,
        "category": category,
        "duration_max": duration,
        "travelers": travelers or 1,
        "destination_slug": destination,
        "date_from": date_from,
        "date_to": date_to,
    }
    no_trip_intent = bool(re.fullmatch(r"\s*(?:привет|hello|hi|сәлем)[!. ]*", text))
    return {"search": not no_trip_intent, "filters": filters}


def _examples() -> str:
    return (
        "\nParsing examples (follow the JSON format; examples are demonstrations, not facts about available tours):\n"
        'User: "Культурный тур в Марокко на 4 дня, я один, максимум 400000 тенге."\n'
        'JSON: {"reply":"Подберу культурные варианты в Марокко.","search":true,"filters":{"budget":400000,"category":"Culture","duration_max":4,"travelers":1,"destination_slug":"morocco","date_from":"","date_to":""}}\n'
        'User: "Nature trip in Costa Rica for three people, six days, up to 700000 KZT."\n'
        'JSON: {"reply":"I will look for nature trips in Costa Rica.","search":true,"filters":{"budget":700000,"category":"Nature","duration_max":6,"travelers":3,"destination_slug":"costa-rica","date_from":"","date_to":""}}\n'
        'User: "Еда и местная кухня в Танзании на 5 дней, для двух человек, до 650000 ₸."\n'
        'JSON: {"reply":"Подберу гастрономические варианты в Танзании.","search":true,"filters":{"budget":650000,"category":"Food","duration_max":5,"travelers":2,"destination_slug":"tanzania","date_from":"","date_to":""}}\n'
    )


def _request_json(url: str, body: dict, api_key: str, timeout: int = 45) -> dict:
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                      headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
    for attempt in range(5):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read(2_000_000).decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < 4:
                time.sleep(min(60, 15 * (attempt + 1)))
                continue
            raise RuntimeError(f"Gemini request failed with HTTP {exc.code}; response body suppressed") from None
        except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            if attempt == 4:
                raise RuntimeError("Gemini request failed; response details suppressed") from None
            time.sleep(2 ** attempt)
    raise RuntimeError("Gemini request failed after retries")


def _contents(messages: list[dict]) -> list[dict]:
    values = [{"role": "model" if item["role"] == "assistant" else "user",
               "parts": [{"text": item["content"]}]} for item in messages]
    return values[1:] if values and values[0]["role"] == "model" else values


def _parse_filters(value: dict, category_codes: set[str], destination_slugs: set[str]) -> dict:
    filters = value.get("filters") or {}
    category = filters.get("category") or None
    destination = filters.get("destination_slug") or None
    date_from, date_to = filters.get("date_from") or None, filters.get("date_to") or None
    if category not in category_codes:
        category = None
    if destination not in destination_slugs:
        destination = None
    for key, val in (("date_from", date_from), ("date_to", date_to)):
        if val:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except (TypeError, ValueError):
                if key == "date_from":
                    date_from = None
                else:
                    date_to = None
    if date_from and date_to and date_to < date_from:
        date_from = date_to = None
    return {
        "budget": filters.get("budget") or None,
        "category": category,
        "duration_max": filters.get("duration_max") or None,
        "travelers": filters.get("travelers") or 1,
        "destination_slug": destination,
        "date_from": date_from,
        "date_to": date_to,
    }


def _ask(row: dict, *, mode: str, model: str, api_key: str, categories: list[dict], destinations: list[dict]) -> dict:
    from app.services.travel_assistant_service import (
        ParsedTurn,
        _instructions,
        _budget_from_message,
        _merge_current_filters,
        _normalize_current_filters,
        _schema,
        _should_search,
    )

    lang = row["lang"]
    category_codes = {x["code"] for x in categories}
    destination_slugs = {x["slug"] for x in destinations}
    current_filters = _normalize_current_filters(row.get("current_filters"), category_codes, destination_slugs)
    instruction = _instructions(lang, categories, destinations, current_filters)
    if mode == "few-shot":
        instruction += _examples()
    contents = _contents(row["messages"])
    body = {
        "systemInstruction": {"parts": [{"text": instruction}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0,
            "seed": 42,
            "maxOutputTokens": 700,
            "responseMimeType": "application/json",
            "responseJsonSchema": _schema([item["code"] for item in categories],
                                           [item["slug"] for item in destinations]),
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    raw = _request_json(url, body, api_key)
    text = raw["candidates"][0]["content"]["parts"][0]["text"]
    parsed = ParsedTurn.model_validate_json(text)
    latest_user = next(item["content"] for item in reversed(row["messages"]) if item["role"] == "user")
    merged_filters = _merge_current_filters(parsed.filters, current_filters, latest_user, parsed.reply)
    explicit_budget = _budget_from_message(latest_user)
    if explicit_budget is not None:
        merged_filters.budget = explicit_budget
    search = _should_search(parsed, merged_filters, row["messages"], current_filters)
    return {
        "id": row["id"], "mode": mode, "model": raw.get("modelVersion", model),
        "prediction": {"search": search,
                       "filters": _parse_filters({"filters": merged_filters.model_dump()}, category_codes,
                                                 destination_slugs)},
        "raw_response": text,
        "usage": raw.get("usageMetadata", {}),
        "temperature": 0, "seed": 42,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def _quality(rows: list[dict], predictions: list[dict]) -> dict:
    per_field = {}
    exact_records = 0
    tp_total = fp_total = fn_total = 0
    for field in ("search", *FIELDS):
        tp = fp = fn = support = correct = 0
        for row, predicted in zip(rows, predictions):
            expected = row["expected"]["search"] if field == "search" else row["expected"]["filters"][field]
            actual = predicted["search"] if field == "search" else predicted["filters"][field]
            support += expected is not None and expected is not False
            if expected == actual:
                correct += 1
            if expected is not None and expected is not False and expected == actual:
                tp += 1
            elif actual is not None and actual is not False and actual != expected:
                fp += 1
                if expected is not None and expected is not False:
                    fn += 1
            elif expected is not None and expected is not False:
                fn += 1
        f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0
        per_field[field] = {"support": support, "exact_correct": correct,
                            "exact_accuracy": correct / len(rows), "tp": tp, "fp": fp, "fn": fn, "f1": f1}
        if field != "search":
            tp_total += tp
            fp_total += fp
            fn_total += fn
    for row, predicted in zip(rows, predictions):
        if row["expected"]["search"] == predicted["search"] and row["expected"]["filters"] == predicted["filters"]:
            exact_records += 1
    return {
        "examples": len(rows), "exact_record_match": exact_records / len(rows),
        "macro_f1_slots": statistics.mean(per_field[field]["f1"] for field in FIELDS),
        "micro_f1_slots": 2 * tp_total / (2 * tp_total + fp_total + fn_total) if 2 * tp_total + fp_total + fn_total else 0,
        "search_accuracy": per_field["search"]["exact_accuracy"], "per_field": per_field,
    }


def _cost(rows: list[dict], outputs: dict[str, list[dict]]) -> dict:
    modes = {}
    for mode, values in outputs.items():
        input_tokens = [int(item.get("usage", {}).get("promptTokenCount", 0)) for item in values]
        visible_tokens = [int(item.get("usage", {}).get("candidatesTokenCount", 0)) for item in values]
        thinking_tokens = [int(item.get("usage", {}).get("thoughtsTokenCount", 0)) for item in values]
        output_tokens = [visible + thoughts for visible, thoughts in zip(visible_tokens, thinking_tokens)]
        mean_input = statistics.mean(input_tokens) if input_tokens else 0
        mean_output = statistics.mean(output_tokens) if output_tokens else 0
        per_request = (mean_input * INPUT_USD_PER_MILLION + mean_output * OUTPUT_USD_PER_MILLION) / 1_000_000
        modes[mode] = {
            "measured_requests": len(values), "mean_input_tokens_gemini": mean_input,
            "mean_output_billable_tokens_gemini": mean_output,
            "mean_visible_output_tokens_gemini": statistics.mean(visible_tokens) if visible_tokens else 0,
            "mean_thinking_tokens_gemini": statistics.mean(thinking_tokens) if thinking_tokens else 0,
            "total_input_tokens": sum(input_tokens), "total_output_tokens": sum(output_tokens),
            "estimated_cost_per_request_paid_usd": per_request,
            "scenarios_paid_usd": {str(n): n * per_request for n in (10000, 100000)},
            "estimated_break_even_requests_month": SELF_HOST_FIXED_USD / per_request if per_request else None,
        }
    return {
        "price_date": PRICE_DATE, "api_source": "https://ai.google.dev/gemini-api/docs/pricing",
        "model": os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        "input_usd_per_million": INPUT_USD_PER_MILLION, "output_usd_per_million": OUTPUT_USD_PER_MILLION,
        "self_host_fixed_monthly_usd_assumption": SELF_HOST_FIXED_USD,
        "self_host_fixed_basis": "Planning assumption inherited from LZ8: USD 24 infrastructure + USD 40 administration; not an actual invoice.",
        "scenarios_are_paid_tier_estimates": True,
        "token_counts_source": "Gemini usageMetadata returned by the actual generateContent requests; includes the model tokenizer's input/output counts.",
        "api_invoice_is_actual": False,
        "local_invoice_total": None,
        "models": modes,
        "limitations": [
            "A free tier may make actual API charges zero within its quotas; estimates use the published standard paid tier.",
            "Self-host break-even is arithmetic only; required throughput, hardware capacity, availability and quality at that scale are not measured.",
            "Synthetic provisional test prompts are not real customer traffic and are not human-approved gold labels.",
        ],
    }


def run(*, output: Path, model: str, sleep_seconds: float, overwrite: bool,
       only_mode: str | None = None, human_gold: Path | None = None) -> dict:
    _load_env_file(ROOT / ".env")
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in the environment or ignored .env file")
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise RuntimeError(f"Output directory is non-empty: {output}; use --overwrite only to replace it")
    output.mkdir(parents=True, exist_ok=True)
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from app.services.travel_assistant_service import _schema

    catalogs = {}
    for lang in ("ru", "kk", "en"):
        with urlopen(f"https://sapartravel.onrender.com/api/v1/categories?lang={lang}", timeout=20) as response:
            category_items = json.load(response)["items"]
        with urlopen(f"https://sapartravel.onrender.com/api/v1/destinations?lang={lang}", timeout=20) as response:
            destination_items = json.load(response)["items"]
        # Match the production service: pass only localized labels, never descriptions or image URLs.
        categories = [{"code": item["code"], "name": item.get("name_" + lang) or item["code"]}
                      for item in category_items]
        destinations = [{"slug": item["slug"], "name": item["name"], "country": item["country"]}
                        for item in destination_items]
        if not categories or not destinations:
            raise RuntimeError(f"The public {lang} catalog returned no categories or destinations")
        if not _schema([x["code"] for x in categories], [x["slug"] for x in destinations]):
            raise RuntimeError(f"Could not build the structured output schema for {lang}")
        catalogs[lang] = {"categories": categories, "destinations": destinations}

    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) < 30 or sum(row.get("difficulty") == "hard" for row in rows) < 5:
        raise RuntimeError("Evaluation requires at least 30 examples and five difficult cases")
    gold_approved = False
    if human_gold:
        gold_rows = [json.loads(line) for line in human_gold.read_text(encoding="utf-8").splitlines() if line.strip()]
        if [row.get("id") for row in gold_rows] != [row["id"] for row in rows]:
            raise RuntimeError("Human gold must cover every dataset ID exactly once and in order")
        for row, gold in zip(rows, gold_rows):
            reviewers = gold.get("reviewers", [])
            if gold.get("annotation_status") != "two-human-reviewed" or len(set(reviewers)) < 2:
                raise RuntimeError(f"Human gold for {row['id']} lacks two distinct named reviewers")
            expected = gold.get("expected", {})
            if set(expected) != {"search", "filters"} or set(expected["filters"]) != set(FIELDS):
                raise RuntimeError(f"Human gold for {row['id']} does not include every expected field")
            row["expected"] = expected
        gold_approved = True
    rules = [rules_baseline(row) for row in rows]
    outputs: dict[str, list[dict]] = {"rules": []}
    rules_path = output / "rules.jsonl"
    rules_path.write_text("\n".join(json.dumps({"id": row["id"], "prediction": pred}, ensure_ascii=False)
                                    for row, pred in zip(rows, rules)) + "\n", encoding="utf-8")
    outputs["rules"] = rules

    if only_mode and only_mode not in {"zero-shot", "few-shot"}:
        raise ValueError("only_mode must be zero-shot or few-shot")
    for mode in ("zero-shot", "few-shot"):
        path = output / f"{mode}.jsonl"
        if only_mode and mode != only_mode:
            if not path.is_file():
                raise RuntimeError(f"Cannot preserve missing {mode} output while running only {only_mode}")
            previous = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if [item.get("id") for item in previous] != [row["id"] for row in rows]:
                raise RuntimeError(f"Existing {mode} output does not align with this dataset")
            outputs[mode] = [item["prediction"] for item in previous]
            continue
        values = []
        with path.open("w", encoding="utf-8") as stream:
            for index, row in enumerate(rows):
                result = _ask(row, mode=mode, model=model, api_key=api_key,
                              categories=catalogs[row["lang"]]["categories"],
                              destinations=catalogs[row["lang"]]["destinations"])
                values.append(result["prediction"])
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
                stream.flush()
                if sleep_seconds > 0 and index < len(rows) - 1:
                    time.sleep(sleep_seconds)
        outputs[mode] = values

    for mode, predictions in outputs.items():
        if len(predictions) != len(rows):
            raise RuntimeError(f"Incomplete model output for {mode}")
    raw_runs = {mode: [json.loads(line) for line in (output / f"{mode}.jsonl").read_text().splitlines() if line.strip()]
                for mode in ("zero-shot", "few-shot")}
    actual_versions = sorted({item.get("model", model) for values in raw_runs.values() for item in values})
    results = {
        "data_kind": "synthetic_provisional_evaluation",
        "lab": 12, "function": "Extract travel search filters from natural language",
        "gold_human_approved": gold_approved, "independent_human_annotators": 2 if gold_approved else 0,
        "examples": len(rows), "difficult_examples": sum(row["difficulty"] == "hard" for row in rows),
        "model": model, "actual_model_versions": actual_versions, "temperature": 0, "seed": 42,
        "catalog_context": "Production-equivalent shape per locale: category code/name; destination slug/name/country. No descriptions, image URLs or tour facts are sent.",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "dataset_sha256": hashlib.sha256(DATASET.read_bytes()).hexdigest(),
        "run_date_utc": datetime.now(timezone.utc).isoformat(),
        "acceptance_criterion": ">= 0.90 exact-record match, >= 0.95 exact accuracy for each field, and zero unsupported category/destination values; human review required before acceptance.",
        "metrics_are_provisional": True,
        "baseline_was_tuned_alongside_this_synthetic_development_set": True,
        "server_postprocessing": [
            "Carry forward the previous validated filters unless the latest user message changes them.",
            "Normalize explicitly written KZT totals, including Kazakh currency endings; multiply only when the user explicitly states a per-person amount.",
            "Repeat search for an explicit search request even when Gemini returns search=false, and preserve filters when budget changes or the visitor asks to search again.",
            "Do not search across destinations when the assistant has rejected an unsupported destination unless the visitor asks the assistant to choose.",
        ],
        "raw_model_json_is_preserved": True,
        "diagnostic_metrics": {mode: _quality(rows, predictions) for mode, predictions in outputs.items()},
        "errors": {
            mode: [{"id": row["id"], "difficulty": row["difficulty"], "expected": row["expected"], "predicted": predictions[index]}
                   for index, row in enumerate(rows)
                   if row["expected"] != predictions[index]]
            for mode, predictions in outputs.items()
        },
        "abstention_policy": "Unknown destinations/categories and invalid dates are cleared to null; prompt instructs the model to ask a clarification when dates are ambiguous. No calibrated numeric confidence score is exposed.",
        "limitations": [
            "Every case is synthetic and authored for this dry run; the set is not representative customer data.",
            "The deterministic baseline was built alongside these examples, so its score is a harness check rather than an unbiased comparison. Freeze rules and evaluate on new human-reviewed cases before deciding whether AI wins.",
            "Expected filters are AI-authored and remain provisional until two people independently annotate and a product owner adjudicates disagreements.",
            "Synthetic results do not establish conversion lift, time saved, or production error rates.",
            "The rules baseline is a deterministic extraction benchmark, while the deployed manual catalog form remains a stronger no-model fallback for actual visitors.",
        ],
    }
    cost = _cost(rows, raw_runs)
    (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "cost.json").write_text(json.dumps(cost, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--model", default=None)
    parser.add_argument("--sleep-seconds", type=float, default=4.2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--only-mode", choices=("zero-shot", "few-shot"))
    parser.add_argument("--human-gold", type=Path, default=None,
                        help="Use adjudicated two-human JSONL produced from the blind forms")
    args = parser.parse_args()
    _load_env_file(ROOT / ".env")
    model = args.model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    result = run(output=args.output, model=model, sleep_seconds=args.sleep_seconds, overwrite=args.overwrite,
                 only_mode=args.only_mode, human_gold=args.human_gold)
    print(json.dumps({"examples": result["examples"], "difficult_examples": result["difficult_examples"],
                      "gold_human_approved": result["gold_human_approved"],
                      "metrics": {key: value["exact_record_match"] for key, value in result["diagnostic_metrics"].items()}},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
