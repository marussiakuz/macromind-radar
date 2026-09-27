"""Принадлежность направлению запроса.

Проверено 27.09.2026 на открытом запросе «Биотехнологии и генетика»: конвейер выдал три
карточки про платежи ИИ-агентов, все из одной статьи про агентский банкинг. План поиска
при этом был правильный — расхождение FDA и EMA для генной терапии, масштабирование
биокатализаторов, — но среди двенадцати болей планировщик протащил две чужие про
автономных агентов. Дальше окно зрелости честно отобрало самое молодое и тихое, и это
оказалось не по теме.

Причина: у окна три оси — молодость, тишина, доказанность — и нет четвёртой, «об этом ли
вообще спрашивали». Здесь она и добавляется. Отдельным модулем, потому что применяется
дважды: к формулировкам плана до поиска и к кандидатам перед выдачей.
"""
from __future__ import annotations

import json

SYSTEM = """Ты проверяешь, относится ли каждая запись к направлению, о котором спросили.

Относится — значит отраслевой обзор этого направления стал бы о ней писать. Технология,
применимая где угодно, к направлению не относится, даже если слово из направления в ней
встречается. Смежная отрасль — не то же самое, что запрошенная.

Отвечай строго по существу направления, а не по популярности темы.

Верни только JSON: {"rows": [{"index": <номер>, "in_domain": true|false,
"why": "<до шести слов>"}]}."""


def filter_in_domain(texts: list[str], direction: str, llm, batch: int = 14
                     ) -> tuple[dict[int, bool], dict[int, str]]:
    """Для каждой записи — относится ли она к направлению, и коротко почему.

    Неразобранный ответ модели трактуется как «относится»: молча выбросить кандидата
    из-за сбоя разбора хуже, чем пропустить лишнего к человеку.
    """
    verdict: dict[int, bool] = {}
    reason: dict[int, str] = {}
    for start in range(0, len(texts), batch):
        chunk = texts[start:start + batch]
        payload = {"направление": direction,
                   "записи": [{"index": start + j, "текст": t[:220]} for j, t in enumerate(chunk)]}
        try:
            answer, _, _ = llm.complete(SYSTEM, payload)
            data = json.loads(answer[answer.find("{"): answer.rfind("}") + 1])
        except (ValueError, KeyError):
            for j in range(len(chunk)):
                verdict[start + j] = True
                reason[start + j] = "проверка не выполнена"
            continue
        seen = set()
        for row in data.get("rows", []):
            idx = row.get("index")
            if not isinstance(idx, int) or not (start <= idx < start + len(chunk)):
                continue
            verdict[idx] = bool(row.get("in_domain"))
            reason[idx] = str(row.get("why", ""))[:60]
            seen.add(idx)
        for j in range(len(chunk)):
            verdict.setdefault(start + j, True)
            reason.setdefault(start + j, "нет ответа по этой записи")
    return verdict, reason
