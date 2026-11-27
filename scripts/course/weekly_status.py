"""Generate a checked PM draft from measured facts; never publish or send it."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from scripts.course.gemini_api import generate
from scripts.course.ai import numeric_discrepancies
from scripts.course.metrics import stamp


def _claim_schema(facts):
    return {"type": "object", "properties": {
        "claims": {"type": "array", "items": {
            "type": "object", "properties": {
                "text": {"type": "string"},
                "source_keys": {"type": "array", "items": {"type": "string", "enum": sorted(facts)}},
            }, "required": ["text", "source_keys"],
        }},
    }, "required": ["claims"]}


def period_facts(snapshot, start, end):
    if not start < end:
        raise ValueError("Expected a nonempty reporting period")
    issues = snapshot["issues"]
    runs = [r for r in snapshot["runs"] if start <= stamp(r["created_at"]) < end]
    project_available = (snapshot.get("project_evidence") != "not_requested"
                         and not snapshot.get("project_items_truncated", False)
                         and isinstance(snapshot.get("project_items"), list))
    project_items = snapshot.get("project_items", []) if project_available else []
    project_statuses = [item.get("status") or "Unknown" for item in project_items]
    captured_at = snapshot.get("captured_at_utc")
    return {"period_start": start.date().isoformat(), "period_end_exclusive": end.date().isoformat(),
            "issues_created": sum(start <= stamp(r["created_at"]) < end for r in issues),
            "issues_closed": sum(bool(r["closed_at"]) and start <= stamp(r["closed_at"]) < end for r in issues),
            "issues_open_at_capture": sum(r.get("state") == "open" for r in issues),
            "issues_closed_at_capture": sum(r.get("state") == "closed" for r in issues),
            "project_in_progress_at_capture": sum(status in {"In progress", "FOR TEST", "Review"} for status in project_statuses) if project_available else None,
            "project_blocked_at_capture": sum(status == "Blocked" for status in project_statuses) if project_available else None,
            "project_status_capture_date": stamp(captured_at).date().isoformat() if captured_at else None,
            "ci_success": sum(r["conclusion"] == "success" for r in runs),
            "ci_failure": sum(r["conclusion"] == "failure" for r in runs),
            "recorded_deployments": sum(start <= stamp(r["created_at"]) < end for r in snapshot["deployments"]),
            "manual_deployments": None, "customer_approval": None,
            "sprint_goal": None, "measured_manual_minutes": None}


def _summary(result, facts, version):
    try:
        parsed = json.loads(result["text"])
    except (TypeError, ValueError, KeyError):
        raise RuntimeError("Gemini response was not valid JSON") from None
    if version < 3:
        summary = parsed.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise RuntimeError("Gemini response did not match the required JSON summary format")
        return summary.strip(), []

    claims = parsed.get("claims")
    if not isinstance(claims, list) or not claims:
        raise RuntimeError("Gemini response did not contain source-linked claims")
    rendered, number_errors = [], []
    known_keys = set(facts)
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not isinstance(claim.get("text"), str):
            raise RuntimeError("Gemini returned a malformed claim")
        text = claim["text"].strip()
        keys = claim.get("source_keys")
        if not text or not isinstance(keys, list) or not keys or any(key not in known_keys for key in keys):
            raise RuntimeError("Gemini returned a claim with missing or unknown source keys")
        if re.search(r"\b20\d{2}-\d{2}-\d{2}\b", text):
            number_errors.append({"claim_index": index, "kind": "date_generated_by_model"})
        if re.search(r"на дату снимка", text, flags=re.IGNORECASE) and not any(key.endswith("_at_capture") for key in keys):
            number_errors.append({"claim_index": index, "kind": "snapshot_date_missing_from_source_keys"})
        for key in keys:
            value = facts[key]
            if value is None and "нет данных" not in text.casefold():
                number_errors.append({"claim_index": index, "kind": "null_fact_not_marked_missing", "key": key})
            elif isinstance(value, int):
                equivalent_zero = (value == 0 and key == "recorded_deployments"
                                   and "запис" in text.casefold()
                                   and re.search(r"\b(нет|отсутствуют|отсутствует)\b", text.casefold()))
                if str(value) not in claim_numbers_for(text) and not equivalent_zero:
                    number_errors.append({"claim_index": index, "kind": "known_count_omitted_or_changed", "key": key,
                                          "expected": value})
                if "нет данных" in text.casefold():
                    number_errors.append({"claim_index": index, "kind": "known_fact_reported_as_missing", "key": key})
        if any(key in {"project_in_progress_at_capture", "project_blocked_at_capture"} for key in keys):
            if "задач" not in text.casefold() or re.search(r"\bпроект(ов|а|ы)\b", text.casefold()):
                number_errors.append({"claim_index": index, "kind": "project_task_unit_mislabeled"})
        if "recorded_deployments" in keys and facts["recorded_deployments"] == 0:
            if "запис" not in text.casefold() and not ("api" in text.casefold() and "нет" in text.casefold()):
                number_errors.append({"claim_index": index, "kind": "deployment_record_overstated"})
        allowed_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", json.dumps({key: facts[key] for key in keys}, ensure_ascii=False)))
        claim_numbers = set(claim_numbers_for(text))
        unexpected = sorted(claim_numbers - allowed_numbers)
        if unexpected:
            number_errors.append({"claim_index": index, "kind": "numbers_not_in_cited_facts", "values": unexpected})
        rendered.append(f"{text} [{', '.join(keys)}]")
    return " ".join(rendered), number_errors


def claim_numbers_for(text):
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def _prompt(version):
    prompt = ("Роль: ассистент менеджера проекта. Адресат: команда проекта. "
              "Подготовь краткий черновик статуса на русском языке. Единственный источник фактов — "
              "JSON из сообщения пользователя. "
              "Не добавляй факты, числа, даты, причины, статусы согласования или выводы, которых в нём нет. "
              "При отсутствии сведений напиши «нет данных». Не используй оценочные слова. "
              "До 90 слов. Успешный CI не означает закрытую задачу или развёртывание. "
              "Поля со словом at_capture относятся к дате снимка, а не к отчётному периоду.")
    if version < 3:
        prompt += " Верни ответ только JSON вида {\"summary\":\"...\"}."
    else:
        prompt += (" Верни JSON вида {\"claims\":[{\"text\":\"одна короткая фраза\","
                   "\"source_keys\":[\"ключ JSON facts\"]}]}. Каждый элемент claims — одно "
                   "фактическое утверждение, source_keys содержит ключи, которые его подтверждают.")
    if version >= 2:
        prompt += (" Каждое фактическое предложение заканчивай ссылкой на ключ JSON в квадратных скобках. "
                   "Не считай проценты, длительность или экономию. Не делай выводов об отсутствии ручных "
                   "действий из пустого журнала. Значения null передавай словами «нет данных»; никогда "
                   "не превращай их в ноль. Не называй CI-запуски задачами или развёртываниями. "
                   "Если project_status_capture_date отсутствует, статус задач в работе и заблокированных "
                   "задач неизвестен; если он указан, привяжи эти числа только к дате снимка.")
    if version >= 3:
        prompt += (" Версия промпта 3 после проверки ошибок. Не указывай даты в claims: точный интервал "
                   "уже указан в заголовке отчёта, называй его «за отчётный период». Верни JSON-массив "
                   "claims; каждый элемент — одна короткая фактическая фраза с source_keys из ключей "
                   "JSON facts. Скрипт сам добавит названия ключей к каждой фразе. "
                   "Поля project_in_progress_at_capture и project_blocked_at_capture — количество задач "
                   "в проекте, не проектов; обязательно называй их задачами и указывай дату снимка. "
                   "recorded_deployments — число записей в GitHub Deployments API. При нуле сообщай только, "
                   "что в API нет записей; не утверждай, что развёртываний не было. "
                   "manual_deployments=null означает «ручные развёртывания: нет данных». "
                   "Не объединяй метрики разных ключей в одно утверждение.")
    if version == 4:
        prompt += (" Версия промпта 4 исправляет ошибки ссылок на дату. Не указывай календарные даты, "
                   "даже дату снимка; точные даты уже есть в проверяемой части отчёта. Пиши только «за "
                   "отчётный период» и «на дату снимка». Данные сообщения намеренно не содержат календарных "
                   "дат. Если фраза говорит «на дату снимка», source_keys обязательно должен включать "
                   "соответствующий ключ с суффиксом _at_capture. Для каждой фразы укажи только ключи, "
                   "которые прямо подтверждают её текст; не объединяй разные метрики. В тексте не должно "
                   "быть чисел или дат, кроме значений именно этих source_keys. Скрипт добавит ссылки на ключи.")
    if version >= 5:
        prompt += (" Версия промпта 5 исправляет ошибки, найденные в версии 4. Ноль — измеренное "
                   "числовое значение, сообщай его как 0; только null значит «нет данных». Каждый источник "
                   "с числовым значением обязательно отрази тем же числом в тексте. Для project_*_at_capture "
                   "пиши «задач», никогда «проектов». Для recorded_deployments при нуле явно говори, что "
                   "записей в GitHub Deployments API нет; не делай вывода о фактическом отсутствии ручных "
                   "развёртываний. Для каждого null-источника явно пиши «нет данных». Не опускай поля с "
                   "известным значением 0 или ненулевым значением.")
    if version >= 6:
        prompt += (" Версия промпта 6 исправляет найденные стилистические ошибки. Пиши естественным, "
                   "грамматически правильным русским языком; английские фрагменты запрещены, кроме общих "
                   "названий CI и API. Используй термины: issues_created — «создано задач», issues_closed — "
                   "«закрыто задач», issues_open_at_capture — «открытых задач», "
                   "issues_closed_at_capture — «закрытых задач», project_in_progress_at_capture — "
                   "«задач в работе», project_blocked_at_capture — «заблокированных задач», "
                   "ci_success — «успешных CI-запусков», ci_failure — «неуспешных CI-запусков». "
                   "Пример: {\"claims\":[{\"text\":\"Создано задач за отчётный период: 0.\","
                   "\"source_keys\":[\"issues_created\"]},{\"text\":\"Задач в работе на дату снимка: 1.\","
                   "\"source_keys\":[\"project_in_progress_at_capture\"]}]}. Для нуля recorded_deployments "
                   "пиши «Записей о развёртывании в GitHub API за отчётный период нет.» "
                   "Для всех остальных известных нулей указывай цифру 0.")
    return prompt


def build(snapshot, start, end, output, *, model=None, prompt_versions=(6,)):
    facts = period_facts(snapshot, start, end)
    output.mkdir(parents=True, exist_ok=True)
    journal = []
    summaries = {}
    metadata = {}
    for version in prompt_versions:
        prompt = _prompt(version)
        model_facts = facts
        if version >= 4:
            model_facts = {key: value for key, value in facts.items()
                           if key not in {"period_start", "period_end_exclusive", "project_status_capture_date"}}
        response_schema = _claim_schema(model_facts) if version >= 3 else None
        result = generate([{"role": "system", "content": prompt},
                           {"role": "user", "content": json.dumps(model_facts, ensure_ascii=False)}],
                          model=model, max_tokens=500,
                          response_schema=response_schema)
        (output / f"prompt-v{version}.json").write_text(json.dumps({
            "system_prompt": prompt, "user_facts": model_facts, "response_schema": response_schema,
            "generation": {"model": result["model"], "temperature": 0, "seed": 42,
                           "max_output_tokens": 500, "response_mime_type": "application/json"},
        }, ensure_ascii=False, indent=2) + "\n")
        summary, claim_number_errors = _summary(result, model_facts, version)
        summaries[version] = summary
        metadata[version] = {"model": result["model"], "provider": result["provider"]}
        unexpected = numeric_discrepancies(summary, model_facts)
        (output / f"model-v{version}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        journal.append({"prompt_version": version, "machine_numeric_discrepancies": unexpected,
                        "claim_number_errors": claim_number_errors,
                        "machine_check_passed": not unexpected and not claim_number_errors,
                        "human_review": "pending", "reviewer": None,
                        "semantic_error_rate": None, "generation_seconds": result["seconds"]})
    (output / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n")
    (output / "verification.json").write_text(json.dumps({"claims": journal,
        "provider": "Google Gemini API", "automatic_check_limitation": "Числовая проверка не проверяет смысл, причины, согласования и атрибуцию",
        "manual_baseline_runs": [], "net_savings_minutes": None, "payback_runs": None,
        "status": "draft_requires_human_review"}, ensure_ascii=False, indent=2) + "\n")
    lines = ["# Статус проекта — черновик для проверки", "",
             f"Период: {facts['period_start']} — {facts['period_end_exclusive']} (конец не включён).", "",
             "Факты рассчитаны Python по сохранённому снимку GitHub:", ""]
    for key in ("issues_created", "issues_closed", "ci_success", "ci_failure", "recorded_deployments"):
        lines.append(f"- {key}: {facts[key]}.")
    lines += ["", f"Состояние issues и Project V2 на дату снимка {facts['project_status_capture_date'] or 'нет данных'}:"]
    for key in ("issues_open_at_capture", "issues_closed_at_capture", "project_in_progress_at_capture", "project_blocked_at_capture"):
        value = facts[key] if facts[key] is not None else "нет данных"
        lines.append(f"- {key}: {value}.")
    selected_version = max(summaries)
    for key in ("manual_deployments", "customer_approval", "sprint_goal", "measured_manual_minutes"):
        if facts[key] is None:
            lines.append(f"- {key}: нет данных.")
    lines += ["", "## Черновик формулировки", "", summaries[selected_version], "",
              f"Использование ИИ: Google Gemini API ({metadata[selected_version]['model']}) "
              "сформировал текстовый черновик; числа и факты подготовлены Python. "
              "Факты предварительно сверил Codex по сохранённому снимку GitHub. "
              "PM-проверка и утверждение не выполнены; черновик не опубликован."]
    (output / "status.md").write_text("\n".join(lines) + "\n")
    return facts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--start", type=stamp, required=True)
    parser.add_argument("--end", type=stamp, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--prompt-versions", type=int, nargs="+", choices=(1, 2, 3, 4, 5, 6), default=(6,))
    args = parser.parse_args()
    facts = build(json.loads(args.snapshot.read_text()), args.start, args.end, args.output_directory,
                  prompt_versions=tuple(args.prompt_versions))
    print(json.dumps(facts))


if __name__ == "__main__":
    main()
