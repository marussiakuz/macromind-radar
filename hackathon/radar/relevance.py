"""Проверка связи кандидата с направлением пользовательского запроса."""
from __future__ import annotations

import json
import re

# Слова нашей постановки задачи. Измерено 28.09.2026: на запросе «слабые сигналы в
# финансовых технологиях» проверка пометила «вне области» 81 кандидата из 96, и в
# причинах стояло «платежи, не слабые сигналы», «расчеты стейблкоинами, не слабые
# сигналы». Модель приняла «слабые сигналы» за ТЕМУ, которой обязан соответствовать
# кандидат, и отбраковала финтех за то, что он про финтех. Направление надо спрашивать
# без слов задачи.
_TASK_WORDS = re.compile(
    r"\b(слабы[ехй]+\s+сигнал\w*|сигнал\w*\s+слабы\w*|зарождающ\w+|нарождающ\w+|"
    r"формирующ\w+|восходящ\w+|перспективн\w+|ранн\w+\s+стади\w*|тренд\w*|"
    r"технологическ\w+\s+тренд\w*|радар\w*|weak\s+signals?|emerging|early\s+stage)\b",
    re.IGNORECASE)


def direction_of(query: str) -> str:
    """Предметное направление без слов нашей задачи: «слабые сигналы в X» → «X».

    Если после чистки ничего не осталось, возвращаем исходный запрос: пустое направление
    заставило бы модель угадывать, а это хуже лишнего слова.
    """
    cleaned = _TASK_WORDS.sub(" ", query or "")
    cleaned = re.sub(r"^[\s,.:;—-]*(в|во|по|о|об|про|для|на|in|on|for|about|of)\s+",
                     " ", cleaned.strip(), flags=re.I)
    cleaned = " ".join(cleaned.split()).strip(" ,.:;—-")
    return cleaned if len(cleaned) >= 3 else (query or "").strip()

SYSTEM = """Ты проверяешь, относится ли каждая запись к направлению, о котором спросили.

Относится — значит отраслевой обзор этого направления стал бы о ней писать. Технология,
применимая где угодно, к направлению не относится, даже если слово из направления в ней
встречается. Смежная отрасль — не то же самое, что запрошенная.

Отвечай строго по существу направления, а не по популярности темы.

Здесь проверяется только предметная принадлежность. Зрелость, новизна и раннее ли это
явление проверяются отдельно и тебя не касаются: «промышленный стандарт» и «давно
продаётся» — это не повод ответить false.

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
