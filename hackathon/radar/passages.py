"""Bounded extraction windows selected from the entire document, with exact offsets."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .selection import terms


@dataclass
class Span:
    span_id: str
    heading: str
    text: str
    start: int = 0
    end: int = 0


def all_spans(doc, max_chars=1200):
    if max_chars < 100:
        raise ValueError("span size must be at least 100 characters")
    spans, start = [], 0
    while start < len(doc.text):
        end = min(len(doc.text), start + max_chars)
        if end < len(doc.text):
            floor = start + max_chars // 2
            boundary = doc.text.rfind("\n", floor, end)
            if boundary < floor:
                boundary = doc.text.rfind(" ", floor, end)
            if boundary >= floor:
                end = boundary
        a, b = start, end
        while a < b and doc.text[a].isspace(): a += 1
        while b > a and doc.text[b - 1].isspace(): b -= 1
        if b > a:
            spans.append(Span(f"s{len(spans)+1}", doc.title, doc.text[a:b], a, b))
        if end == len(doc.text):
            break
        # Overlap preserves sentences crossing a window boundary.
        start = max(start + 1, end - min(160, max_chars // 5))
        while start < end and not doc.text[start].isspace(): start += 1
    return spans


def make_spans(doc, max_chars=1200, max_spans=12, *, queries=(), exclude_ids=()):
    spans = [s for s in all_spans(doc, max_chars) if s.span_id not in set(exclude_ids)]
    if max_spans <= 0:
        return []
    if len(spans) <= max_spans:
        return spans
    query_sets = [terms(q) for q in queries if terms(q)] or [terms(doc.title)]
    token_sets = [terms(s.text) for s in spans]
    query_words = set().union(*query_sets)
    weights = {w: 1 + math.log((len(spans)+1)/(1+sum(w in ts for ts in token_sets)))
               for w in query_words}
    scores = [max((sum(weights[w] for w in q & ts) / max(1, sum(weights[w] for w in q))
                   for q in query_sets), default=0) for ts in token_sets]
    # Keep the opening for context, then relevant windows, then the most novel ones.
    chosen = {0}
    relevant_slots = max(1, max_spans * 2 // 3)
    for i in sorted(range(len(spans)), key=lambda i: (-scores[i], i)):
        if len(chosen) >= relevant_slots:
            break
        if scores[i] > 0:
            chosen.add(i)
    # Остаток слотов раздаётся по новизне содержимого, а не по удалённости в тексте.
    # Прежнее правило брало «дальний» участок, и раздел, вводящий отдельную реализацию
    # своими словами, проигрывал соседям: 29.09.2026 так был пропущен s7 документа
    # 704d8f65…, где описан SNN-ускоритель с открытым маршрутом проектирования, а в
    # пакет попал соседний s8 с хвостом предыдущего абзаца. Новизна — доля слов окна,
    # которых ещё нет ни в одном выбранном окне: раздел с новой реализацией называет
    # свои сущности, и они как раз новые.
    while len(chosen) < max_spans and len(chosen) < len(spans):
        covered = set().union(*(token_sets[j] for j in chosen)) if chosen else set()
        def novelty(i: int) -> float:
            ts = token_sets[i]
            return len(ts - covered) / len(ts) if ts else 0.0
        i = max((i for i in range(len(spans)) if i not in chosen),
                key=lambda i: (novelty(i), scores[i], -i))
        chosen.add(i)
    return [spans[i] for i in sorted(chosen)]


def unread_sections(doc, span_ids, max_chars=1200, min_novelty=0.35, limit=12):
    """Непрочитанные окна, которые вводят содержимое, не встречавшееся в прочитанных.

    Нужно для решения о продолжении: ответ модели `has_more_candidates=false` относится
    только к показанному тексту и полноту документа не доказывает. Если в непрочитанной
    части остаётся раздел с заметной долей новых слов, документ дочитывается.
    """
    spans = all_spans(doc, max_chars)
    shown = set(span_ids or ())
    read = [s for s in spans if s.span_id in shown]
    rest = [s for s in spans if s.span_id not in shown]
    if not rest:
        return []
    covered = set().union(*(terms(s.text) for s in read)) if read else set()
    scored = []
    for s in rest:
        ts = terms(s.text)
        if not ts:
            continue
        share = len(ts - covered) / len(ts)
        if share >= min_novelty:
            scored.append((share, s))
    scored.sort(key=lambda pair: -pair[0])
    return [s for _, s in scored[:limit]]
