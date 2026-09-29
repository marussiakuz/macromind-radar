"""Проверки доказательств зрелости: даты, масштаб и соответствие цитат."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from radar.maturity import decide, packet, stored_decision          # noqa: E402

CUTOFF = "2026-09-27"
SENTRY_QUOTE = ("I removed the Edge function from my personal site and measured a 40 ms "
                "improvement in time to first byte on the landing page.")
CLOUDFLARE_QUOTE = ("Our TechnologyChecker detected 18,506 domains with signs of Cloudflare "
                    "Workers integration across the crawl sample.")
NETLIFY_NUMBERS = ("Netlify Edge Functions now serve 255m requests per day with 22k "
                   "deployments per day across the platform.")
NETLIFY_BREADTH = ("Deno subhosting powers hundreds of customers and billions of requests "
                   "per month for Netlify Edge Functions.")
OPERATOR_QUOTE = ("Our usage report covers 240 customer organizations running the service in "
                  "production every day during 2026 with measured request volumes.")


def _data(quotes: list[tuple[str, str]]) -> dict:
    cand = {"name_ru": "предмет", "mechanism": "механизм", "object_affected": "объект",
            "evidence": [{"quote": q, "source_url": u} for q, u in quotes]}
    return packet(cand, CUTOFF)


def _audit(fact_id: str, refs: list[str], scope_refs: list[str], **over) -> dict:
    checks = {"fact_id": fact_id, "supported": True, "same_scope": True, "operational": True,
              "scale_supported": True, "dates_supported": True, "entities_supported": True,
              "source_role_supported": True, "evidence_ids": refs, "reason": "ок"}
    checks.update(over.pop("check", {}))
    base = {"no_unresolved_delta": True, "no_conflict": True, "scope_evidence_ids": scope_refs,
            "reason": "ок", "independent_suppliers": True, "independent_buyers": True,
            "independent_events": True, "checks": [checks]}
    base.update(over)
    return base


def _mass(fact_id: str, refs: list[str], breadth: str, **over) -> dict:
    row = {"fact_id": fact_id, "same_scope": True, "actual_routine_use": True,
           "broad_multi_customer_use": True, "source_kind": "operator_usage_report",
           "adoption_unit": "customer_organizations", "minimum_count": 240,
           "breadth_quote": breadth, "evidence_ids": refs, "reason": "ок"}
    row.update(over)
    return {"checks": [row]}


def test_single_site_removal_is_not_mass_adoption() -> None:
    # Sentry, группа 4d4d6fd6543026d42a29: один автор убрал функцию с личного сайта и
    # измерил улучшение TTFB. Модель назвала это массовым применением категории, и второй
    # вызов согласился. Источник настоящий, вывод о массовости из него не следует.
    data = _data([(SENTRY_QUOTE, "https://blog.example.com/edge")])
    proposal = {"facts": [{"id": "f1", "kind": "mass_operational_use",
                           "statement": "убрал функцию и измерил ускорение",
                           "evidence_ids": ["e1"], "supplier": "", "buyer": "",
                           "source_role": "operator", "event_date": "2026-05-01",
                           "in_use_since": None}]}
    mass = _mass("f1", ["e1"], SENTRY_QUOTE[:60], source_kind="single_case",
                 adoption_unit="sites", minimum_count=1, broad_multi_customer_use=False)
    out = decide(data, proposal, _audit("f1", ["e1"], ["e1"]), mass)
    assert out["action"] == "keep_for_review"
    assert out["reason_codes"] == ["maturity_route_not_proven"]


def test_domain_detector_is_not_an_industry_body() -> None:
    # Cloudflare Workers, группа 0eb7258b8b3cc67c6756: коммерческий сканер назван
    # `industry_body`, а 18 506 доменов приравнены к организациям, которые регулярно
    # эксплуатируют механизм. Сам источник описывает неполноту обнаружения.
    data = _data([(CLOUDFLARE_QUOTE, "https://scanner.example.com/report")])
    proposal = {"facts": [{"id": "f1", "kind": "mass_operational_use",
                           "statement": "детектор нашёл 18 506 доменов",
                           "evidence_ids": ["e1"], "supplier": "", "buyer": "",
                           "source_role": "industry_body", "event_date": "2026-03-01",
                           "in_use_since": None}]}
    mass = _mass("f1", ["e1"], CLOUDFLARE_QUOTE[:60], source_kind="web_detector",
                 adoption_unit="domains", minimum_count=18506)
    out = decide(data, proposal, _audit("f1", ["e1"], ["e1"]), mass)
    assert out["action"] == "keep_for_review", "счётчик доменов не доказывает массовость"


def test_breadth_quote_must_live_in_the_referenced_span() -> None:
    # Netlify, группа 609d97baf72208b84ce1: «сотни клиентов» лежат во втором окне
    # (161ed707…, 2611:3621), а сослались на первое (960ec13b…, 0:1836), где только
    # 255m requests/day и 22k deployments/day. Ошибка — связь факта со спаном.
    data = _data([(NETLIFY_NUMBERS, "https://deno.com/blog/netlify-subhosting"),
                  (NETLIFY_BREADTH, "https://deno.com/blog/netlify-subhosting")])
    proposal = {"facts": [{"id": "f1", "kind": "mass_operational_use",
                           "statement": "сотни клиентов и миллиарды запросов",
                           "evidence_ids": ["e1"], "supplier": "", "buyer": "",
                           "source_role": "operator", "event_date": "2026-04",
                           "in_use_since": None}]}
    wrong = _mass("f1", ["e1"], "hundreds of customers and billions of requests")
    assert decide(data, proposal, _audit("f1", ["e1"], ["e1"]), wrong)["action"] == "keep_for_review"
    # Та же проверка при правильной привязке обязана пропустить исключение, иначе правило
    # не отличает ошибку связи от отсутствия доказательства.
    fixed_proposal = {"facts": [{**proposal["facts"][0], "evidence_ids": ["e1", "e2"]}]}
    right = _mass("f1", ["e2"], "hundreds of customers and billions of requests")
    out = decide(data, fixed_proposal, _audit("f1", ["e1", "e2"], ["e2"]), right)
    assert out["action"] == "exclude_mature" and out["route"] == "documented_multi_customer_use"


def test_string_true_and_string_count_are_not_confirmation() -> None:
    # Модель возвращает `"true"` строкой и `"2"` вместо числа. Такое подтверждение
    # принимать нельзя: иначе любое текстовое поле становится доказательством.
    data = _data([(OPERATOR_QUOTE, "https://operator.example.com/usage")])
    proposal = {"facts": [{"id": "f1", "kind": "mass_operational_use",
                           "statement": "240 организаций в продакшене",
                           "evidence_ids": ["e1"], "supplier": "", "buyer": "",
                           "source_role": "operator", "event_date": "2026-06",
                           "in_use_since": None}]}
    audit = _audit("f1", ["e1"], ["e1"], check={"same_scope": "true"})
    assert decide(data, proposal, audit, _mass("f1", ["e1"], OPERATOR_QUOTE[:60]))["action"] == "keep_for_review"
    ok_audit = _audit("f1", ["e1"], ["e1"])
    string_count = _mass("f1", ["e1"], OPERATOR_QUOTE[:60], minimum_count="240")
    assert decide(data, proposal, ok_audit, string_count)["action"] == "keep_for_review"
    bool_count = _mass("f1", ["e1"], OPERATOR_QUOTE[:60], minimum_count=True)
    assert decide(data, proposal, ok_audit, bool_count)["action"] == "keep_for_review"


def test_missing_mass_audit_keeps_candidate() -> None:
    # Проверяется, что без аудита массовости решение
    # обязано оставаться консервативным, а не повторять старый маршрут исключения.
    data = _data([(OPERATOR_QUOTE, "https://operator.example.com/usage")])
    proposal = {"facts": [{"id": "f1", "kind": "mass_operational_use",
                           "statement": "240 организаций", "evidence_ids": ["e1"],
                           "supplier": "", "buyer": "", "source_role": "operator",
                           "event_date": "2026-06", "in_use_since": None}]}
    out = decide(data, proposal, _audit("f1", ["e1"], ["e1"]), None)
    assert out["action"] == "keep_for_review"


def test_entity_must_be_named_in_the_quote() -> None:
    # Имя покупателя нельзя вывести из адреса или заголовка.
    data = _data([(OPERATOR_QUOTE, "https://operator.example.com/usage")])
    proposal = {"facts": [{"id": "f1", "kind": "routine_deployment",
                           "statement": "внедрение у покупателя", "evidence_ids": ["e1"],
                           "supplier": "Operator", "buyer": "Неназванный Банк",
                           "source_role": "operator", "event_date": "2026-06",
                           "in_use_since": "2024-01"}]}
    out = decide(data, proposal, _audit("f1", ["e1"], ["e1"]))
    assert out["action"] == "keep_for_review"
    assert any("не названа в цитате" in r["reason"] for r in out["rejected_facts"])


def test_event_date_after_cutoff_is_rejected() -> None:
    data = _data([(OPERATOR_QUOTE, "https://operator.example.com/usage")])
    proposal = {"facts": [{"id": "f1", "kind": "mass_operational_use",
                           "statement": "будущее событие", "evidence_ids": ["e1"],
                           "supplier": "", "buyer": "", "source_role": "operator",
                           "event_date": "2026-12-01", "in_use_since": None}]}
    out = decide(data, proposal, _audit("f1", ["e1"], ["e1"]),
                 _mass("f1", ["e1"], OPERATOR_QUOTE[:60]))
    assert out["action"] == "keep_for_review"


def test_stored_decision_invalidated_by_changed_dossier() -> None:
    # Изменилось досье — прежнее решение недействительно, кандидат возвращается в очередь.
    cand = {"name_ru": "предмет", "mechanism": "механизм", "object_affected": "объект",
            "evidence": [{"quote": OPERATOR_QUOTE, "source_url": "https://o.example.com/u"}]}
    record = {**packet(cand, CUTOFF), "action": "exclude_mature"}
    assert stored_decision(cand, record, CUTOFF) is not None
    changed = {**cand, "evidence": cand["evidence"] + [{"quote": NETLIFY_BREADTH,
                                                        "source_url": "https://d.example.com/n"}]}
    assert stored_decision(changed, record, CUTOFF) is None
    assert stored_decision(cand, {**record, "version": "proven-maturity/2"}, CUTOFF) is None


def test_filters_see_the_whole_pool_not_one_tier() -> None:
    # Замер 29.09.2026 на живом прогоне Edge: фильтрам передавался только уровень
    # «уверенных», и они видели одного кандидата из ста тридцати пяти — отчёт о фильтрах
    # выглядел пустым, хотя пул был большой. Проверяем на самом вызове конвейера.
    from radar.server import proof_candidates
    confident = {'_assessment': {'domain': 'yes', 'stage': 'early'}}
    review = {'_assessment': {'domain': 'yes', 'stage': 'mature_hint'}}
    outside = {'_assessment': {'domain': 'no', 'stage': 'unknown'}}
    result = proof_candidates([('signal', confident), ('review', review), ('review', outside)])
    assert result[0] is review
    assert {id(c) for c in result} == {id(confident), id(review), id(outside)}
