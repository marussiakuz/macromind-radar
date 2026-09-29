"""Повторы кандидатов внутри одного документа.

Продолжение чтения документа получает список уже найденных названий, но модель их не
всегда соблюдает: 29.09.2026 в прогоне `20260929-191805-edge` три записи вернулись
вторым пакетом с тем же названием и **перефразированным** механизмом — «адаптация к новым
данным» вместо «последовательное обучение с использованием биологически вдохновленных
механизмов». Прежний ключ `(документ, название, механизм)` считал их разными.

Поэтому механизм из ключа убран: он у одной и той же вещи меняется от пересказа к
пересказу, а название внутри одного документа — нет.

Чего здесь намеренно **нет**: слияния по похожести. Совпадать должно всё название целиком
после нормализации регистра, пробелов и пунктуации. Похожие названия остаются разными
записями — внутри одного обзора «мемристоры на основе MoS2» и «фазовая изменяемая память»
это разные механизмы, и склеивать их по общему родителю нельзя. Смысловая склейка разных
документов живёт отдельно, в `merging.py`, и работает по другим правилам.
"""
from __future__ import annotations

import re

_NOT_WORD = re.compile(r"[^0-9a-zA-Zа-яёА-ЯЁ]+")


def name_key(name: str) -> str:
    """Название в сравнимом виде: регистр, пробелы и пунктуация различием не считаются."""
    return " ".join(_NOT_WORD.sub(" ", (name or "").casefold()).split())


def candidate_key(candidate) -> tuple[str, str]:
    """Один документ плюс название. Механизм не участвует: его модель пересказывает."""
    return (getattr(candidate, "document_sha256", "") or "", name_key(getattr(candidate, "name_ru", "")))


def _evidence_key(item) -> tuple:
    return (getattr(item, "quote", "") or "", getattr(item, "start", None),
            getattr(item, "end", None), getattr(item, "document_sha256", None))


def merge_into(existing, duplicate) -> int:
    """Переносит в оставшуюся запись то, чего в ней нет. Возвращает число новых цитат.

    Цитаты повтора не выбрасываются: продолжение читает другие окна документа, и там
    может стоять цитата, которой в первом пакете не было. Происхождение хранится у самой
    цитаты, поэтому перенос не путает документы.
    """
    seen = {_evidence_key(e) for e in existing.evidence}
    added = 0
    for item in duplicate.evidence:
        if _evidence_key(item) not in seen:
            existing.evidence.append(item)
            seen.add(_evidence_key(item))
            added += 1
    # Более подробная формулировка механизма полезнее короткой, если это её же пересказ.
    if len(duplicate.mechanism or "") > len(existing.mechanism or ""):
        short = name_key(existing.mechanism)
        if short and short in name_key(duplicate.mechanism):
            existing.mechanism = duplicate.mechanism
    for org in duplicate.organizations:
        if org not in existing.organizations:
            existing.organizations.append(org)
    if not existing.event_date and duplicate.event_date:
        existing.event_date = duplicate.event_date
    return added


def accept(candidates: list, index: dict, proposals) -> dict:
    """Добавляет новые предложения к пулу, повторы схлопывает.

    `index` — словарь ключ → кандидат, живёт между пакетами одного прогона.
    Возвращает счётчики: сколько предложено, принято, схлопнуто и сколько цитат
    добавлено от повторов. Метрики обязаны различать сырые предложения и принятые
    записи, иначе рост числа строк выглядит как рост полноты.
    """
    stats = {"proposed": 0, "accepted": 0, "duplicates": 0, "evidence_from_duplicates": 0}
    for candidate in proposals:
        stats["proposed"] += 1
        key = candidate_key(candidate)
        existing = index.get(key)
        if existing is None:
            candidates.append(candidate)
            index[key] = candidate
            stats["accepted"] += 1
            continue
        stats["duplicates"] += 1
        stats["evidence_from_duplicates"] += merge_into(existing, candidate)
    return stats
