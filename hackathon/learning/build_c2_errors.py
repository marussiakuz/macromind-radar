"""Часть C2 доказательного датасета: настоящие проблемные карточки живого конвейера.

Зачем именно мы. В задании (`data/dataset-300-brief/01-prompt-agent.md`, §4) C2 — сорок
реальных ошибок конвейера, и там же сказано, что пакет из 30 карточек их не обеспечивает.
Материал есть только у нас: 1258 строк кандидатов в тринадцати живых прогонах и отказы с
дословными причинами, которые видел фильтр. Синтетикой это не заменяется.

Дисциплина, прямо из задания:
  * исходная формулировка сохраняется дословно, «неудачную формулировку не переписываем»;
  * предложение исправления — отдельным полем, в модельный вход не попадает;
  * недостаточность данных — самостоятельный исход, не ложность и не зрелость;
  * «не заставляй все 40 быть отрицательными»: часть отказов конвейера необоснованна, и
    такие случаи здесь отмечены отдельным типом — ошибка измерения, а не дефект карточки;
  * человеческих меток здесь нет. Всё в `annotations` — `ai_draft`, `human_review_required`.

Тип ошибки предлагается по обнаружимому признаку, и рядом записано, чем предложение
обосновано. Окончательное решение принимают Марина и Олег.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

HACK = Path(__file__).resolve().parents[1]
CUTOFF = "2026-09-27"          # срез задания; у нашего пакета разметки он 28.09
SCHEMA = "radar-evidence-dataset/1.0"

AREA_BY_SLUG = {"финтех": "Финтех", "защита": "Защита ИИ",
                "биотехнологии": "Биотехнологии и генетика (открытый запрос, вне таблицы)",
                "гипотезы-финтех": "Финтех"}

# Признаки типов ошибок из §4 C2. Каждый — обнаружимый в тексте, а не догадка.
# «Общий совет вместо технологии» из §4 C2. Слова взяты по факту: на 1258 кандидатах этот
# набор находит 61 случай, среди них «Методологии тестирования на устойчивость ИИ»,
# «практика красного тестирования систем ИИ», «Фракционное руководство для операционной
# ликвидности». Это признак для предложения типа, а не приговор: «управление
# комплаенс-требованиями GDPR» вполне может быть категорией RegTech, и решает человек.
ADVICE = re.compile(r"(следует|необходимо|рекомендац|лучшие практики|best practice|how to|"
                    r"как выбрать|чек-?лист|практик[аи]|методолог|руководств|принцип[ыа]|"
                    r"дорожная карта|обучение персонала|культур[аы])", re.IGNORECASE)
PROMISE = re.compile(r"\b(will |plans? to|planned|expected|ожидается|планирует|намерен|"
                     r"в будущем|anticipat|roadmap|upcoming|is set to)\b", re.IGNORECASE)
REVIEW = re.compile(r"\b(top \d+|best \d+|обзор|подборка|сравнение|guide|list of|"
                    r"vendors? to watch|leaders? in)\b", re.IGNORECASE)
ATTACK = re.compile(r"\b(инъекц|атака|атак[аи]|эксплойт|взлом|jailbreak|poison|adversarial|"
                    r"exfiltrat|bypass)\b", re.IGNORECASE)
DEFENCE = re.compile(r"\b(защит|обнаружен|контрол|фильтрац|монитор|аудит|guardrail|"
                     r"митигац|предотвращ|санитиз)\b", re.IGNORECASE)


def host_of(url: str) -> str:
    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_runs() -> list[dict]:
    """Кандидаты всех живых прогонов с текстами документов и машинными причинами отказа."""
    rows: list[dict] = []
    for run in sorted((HACK / "radar-runs").glob("2026*")):
        manifest = run / "manifest.json"
        cands = run / "candidates.jsonl"
        if not manifest.exists() or not cands.exists():
            continue
        man = json.loads(manifest.read_text(encoding="utf-8"))
        if man.get("mode") != "live":
            continue
        docs: dict[str, dict] = {}
        if (run / "documents.jsonl").exists():
            for line in (run / "documents.jsonl").read_text(encoding="utf-8").splitlines():
                d = json.loads(line)
                docs[d.get("final_url") or d.get("url", "")] = d
                docs.setdefault(d.get("url", ""), d)
        causes: dict[str, dict] = {}
        if (run / "cards.json").exists():
            saved = json.loads((run / "cards.json").read_text(encoding="utf-8"))
            for item in saved.get("rejected", []):
                causes[item["name"].strip().lower()] = item
        slug = run.name.split("-", 2)[-1]
        for line in cands.read_text(encoding="utf-8").splitlines():
            cand = json.loads(line)
            rows.append({"cand": cand, "docs": docs, "run": run.name,
                         "area": AREA_BY_SLUG.get(slug, slug),
                         "query": man.get("query", ""),
                         "cause": causes.get(cand["name_ru"].strip().lower())})
    return rows


def first_quote(cand: dict) -> dict | None:
    for ev in cand.get("evidence") or []:
        if (ev.get("quote") or "").strip():
            return ev
    return None


def classify(row: dict) -> tuple[str, str] | None:
    """Предлагаемый тип ошибки и обоснование предложения. None — случай не берём."""
    cand, cause = row["cand"], row["cause"]
    name, mech = cand.get("name_ru", ""), cand.get("mechanism", "") or ""
    ev = first_quote(cand)
    quote = (ev.get("quote") or "") if ev else ""
    url = (ev.get("source_url") if ev else None) or cand.get("source_url", "")
    reason = (cause or {}).get("reason", "")
    notes = " ".join((cause or {}).get("notes", []))

    # Отказ по измерению, а не по карточке: кандидат мог быть годным.
    if reason.startswith("упоминаний не найдено") or "нет канонического термина" in reason:
        return ("measurement_failure_not_card_defect",
                f"фильтр отказал по причине «{reason}»: это состояние замера, "
                f"а не установленный дефект карточки")
    # Название шире источника: замер нашёл общий термин с большим числом упоминаний.
    if "громко" in reason or "термин слишком общий" in notes:
        return ("name_broader_than_source",
                f"машинная причина отказа: «{reason}»; число упоминаний указывает на "
                f"термин уровня области, а не этого кандидата")
    if reason.startswith("отбраковано: термину"):
        return ("wrong_date_or_scale",
                f"машинная причина отказа: «{reason}» — возраст термина не соответствует "
                f"заявленной новизне механизма")
    if "принадлежности области" in notes:
        return ("application_from_other_area",
                f"проверка области отметила расхождение: «{notes[:120]}»")
    hit = ADVICE.search(name)
    if hit:
        return ("general_advice_not_technology",
                f"в названии слово «{hit.group(0)}»: описан подход или рамка, "
                f"а не способ действия")
    if len(mech.strip()) < 60 or mech.strip().lower() in name.strip().lower():
        return ("broad_topic_no_mechanism",
                f"механизм длиной {len(mech.strip())} знаков не описывает способ действия")
    if row["area"] == "Защита ИИ" and ATTACK.search(name) and not DEFENCE.search(name):
        return ("attack_instead_of_defense",
                "в названии описан способ атаки, а запрос был о защите")
    if PROMISE.search(quote):
        return ("promise_not_event",
                "цитата говорит о планах или ожиданиях, а не о состоявшемся событии")
    if REVIEW.search((row["docs"].get(url) or {}).get("title", "") or "") or REVIEW.search(quote):
        return ("review_not_new_result",
                "источник — обзор или подборка, а не сообщение о новом результате")
    return None


def build_record(row: dict, kind: str, why: str, seq: int) -> dict | None:
    cand = row["cand"]
    ev = first_quote(cand)
    if ev is None:
        return None
    url = ev.get("source_url") or cand.get("source_url", "")
    doc = row["docs"].get(url) or row["docs"].get(cand.get("source_url", "")) or {}
    quote = (ev.get("quote") or "").strip()
    text = doc.get("text") or ""
    start = text.find(quote) if text and quote else -1
    if start < 0:
        return None                      # цитата не найдена в снимке — запись не выпускаем
    pub = (doc.get("published_at") or "")[:10]
    if pub:
        try:
            if date.fromisoformat(pub) > date.fromisoformat(CUTOFF):
                return None              # источник позже среза не обосновывает решение
        except ValueError:
            pub = ""
    sid = digest([row["run"], cand.get("name_ru"), url, "C2/1"])[:24]
    mech = (cand.get("mechanism") or "").strip()
    application = (cand.get("object_affected") or cand.get("context") or "").strip()
    # Нейтральный текст: только то, что сказано в источнике и в извлечении. Без оценок
    # зрелости и без предложения класса — §10 запрещает подсказки в model_input.
    neutral = (f"{cand.get('name_ru','').strip()}. Механизм по извлечению: {mech} "
               f"Объект применения: {application or 'в извлечении не указан'}. "
               f"Источник: {host_of(url)}"
               + (f", дата публикации {pub}." if pub else ", дата публикации не установлена."))
    return {
        "schema_version": SCHEMA,
        "sample_id": sid,
        "cutoff": CUTOFF,
        "model_input": {
            "area": row["area"],
            "category_ru": cand.get("name_ru", ""),
            "category_en": cand.get("name_orig"),
            "mechanism": mech,
            "application": application or None,
            "geography": "global",
            "neutral_summary": neutral,
            "claims": [{"claim_id": "CLAIM_1",
                        "text": f"{cand.get('name_ru','')}: {mech}",
                        "evidence_ids": ["EVIDENCE_1"]}],
            "evidence": [{"evidence_id": "EVIDENCE_1", "source_id": "SOURCE_1",
                          "excerpt": quote,
                          "context": (text[max(0, start - 180):start + len(quote) + 180]
                                      if text else None)}],
        },
        "observations": {
            # Машинные наблюдения живого сервиса. Исправленных здесь нет: агент карточку
            # не правил, иначе потенциал признаков смешался бы с работой пайплайна (§10).
            "automatic_observations": [
                {"observation_id": "AOBS_1", "field": "pipeline_verdict",
                 "value": (row["cause"] or {}).get("reason") or "выдан в карточки",
                 "unit": None, "object_scope": "candidate",
                 "measurement_status": "available", "evidence_ids": [],
                 "collector": "radar_service",
                 "note": "; ".join((row["cause"] or {}).get("notes", [])) or None},
                {"observation_id": "AOBS_2", "field": "extractor_stage_label",
                 "value": cand.get("stage") or "unknown", "unit": None,
                 "object_scope": "described_implementation",
                 "measurement_status": "available", "evidence_ids": [],
                 "collector": "radar_extractor",
                 "note": "самоотчёт извлекателя по тексту, не проверенный факт"},
            ],
            "reviewed_observations": [],
            "events": [],
            "organizations": [{"name": str(o), "role": "mentioned_in_source",
                               "evidence_ids": ["EVIDENCE_1"]}
                              for o in (cand.get("organizations") or [])][:6],
            "funding_rounds": [],
            "scientific_activity": {"coverage_status": "unavailable", "provider": None,
                                    "previous_count": None, "current_count": None,
                                    "query_log_ids": []},
            "public_events_activity": {"coverage_status": "unavailable",
                                       "previous_count": None, "current_count": None,
                                       "query_log_ids": []},
        },
        "sources": [{
            "source_id": "SOURCE_1", "url": url,
            "title": (doc.get("title") or host_of(url))[:200],
            "publisher": host_of(url), "authors": [],
            "source_type": "web_document",
            "publication_date": pub or None,
            "event_date": (cand.get("event_date") or None),
            "accessed_at": (doc.get("retrieved_at") or "")[:10] or None,
            "access": "full_text" if text else "search_excerpt",
            "doi": None, "arxiv_work_id": None, "version": None,
            "object_level": None, "event_group_id": None, "publication_status": None,
            "snapshot_path": f"radar-runs/{row['run']}/documents.jsonl",
            "snapshot_sha256": doc.get("text_sha256"),
            "quotes": [{"text": quote, "start_offset": start,
                        "end_offset": start + len(quote),
                        "locator": "offset in saved document text"}],
            "limitations": ([] if pub else ["дата публикации документа не установлена"])
                           + ([] if text else ["полный снимок недоступен"]),
        }],
        "annotations": {
            "status": "ai_draft", "label_source": "ai_review",
            "reviewer_model": "claude-opus-5", "human_review_required": True,
            "reviewed_at": None,
            "relevance": "uncertain", "unit_type": "uncertain",
            "card_status": "needs_review",
            "claim_checks": [{"claim_id": "CLAIM_1", "support_label": "not_checkable",
                              "evidence_ids": ["EVIDENCE_1"],
                              "explanation": "цитата дословно найдена в снимке; истинность "
                                             "утверждения о рынке не проверялась"}],
            "stage_label": "unknown", "stage_evidence_ids": [], "stage_rationale": None,
            "counterevidence_ids": [],
            # Предлагаемый тип дефекта — это гипотеза о карточке, а не метка зрелости.
            "reason_codes": [kind],
            "proposed_error_type": kind,
            "proposed_error_basis": why,
            "hype_phase_hypothesis": {"phase": "unknown", "rationale": None,
                                      "evidence_ids": []},
            "ready_for_product_card": False,
            "independent_event_groups": [],
            "missing_data": ["публикационная дата" if not pub else None,
                             "объект применения" if not application else None],
            "contradictions": [],
            "proposed_correction": None,
            "human_confirmation": None,
        },
        "provenance": {
            "cohort": "C2",
            "customer_row_number": None, "customer_original_name": None,
            "original_run_id": row["run"],
            "original_candidate_id": digest([cand.get("name_ru"), url])[:16],
            "original_file_sha256": None,
            "pair_id": None,
            "technology_family_id": "fam-" + digest([cand.get("name_ru"), mech])[:8],
            "split_group_id": None,
            "grouping_reasons": ["same source url", "same extracted mechanism"],
            "synthetic": False, "parent_id": None, "synthetic_operation": None,
            # Дословная исходная формулировка: её нельзя переписывать (§4 C2).
            "original_claim": f"{cand.get('name_ru','')} | {mech}",
            "modified_claim": None, "mutation_evidence_ids": [],
            "previously_used": True,
            "usage_history": ["development: ранжирование, калибровка порогов, "
                              "разбор отказов на этих же прогонах"],
            "split_assignment": {"stage_task": None, "card_validity_task": None,
                                 "diagnostic_suite": "C2_pipeline_errors"},
            "record_hash": None,
            "sequence": seq,
            "origin_query": row["query"],
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path,
                    default=HACK / "learning/c2-pipeline-errors-20260928")
    ap.add_argument("--target", type=int, default=44,
                    help="сколько записей собрать; в задании C2 = 40")
    ap.add_argument("--per-type", type=int, default=8, help="потолок на один тип ошибки")
    args = ap.parse_args(argv)

    rows = load_runs()
    print(f"строк кандидатов в живых прогонах: {len(rows)}")
    by_kind: dict[str, list[tuple[dict, str, str]]] = collections.defaultdict(list)
    for row in rows:
        verdict = classify(row)
        if verdict:
            by_kind[verdict[0]].append((row, verdict[0], verdict[1]))
    for kind in by_kind:
        by_kind[kind].sort(key=lambda t: digest([t[0]["run"], t[0]["cand"].get("name_ru")]))
    print("обнаружено случаев по типам:")
    for kind, items in sorted(by_kind.items(), key=lambda kv: -len(kv[1])):
        print(f"   {len(items):4d}  {kind}")

    # Круговой отбор по типам: набор должен покрывать разные ошибки, а не один частый тип.
    records, seen, seq = [], set(), 0
    kinds = sorted(by_kind, key=lambda k: (-len(by_kind[k]), k))
    taken = collections.Counter()
    while len(records) < args.target and any(by_kind[k] for k in kinds):
        progress = False
        for kind in kinds:
            if len(records) >= args.target or not by_kind[kind] or taken[kind] >= args.per_type:
                continue
            row, k, why = by_kind[kind].pop(0)
            key = (row["cand"].get("name_ru", "").strip().lower(),
                   row["cand"].get("source_url", ""))
            if key in seen:
                continue
            rec = build_record(row, k, why, seq)
            if rec is None:
                continue
            seen.add(key)
            records.append(rec)
            taken[kind] += 1
            seq += 1
            progress = True
        if not progress:
            break
    for rec in records:
        rec["provenance"]["record_hash"] = digest(rec)

    dest = args.output
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "dataset.json").write_text(json.dumps(records, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    (dest / "dataset.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    (dest / "model-inputs.json").write_text(json.dumps(
        [{"sample_id": r["sample_id"], "cutoff": r["cutoff"], **r["model_input"]}
         for r in records], ensure_ascii=False, indent=1), encoding="utf-8")
    (dest / "annotations-ai.json").write_text(json.dumps(
        [{"sample_id": r["sample_id"], **r["annotations"]} for r in records],
        ensure_ascii=False, indent=1), encoding="utf-8")
    (dest / "provenance.json").write_text(json.dumps(
        [{"sample_id": r["sample_id"], **r["provenance"]} for r in records],
        ensure_ascii=False, indent=1), encoding="utf-8")
    (dest / "sources.json").write_text(json.dumps(
        [{"sample_id": r["sample_id"], **s} for r in records for s in r["sources"]],
        ensure_ascii=False, indent=1), encoding="utf-8")

    # Читаемый экспорт: задание просит его для агентов и интерфейсов, не принимающих JSONL.
    lines = ["# Набор C2: читаемый экспорт", "",
             f"Записей {len(records)}, срез {CUTOFF}. Метки не назначены; тип дефекта — гипотеза.", ""]
    for i, r in enumerate(records, 1):
        mi, src, ann = r["model_input"], r["sources"][0], r["annotations"]
        lines += [f"## {i}. {mi['category_ru']}", "",
                  f"- **ID**: `{r['sample_id']}`  ·  область: {mi['area']}",
                  f"- **Механизм**: {mi['mechanism'] or '—'}",
                  f"- **Применение**: {mi['application'] or 'в извлечении не указано'}",
                  f"- **Источник**: [{src['title']}]({src['url']})  ·  дата публикации: "
                  f"{src['publication_date'] or 'не установлена'}"
                  + (f"  ·  дата события из извлечения: {src['event_date']}" if src['event_date'] else ""),
                  f"- **Цитата дословно**: «{src['quotes'][0]['text']}»",
                  f"- **Предложенный тип дефекта**: `{ann['proposed_error_type']}` — {ann['proposed_error_basis']}",
                  f"- **Вердикт сервиса**: {r['observations']['automatic_observations'][0]['value']}",
                  f"- **Решение человека**: _не принято_", ""]
    (dest / "dataset-readable.md").write_text("\n".join(lines), encoding="utf-8")

    # Автоматические признаки: только то, что живой сервис действительно знает сам.
    # Исправленных человеком значений здесь нет — задание требует их не смешивать.
    feats = []
    for r in records:
        mi, src = r["model_input"], r["sources"][0]
        feats.append({
            "sample_id": r["sample_id"],
            "collector": "automatic_only",
            "extractor_stage_label": r["observations"]["automatic_observations"][1]["value"],
            "organizations_named": len(r["observations"]["organizations"]),
            "has_dated_event": bool(src["event_date"]),
            "publication_date_known": bool(src["publication_date"]),
            "source_access": src["access"],
            "source_type": src["source_type"],
            "quote_chars": len(src["quotes"][0]["text"]),
            "mechanism_chars": len(mi["mechanism"] or ""),
            "application_present": bool(mi["application"]),
            "missing": [m for m in r["annotations"]["missing_data"] if m],
        })
    (dest / "features-automatic.json").write_text(json.dumps(feats, ensure_ascii=False, indent=1),
                                                  encoding="utf-8")

    # Журнал поиска: настоящие запросы и артефакты лежат в прогонах, здесь указатели на них.
    log = [{"sample_id": r["sample_id"], "origin_run": r["provenance"]["original_run_id"],
            "query": r["provenance"]["origin_query"],
            "search_artifacts": f"radar-runs/{r['provenance']['original_run_id']}/hits.jsonl",
            "fetch_artifacts": f"radar-runs/{r['provenance']['original_run_id']}/fetches.jsonl",
            "note": "поиск выполнялся живым прогоном радара, дополнительных запросов для "
                    "этого набора не делалось"} for r in records]
    (dest / "search-log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1),
                                          encoding="utf-8")

    (dest / "split.json").write_text(json.dumps({
        "assigned": False,
        "reason": "C2 — часть набора из 300 записей. Группы и split назначает тот, кто "
                  "собирает весь датасет: группировать надо вместе с A, B, C1 и C3, "
                  "иначе одна технология окажется в обучении и в контроле одновременно.",
        "available_grouping_keys": ["technology_family_id", "sources[].url",
                                    "provenance.original_run_id"],
        "constraint": "все записи имеют previously_used=true: прогоны использовались в "
                      "разработке, независимым тестом набор не является",
        "seed_recommended_by_brief": 42}, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = collections.Counter(r["annotations"]["proposed_error_type"] for r in records)
    areas = collections.Counter(r["model_input"]["area"] for r in records)
    runs = collections.Counter(r["provenance"]["original_run_id"] for r in records)
    missing = ["name_broader_than_source", "application_from_other_area"]
    info = {"schema_version": SCHEMA, "cohort": "C2", "built_on": "2026-09-28",
            "types_from_brief_not_represented": missing,
            "why_not_represented": "машинных вердиктов «громко: термин слишком общий» и "
                                   "«сомнение в принадлежности области» в сохранённых "
                                   "разборах нет: после правок 28.09 такие кандидаты "
                                   "отбраковываются раньше, по возрасту термина. Эти два "
                                   "типа добираются новым прогоном, синтетикой не заменены.",
            "cutoff": CUTOFF, "records": len(records),
            "records_are_human_labelled": False, "paid_api_calls": 0,
            "candidate_rows_available": len(rows),
            "detected_by_type": dict(collections.Counter(
                {k: len(v) + taken[k] for k, v in by_kind.items()})),
            "selected_by_type": dict(counts), "by_area": dict(areas), "by_run": dict(runs),
            "families": len({r["provenance"]["technology_family_id"] for r in records}),
            "sources_unique": len({s["url"] for r in records for s in r["sources"]}),
            "note": "Проблемные карточки живого конвейера. Типы дефектов предложены по "
                    "обнаружимым признакам и являются гипотезами; окончательное решение "
                    "за человеком. Отказ по измерению не считается дефектом карточки."}
    (dest / "manifest.json").write_text(json.dumps(info, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    print(json.dumps({k: info[k] for k in ("records", "selected_by_type", "by_area",
                                           "families", "sources_unique")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
