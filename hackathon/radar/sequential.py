"""Последовательные фильтры пула: сначала доказанно зрелое, затем доказанно опровергнутое.

Порядок задан заказчиком и пользователем: из пула убираем **только** доказанное, всё
неизвестное остаётся. Остаток называется кандидатами, а не подтверждёнными сигналами.

Две корзины исключений раздельны и обратимы: у каждого решения сохраняются основание,
дословные цитаты, версия правила, отпечаток досье и срез. Изменилось досье или правило —
решение пересчитывается, кандидат возвращается в очередь.

Экономика важна не меньше правил. Проверка одного кандидата у Codex стоила около 1,14 ₽ и
трёх вызовов модели; на 135 кандидатов это 150 ₽, а на модель у нас осталось 76 ₽. Поэтому:
  * решения кешируются на диск и переиспользуются, пока действителен отпечаток;
  * есть бесплатный проход `plan_only`, который показывает, сколько будет стоить полный;
  * лимит числа проверяемых кандидатов задаётся явно, а не «сколько получится».
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import feasibility, maturity
from .ledger import LimitReached, llm_cost, shared as shared_ledger
from .usage_evidence import gather as gather_usage

STORE_NAME = "filter-decisions.json"
# Оценка стоимости одной проверки по замеру Codex: три вызова модели на кандидата.
COST_PER_CANDIDATE_RUB = 1.2


@dataclass
class FilterOutcome:
    """Итог последовательных фильтров по пулу."""

    remaining: list[dict] = field(default_factory=list)
    mature: list[dict] = field(default_factory=list)
    refuted: list[dict] = field(default_factory=list)
    unchecked: list[dict] = field(default_factory=list)
    decisions: dict = field(default_factory=dict)
    llm_calls: int = 0
    spent_rub: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict:
        return {"пул": len(self.remaining) + len(self.mature) + len(self.refuted) + len(self.unchecked),
                "исключено как зрелое": len(self.mature),
                "исключено как опровергнутое": len(self.refuted),
                "не проверено": len(self.unchecked),
                "осталось кандидатов": len(self.remaining) + len(self.unchecked),
                "проверено и оставлено": len(self.remaining),
                "вызовов модели": self.llm_calls,
                "расход, ₽": round(self.spent_rub, 2)}


def candidate_key(cand: dict) -> str:
    """Ключ кандидата в хранилище решений: устойчив к порядку в файле."""
    return maturity.fingerprint(cand, maturity.packet(cand, "1970-01-01")["evidence"])[:24]


def load_store(run: Path) -> dict:
    path = run / STORE_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_store(run: Path, store: dict) -> None:
    from .ledger import _atomic_write
    _atomic_write(run / STORE_NAME, store)


def _ask(llm, system: str, payload: dict) -> tuple[dict, int]:
    """Один вызов модели с разбором JSON. Пустой ответ — это отсутствие фактов, не ошибка."""
    text, _, _ = llm.complete(system, payload)
    try:
        return json.loads(text[text.find("{"): text.rfind("}") + 1]), 1
    except (ValueError, KeyError):
        return {}, 1


def screen_maturity(cand: dict, llm, cutoff: str, searcher=None,
                    fetcher=None) -> tuple[dict, int]:
    """Три вопроса: предложить факты, проверить их, проверить границу массовости.

    Если дан `searcher`, сначала собираются факты применения: иначе проверять нечего.
    """
    extra = gather_usage(cand, searcher, fetcher=fetcher) if searcher is not None else []
    data = maturity.packet(cand, cutoff, extra)
    def attach(decision):
        decision['base_input_hash'] = maturity.packet(cand, cutoff)['input_hash']
        decision['packet'] = data
        return decision
    if not data["evidence"]:
        return attach(maturity.decide(data)), 0
    calls = 0
    proposal, n = _ask(llm, maturity.PROPOSE, {"subject": data["subject"],
                                               "cutoff": cutoff,
                                               "evidence": data["evidence"]})
    calls += n
    facts = proposal.get("facts") if isinstance(proposal, dict) else None
    if not facts:
        decision = attach(maturity.decide(data, proposal))
        decision['proposal'] = proposal
        return decision, calls
    audit, n = _ask(llm, maturity.AUDIT, {"subject": data["subject"], "cutoff": cutoff,
                                          "evidence": data["evidence"], "facts": facts})
    calls += n
    mass = None
    if any(isinstance(f, dict) and f.get("kind") == "mass_operational_use" for f in facts):
        mass, n = _ask(llm, maturity.MASS_AUDIT,
                       {"subject": data["subject"], "evidence": data["evidence"],
                        "facts": [f for f in facts
                                  if isinstance(f, dict) and f.get("kind") == "mass_operational_use"]})
        calls += n
    decision = maturity.decide(data, proposal, audit, mass)
    decision["packet"] = data
    decision["proposal"] = proposal
    decision["audit"] = audit
    decision["mass_audit"] = mass
    return attach(decision), calls


def screen_refutation(cand: dict, llm, cutoff: str) -> tuple[dict, int]:
    data = feasibility.packet(cand, cutoff)
    if not data["evidence"]:
        return feasibility.decide(data), 0
    calls = 0
    proposal, n = _ask(llm, feasibility.PROPOSE, {"subject": data["subject"],
                                                  "cutoff": cutoff,
                                                  "evidence": data["evidence"]})
    calls += n
    facts = proposal.get("facts") if isinstance(proposal, dict) else None
    if not facts:
        return feasibility.decide(data, proposal), calls
    audit, n = _ask(llm, feasibility.AUDIT, {"subject": data["subject"], "cutoff": cutoff,
                                             "evidence": data["evidence"], "facts": facts})
    calls += n
    decision = feasibility.decide(data, proposal, audit)
    decision.update(packet=data, proposal=proposal, audit=audit)
    return decision, calls


def run_filters(pool: list[dict], run: Path, cutoff: str, llm=None, limit: int | None = None,
                plan_only: bool = False, searcher=None, fetcher=None) -> FilterOutcome:
    """Пул → зрелость → фантастика → остаток. Без `llm` работает только на сохранённых решениях.

    `plan_only=True` ничего не тратит и отвечает, сколько будет стоить полная проверка.
    """
    out = FilterOutcome()
    store = load_store(run)
    ledger = shared_ledger()
    spent_before = getattr(llm, 'spent_rub', 0.0)
    checked = 0

    for cand in pool:
        key = candidate_key(cand)
        record = store.get(key) or {}
        mature_decision = maturity.stored_decision(cand, record.get("maturity") or {}, cutoff)
        refute_decision = feasibility.stored_decision(cand, record.get("refutation") or {}, cutoff)

        need_llm = mature_decision is None or (
            mature_decision.get("action") != "exclude_mature" and refute_decision is None)
        if need_llm and (plan_only or llm is None or (limit is not None and checked >= limit)):
            out.unchecked.append({**cand, "_filter": "не проверено: нет бюджета или лимит"})
            continue
        if need_llm:
            checked += 1

        if mature_decision is None:
            try:
                mature_decision, calls = screen_maturity(cand, llm, cutoff, searcher, fetcher)
            except LimitReached as exc:
                out.notes.append(f"остановлено по лимиту расходов: {exc}")
                out.unchecked.append({**cand, "_filter": "не проверено: лимит расходов"})
                continue
            out.llm_calls += calls
            store.setdefault(key, {})["maturity"] = mature_decision
            save_store(run, store)

        if mature_decision.get("action") == "exclude_mature":
            out.mature.append({**cand, "_decision": mature_decision})
            continue

        if refute_decision is None:
            try:
                refute_decision, calls = screen_refutation(cand, llm, cutoff)
            except LimitReached as exc:
                out.notes.append(f"остановлено по лимиту расходов: {exc}")
                out.unchecked.append({**cand, "_filter": "не проверено: лимит расходов"})
                continue
            out.llm_calls += calls
            store.setdefault(key, {})["refutation"] = refute_decision
            save_store(run, store)

        if refute_decision.get("action") == "exclude_refuted":
            out.refuted.append({**cand, "_decision": refute_decision})
            continue

        out.remaining.append({**cand, "_maturity": mature_decision.get("reason_codes"),
                              "_refutation": refute_decision.get("reason_codes")})

    out.decisions = store
    out.spent_rub = max(0.0, getattr(llm, 'spent_rub', 0.0) - spent_before)
    if plan_only:
        need = len(out.unchecked)
        out.notes.append(f"полная проверка потребует около {need * COST_PER_CANDIDATE_RUB:.0f} ₽ "
                         f"на {need} кандидатов (по замеру Codex 1,2 ₽ и три вызова на кандидата); "
                         f"остаток корзины модели {ledger.remaining()['llm']:.2f} ₽")
    out.notes.append(f"срез {cutoff}, правила {maturity.VERSION} и {feasibility.VERSION}")
    return out
