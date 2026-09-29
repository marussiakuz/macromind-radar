"""Оценка пула кандидатов: метрика C и воронка потерь.

C — число различных эталонных категорий области, найденных в пуле. Сопоставление
один к одному: две карточки одной категории не дают два зачёта, alias не создаёт
новую категорию. Машина только предлагает пары; засчитывает их человек — это
правило раздела 14, поэтому здесь есть режим подтверждения.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import Candidate
from .reference import DO_NOT_MERGE, ReferenceItem, area_items, normalize_tokens


@dataclass
class MatchSuggestion:
    candidate_index: int
    candidate_name: str
    reference_number: int
    reference_name: str
    score: float
    decision: str = "pending"  # pending | accepted | rejected
    comment: str | None = None  # пометка проверяющего: почему принято или отозвано


@dataclass
class Funnel:
    """Где теряются категории. Пустые ступени показывают, что чинить."""

    queries: int = 0
    hits: int = 0
    unique_urls: int = 0
    fetch_attempts: int = 0
    from_api: int = 0          # документы, пришедшие из API вместе с текстом
    fetched_ok: int = 0
    parsed_ok: int = 0
    # Три разные величины, которые нельзя складывать: сколько модель предложила,
    # сколько принято в пул и сколько отброшено как повтор внутри документа.
    proposed_candidates: int = 0
    duplicate_candidates: int = 0
    extracted_candidates: int = 0
    after_merge: int = 0
    matched_reference: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def name_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Сходство названий: доля пересечения к меньшему из названий.

    Эталон часто длиннее кандидата («… и защита от tool poisoning»), поэтому
    Жаккар занижает верные пары. Требуем не меньше двух общих слов, иначе одно
    частое слово вроде «ИИ» начинает предлагать пары со всей областью.
    """
    if not a or not b:
        return 0.0
    shared = a & b
    if len(shared) < 2:
        return jaccard(a, b)
    return max(jaccard(a, b), len(shared) / min(len(a), len(b)))


def suggest_matches(
    candidates: list[Candidate], reference: list[ReferenceItem], area: str, threshold: float = 0.34
) -> list[MatchSuggestion]:
    """Предлагает пары «кандидат — строка эталона» по пересечению слов названия.

    Это подсказка для человека, а не решение. Порог намеренно низкий: пропустить
    пару хуже, чем показать лишнюю, которую Олег отклонит за секунды.
    """
    items = area_items(reference, area)
    out: list[MatchSuggestion] = []
    for ci, c in enumerate(candidates):
        # Сравниваем только названия: текст механизма длиннее названия и размывает
        # пересечение, из-за чего верная пара уходит ниже порога.
        ctoks = normalize_tokens(f"{c.name_ru} {c.name_orig or ''}")
        scored = sorted(
            ((name_similarity(ctoks, i.tokens), i) for i in items), key=lambda p: p[0], reverse=True
        )
        for score, item in scored[:2]:
            if score >= threshold:
                out.append(
                    MatchSuggestion(
                        candidate_index=ci,
                        candidate_name=c.name_ru,
                        reference_number=item.number,
                        reference_name=item.name,
                        score=round(score, 3),
                    )
                )
    return out


def compute_c(accepted: list[MatchSuggestion]) -> tuple[int, list[int]]:
    """C по принятым человеком парам, один к одному.

    Одна строка эталона засчитывается один раз; один кандидат закрывает одну строку.
    """
    used_ref: set[int] = set()
    used_cand: set[int] = set()
    for m in sorted(accepted, key=lambda m: -m.score):
        if m.decision != "accepted":
            continue
        if m.reference_number in used_ref or m.candidate_index in used_cand:
            continue
        used_ref.add(m.reference_number)
        used_cand.add(m.candidate_index)
    return len(used_ref), sorted(used_ref)


def check_do_not_merge(accepted: list[MatchSuggestion]) -> list[str]:
    """Ловит склейку соседних строк: две строки пары не могут закрываться одним кандидатом."""
    by_candidate: dict[int, set[int]] = {}
    for m in accepted:
        if m.decision == "accepted":
            by_candidate.setdefault(m.candidate_index, set()).add(m.reference_number)
    errors = []
    for ci, refs in by_candidate.items():
        for a, b in DO_NOT_MERGE:
            if {a, b} <= refs:
                errors.append(f"кандидат #{ci} закрывает сразу №{a} и №{b}: это разные категории")
    return errors


def write_review_file(path: Path, suggestions: list[MatchSuggestion], area: str, total_ref: int) -> Path:
    """Файл для ручного подтверждения: решение меняется правкой поля decision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "area": area,
        "reference_total": total_ref,
        "instruction": "decision: accepted | rejected. accepted означает совпадение по смыслу: "
        "тот же механизм и то же применение. Уточняющие слова таблицы не обязательны.",
        "matches": [m.__dict__ for m in suggestions],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_review_file(path: Path) -> list[MatchSuggestion]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [MatchSuggestion(**m) for m in data["matches"]]


def report(area: str, funnel: Funnel, c_value: int, total_ref: int, errors: list[str]) -> str:
    target = 14
    lines = [
        f"Область: {area}",
        f"C = {c_value} из {total_ref} эталонных категорий (цель C ≥ {target})",
        "",
        "Воронка:",
        f"  поисковых запросов        {funnel.queries}",
        f"  позиций выдачи            {funnel.hits}",
        f"  уникальных URL            {funnel.unique_urls}",
        f"  попыток загрузки          {funnel.fetch_attempts}",
        f"  получено документов       {funnel.fetched_ok}"
        + (f" (из них {funnel.from_api} из API без загрузки)" if funnel.from_api else ""),
        f"  разобрано текстов         {funnel.parsed_ok}",
        f"  извлечено кандидатов      {funnel.extracted_candidates}",
        f"  после склейки             {funnel.after_merge}",
        f"  подтверждено совпадений   {funnel.matched_reference}",
    ]
    if funnel.fetch_attempts:
        # Именно разобранный текст, а не успешный HTTP: страница может открыться и не
        # дать текста. Раньше подпись обещала одно, а считала другое.
        share = (funnel.parsed_ok - funnel.from_api) / funnel.fetch_attempts
        lines.append(f"  доля страниц с текстом    {share:.0%} (порог 70 %)")
    if errors:
        lines += ["", "Ошибки:"] + [f"  {e}" for e in errors]
    if funnel.notes:
        lines += ["", "Заметки:"] + [f"  {n}" for n in funnel.notes]
    return "\n".join(lines)
