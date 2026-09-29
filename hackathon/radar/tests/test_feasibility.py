"""Регрессии фильтра фантастики: удаляем только прямо опровергнутое.

Главный риск этого фильтра — принять признаки настоящего слабого сигнала (ранняя стадия,
прототип, отсутствие продаж) за признаки вымысла. Тогда фильтр выбрасывает именно то, что
мы ищем. Поэтому отрицательные случаи здесь важнее положительных.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from radar.feasibility import decide, packet, stored_decision        # noqa: E402

CUTOFF = "2026-09-27"
FICTION = ("The authors note in the paper itself that the described device is a thought "
           "experiment and no physical prototype exists or is planned.")
NO_SALES = ("The startup has no commercial customers yet and the product remains in a "
            "closed laboratory prototype stage as of September 2026.")
RETRACTION = ("The journal has retracted the original paper; the single demonstration the "
              "claim relied upon could not be reproduced by the authors themselves.")


def _data(quotes: list[str]) -> dict:
    cand = {"name_ru": "предмет", "mechanism": "механизм", "object_affected": "объект",
            "evidence": [{"quote": q, "source_url": "https://src.example.com/a"} for q in quotes]}
    return packet(cand, CUTOFF)


def _audit(fact_id: str, refs: list[str], **over) -> dict:
    check = {"fact_id": fact_id, "evidence_ids": refs, "supported": True, "same_scope": True,
             "entire_candidate_refuted": True, "direct_refutation": True,
             "competent_source": True, "not_merely_early_or_planned": True}
    check.update(over.pop("check", {}))
    base = {"no_conflicting_implementation": True, "reason": "ок", "checks": [check]}
    base.update(over)
    return base


def test_absence_of_sales_is_not_fiction() -> None:
    # Ранняя стадия, прототип и отсутствие покупателей — признаки слабого сигнала.
    data = _data([NO_SALES])
    proposal = {"facts": [{"id": "f1", "kind": "mechanism_impossible",
                           "statement": "нет продаж, значит невозможно",
                           "evidence_ids": ["e1"]}]}
    audit = _audit("f1", ["e1"], check={"not_merely_early_or_planned": False})
    assert decide(data, proposal, audit)["action"] == "keep_for_review"


def test_explicit_fiction_is_excluded() -> None:
    # Обратная сторона: если источник сам называет объект мысленным экспериментом,
    # фильтр обязан сработать, иначе он бесполезен.
    data = _data([FICTION])
    proposal = {"facts": [{"id": "f1", "kind": "explicit_fiction",
                           "statement": "авторы называют устройство мысленным экспериментом",
                           "evidence_ids": ["e1"]}]}
    out = decide(data, proposal, _audit("f1", ["e1"]))
    assert out["action"] == "exclude_refuted" and out["route"] == "explicit_fiction"


def test_retraction_of_single_result_is_excluded() -> None:
    data = _data([RETRACTION])
    proposal = {"facts": [{"id": "f1", "kind": "core_result_refuted",
                           "statement": "статья отозвана, результат не воспроизведён",
                           "evidence_ids": ["e1"]}]}
    assert decide(data, proposal, _audit("f1", ["e1"]))["action"] == "exclude_refuted"


def test_conflicting_implementation_blocks_refutation() -> None:
    # Если в материалах есть состоявшаяся реализация того же механизма, объявлять его
    # невозможным нельзя, каким бы уверенным ни было опровержение.
    data = _data([FICTION, "The same mechanism is running in production at two operators."])
    proposal = {"facts": [{"id": "f1", "kind": "mechanism_impossible",
                           "statement": "механизм невозможен", "evidence_ids": ["e1"]}]}
    audit = _audit("f1", ["e1"], no_conflicting_implementation=False)
    out = decide(data, proposal, audit)
    assert out["action"] == "keep_for_review"
    assert out["reason_codes"] == ["unverified_or_conflicting_refutation"]


def test_string_true_is_not_confirmation() -> None:
    data = _data([FICTION])
    proposal = {"facts": [{"id": "f1", "kind": "explicit_fiction", "statement": "вымысел",
                           "evidence_ids": ["e1"]}]}
    audit = _audit("f1", ["e1"], check={"direct_refutation": "true"})
    assert decide(data, proposal, audit)["action"] == "keep_for_review"


def test_unknown_kind_and_foreign_refs_are_rejected() -> None:
    data = _data([FICTION])
    bad_kind = {"facts": [{"id": "f1", "kind": "слишком_дорого", "statement": "дорого",
                           "evidence_ids": ["e1"]}]}
    assert decide(data, bad_kind, _audit("f1", ["e1"]))["action"] == "keep_for_review"
    foreign = {"facts": [{"id": "f1", "kind": "explicit_fiction", "statement": "вымысел",
                          "evidence_ids": ["e99"]}]}
    assert decide(data, foreign, _audit("f1", ["e99"]))["action"] == "keep_for_review"


def test_stored_refutation_invalidated_by_new_evidence() -> None:
    cand = {"name_ru": "предмет", "mechanism": "механизм", "object_affected": "объект",
            "evidence": [{"quote": FICTION, "source_url": "https://src.example.com/a"}]}
    record = {**packet(cand, CUTOFF), "action": "exclude_refuted"}
    assert stored_decision(cand, record, CUTOFF) is not None
    changed = {**cand, "evidence": cand["evidence"] + [{"quote": RETRACTION,
                                                        "source_url": "https://j.example.com/r"}]}
    assert stored_decision(changed, record, CUTOFF) is None
