"""Пакет реальных кандидатов конвейера для разметки «слабый / зрелый / неясно».

Зачем. Пилот Codex учится различать 30 строк таблицы заказчика и 30 подобранных вручную
«зрелых соседей». Это не наш режим отказа: в живом прогоне отрицательные примеры — это
вендорские подборки, обзоры и общие формулировки, а не аккуратные зрелые аналоги. Они это
сами записали в ограничениях: «перед внедрением нужен дополнительный набор реальных
кандидатов из конвейера с одинаковым способом подготовки текста». Здесь такой набор.

Что здесь сознательно НЕ делается:
  * не проставляется никакая метка, в том числе по нашему баллу и уровню (`signal`/`review`)
    — иначе классификатор выучит решение нашего же фильтра;
  * не отмечается, совпал ли кандидат со строкой таблицы заказчика, хотя такие в выборке
    есть: пометка втащила бы таблицу в обучение и убила бы её как независимую метрику;
  * `quote` хранится дословно для человека, но в признаки модели он у Codex не входит
    (`feature_text` берёт area, category, mechanism, application, cutoff и `summary_ru`).

Ограничение, которое надо держать в голове при обучении: у карточек Codex `summary_ru` —
пересказ куратора, у наших — пересказ модели по сохранённому снимку. Регистр я выравнивал
инструкцией, но полностью совпасть он не может. Поэтому смешивать два пакета в одном
обучении нельзя без контроля на происхождение: модель может выучить составителя.
Правильное применение этого пакета — отдельная проверка переноса.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from datetime import date
from pathlib import Path

HACK = Path(__file__).resolve().parents[1]
CODEX = HACK.parent / "radar-codex"
sys.path.insert(0, str(HACK))
sys.path.insert(0, str(CODEX))

from radar.hoststats import host_of, layer_of              # noqa: E402
from signal_radar.weakness_binary import digest, freeze_split, validate_packet  # noqa: E402

CUTOFF = "2026-09-28"
RUNS = {
    "Финтех": ["20260927-082453-финтех", "20260927-213138-финтех", "20260926-182222-финтех"],
    "Защита ИИ": ["20260927-083230-защита", "20260926-181346-защита"],
}
# Роль источника в их схеме — primary или secondary. Первоисточник у нас определяет
# `radar/hoststats.py` по хосту, тем же правилом, каким мы считали долю первоисточников.
SOURCE_TYPE = {"первоисточник": "primary"}

SUMMARY_SYSTEM = """Ты пишешь короткую нейтральную выжимку по одному источнику для эксперта,
который будет решать, зрелая это технология или ранняя.

Три предложения, по-русски:
1. Что источник утверждает — кто и что делает, дословными фактами из цитаты.
2. Датированная конкретика, если она есть в цитате (год, раунд, пилот, релиз, стандарт).
3. Чего источник НЕ доказывает: чего в нём нет.

Запрещено: оценивать зрелость или раннюю стадию, писать «слабый сигнал», «зарождающийся»,
«перспективный», рекламные слова, домыслы за пределами цитаты. Если в цитате нет даты,
третье предложение так и говорит: дата в источнике не указана.

Верни только JSON: {"items": [{"index": <номер>, "summary_ru": "<три предложения>"}]}."""


def stage_bucket(stage: str) -> str:
    if stage in ("research", "prototype", "pilot"):
        return "раннее"
    if stage == "limited_sales":
        return "продаётся_ограниченно"
    if stage == "scaled":
        return "масштабировано"
    return "стадия_неизвестна"


def load_area(runs: list[str], stats: dict) -> list[dict]:
    """Кандидаты области из нескольких прогонов, без повторов, только с дословной цитатой."""
    docs: dict[str, dict] = {}
    seen: set[tuple] = set()
    out: list[dict] = []
    for name in runs:
        run = HACK / "radar-runs" / name
        for line in (run / "documents.jsonl").read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            docs[d.get("final_url") or d.get("url", "")] = d
            docs.setdefault(d.get("url", ""), d)
        for line in (run / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            stats["пул_всего"] += 1
            quotes = [e for e in (c.get("evidence") or []) if (e.get("quote") or "").strip()]
            if not quotes or not c.get("source_url"):
                stats["исключено_нет_цитаты_или_ссылки"] += 1
                continue
            key = (c["name_ru"].strip().lower(), c["source_url"])
            if key in seen:
                stats["исключено_повтор"] += 1
                continue
            seen.add(key)
            c["_run"] = name
            c["_docs"] = docs
            out.append(c)
    return out


def sample_area(cands: list[dict], want: int) -> list[dict]:
    """Круговой отбор по слоям источника и стадиям: нужна реалистичная смесь, не топ.

    Тот же принцип, который на отборе URL поднял число работающих запросов с 7 до 34:
    брать по одному из каждой страты по кругу, а не заполнять квоту первыми подходящими.
    """
    strata: dict[tuple, list[dict]] = collections.defaultdict(list)
    for c in cands:
        layer = layer_of(host_of(c["source_url"]))
        strata[(layer, stage_bucket(c.get("stage") or "unknown"))].append(c)
    for key in strata:
        strata[key].sort(key=lambda c: digest([c["name_ru"], c["source_url"]]))
    picked: list[dict] = []
    keys = sorted(strata, key=lambda k: (-len(strata[k]), k))
    while len(picked) < want and any(strata[k] for k in keys):
        for k in keys:
            if strata[k] and len(picked) < want:
                picked.append(strata[k].pop(0))
    return picked


def concerns_of(cand: dict, layer: str, has_date: bool) -> list[str]:
    notes = []
    if layer != "первоисточник":
        notes.append(f"источник не первоисточник ({layer}): проверьте по ссылке, кто делает заявление.")
    if not has_date:
        notes.append("дата документа не установлена; свежесть по этому источнику не проверена.")
    # Стадию, присвоенную извлекателем (prototype / limited_sales / scaled), в карточку не
    # выводим вообще. Возражение Codex 28.09 верное: оговорка «не проверенный факт» подсказку
    # не снимает, а человек здесь решает ровно тот же вопрос, на который модель уже ответила.
    notes.append("стадию определите сами по тексту источника: наша оценка стадии в карточке "
                 "не показана намеренно.")
    if len(cand.get("organizations") or []) == 0:
        notes.append("организации в источнике не названы: кто это делает, по документу не видно.")
    return notes


def build_rows(area_cands: dict[str, list[dict]], summaries: dict[str, str],
               stats: dict) -> list[dict]:
    rows, n, used = [], 0, set()
    for area in sorted(area_cands):
        for cand in area_cands[area]:
            n += 1
            sources = []
            for ev in [e for e in (cand.get("evidence") or []) if (e.get("quote") or "").strip()][:2]:
                url = ev.get("source_url") or cand["source_url"]
                doc = cand["_docs"].get(url) or cand["_docs"].get(cand["source_url"]) or {}
                quote = (ev.get("quote") or "").strip()
                text = doc.get("text") or ""
                # Проверка «цитата — подстрока сохранённого снимка» перенесена в сборщик:
                # Codex подтвердил её вручную на 43/43, но в коде её не было, и пакет мог
                # уехать с непроверенной цитатой. Не прошло — источник не берём.
                start = text.find(quote) if text and quote else -1
                if start < 0:
                    stats["исключено_цитата_не_в_снимке"] += 1
                    continue
                # Дата публикации — только из метаданных документа. `event_date` кандидата
                # сюда больше не подставляется: в v1 так вышло дважды (карточка про фреймворк
                # оценки рисков получила 2025-12-10 при отсутствии даты у документа), и это
                # смешивало дату события из цитаты с датой публикации источника.
                pub = (doc.get("published_at") or "")[:10]
                if pub:
                    try:
                        if date.fromisoformat(pub) > date.fromisoformat(CUTOFF):
                            # Документ позже даты оценки нельзя использовать как основание
                            # исторического решения. В v1 дата обнулялась, а источник
                            # оставался — это обход календарного валидатора.
                            stats["исключено_источник_после_среза"] += 1
                            continue
                    except ValueError:
                        pub = ""
                claimed = (cand.get("event_date") or "")[:10] or None
                layer = layer_of(host_of(url))
                item = {
                    "url": url,
                    "title": (doc.get("title") or host_of(url))[:160],
                    "date": pub or None,
                    "date_origin": "document_metadata" if pub else "unknown",
                    "event_date_claimed": claimed,
                    "event_date_origin": "extractor_from_quote_unverified" if claimed else None,
                    "summary_ru": summaries.get(digest([url, ev.get("quote", "")]), ""),
                    "quote": quote[:400],
                    "quote_start": start,
                    "quote_end": start + len(quote),
                    "document_sha256": doc.get("text_sha256") or "",
                    "verification": "quote_found_in_saved_snapshot_by_builder",
                    "source_type": SOURCE_TYPE.get(layer, "secondary"),
                    "source_layer": layer,
                    "checked_on": CUTOFF,
                    "note_type": "model_paraphrase_of_saved_snapshot_with_verbatim_quote",
                }
                item["source_id"] = digest(item)[:16]
                sources.append(item)
            if not sources:
                continue
            if not all(s["summary_ru"].strip() for s in sources):
                continue
            # Семейство больше не «первые два слова названия»: получались «обнаружение-и»,
            # «аудит-и» — ключи, которые выглядят как проверенные семейства технологий, но
            # ничего не значат. Ставим нейтральный идентификатор, а предполагаемые семейства
            # выносим отдельной таблицей на ручную проверку до заморозки контроля.
            sid = digest([area, cand["name_ru"], cand["source_url"], "pipeline/1"])[:24]
            if sid in used:      # один и тот же документ встречается в пулах двух областей
                continue
            used.add(sid)
            rows.append({
                "sample_id": digest([area, cand["name_ru"], cand["source_url"], "pipeline/1"])[:24],
                "pair_id": f"pipe-{n:03}",
                "area": area,
                "cutoff": CUTOFF,
                "category": cand["name_ru"][:200],
                "mechanism": (cand.get("mechanism") or "")[:600],
                "application": (cand.get("object_affected") or cand.get("context") or "")[:300],
                "family": "fam-" + digest([cand["name_ru"], cand.get("mechanism", "")])[:8],
                "sources": sources,
                "reference_label": None,
                "proposed_label": None,
                "proposal_source": "radar_pipeline_candidate_unlabeled",
                "concerns": concerns_of(cand, layer_of(host_of(cand["source_url"])),
                                       bool(sources[0]["date"])),
                "boundary": "",
                "maturity_reason": "",
                "reference_provenance": None,
                "provenance_role": "pipeline",
                "origin_run": cand["_run"],
                "packet_version": "pipeline/2",
            })
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path,
                    default=HACK / "learning/pipeline-candidates-v2-20260928")
    ap.add_argument("--per-area", type=int, default=15)
    ap.add_argument("--test-pairs", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true", help="состав выборки без платных вызовов")
    args = ap.parse_args(argv)

    stats: dict = collections.Counter()
    pool = {area: load_area(runs, stats) for area, runs in RUNS.items()}
    # Доли слоёв до и после отбора: круговой отбор выравнивает страты, то есть меняет
    # частоты относительно исходного потока. Возражение Codex верное — по этим 30 нельзя
    # заявлять долю слабых сигналов в реальном потоке, поэтому обе доли печатаем.
    before = {area: collections.Counter(layer_of(host_of(c["source_url"])) for c in cands)
              for area, cands in pool.items()}
    chosen = {area: sample_area(cands, args.per_area) for area, cands in pool.items()}
    after = {area: collections.Counter(layer_of(host_of(c["source_url"])) for c in chosen[area])
             for area in chosen}
    for area, cands in chosen.items():
        mix = collections.Counter((layer_of(host_of(c["source_url"])), stage_bucket(c.get("stage") or "unknown"))
                                  for c in cands)
        print(f"{area}: {len(cands)} карточек")
        for (layer, stage), k in sorted(mix.items()):
            print(f"   {k}× {layer} / {stage}")
    if args.dry_run:
        for area, cands in chosen.items():
            print(f"\n--- {area} ---")
            for c in cands:
                print(f"  {c['name_ru'][:64]:64s} {host_of(c['source_url'])[:26]}")
        return 0

    from radar.config import Settings, load_env_file
    from radar.extract import YandexLLM
    load_env_file()
    llm = YandexLLM(Settings(), max_tokens=1500)
    tasks = []
    for area, cands in chosen.items():
        for c in cands:
            for ev in [e for e in (c.get("evidence") or []) if (e.get("quote") or "").strip()][:2]:
                url = ev.get("source_url") or c["source_url"]
                tasks.append((digest([url, ev.get("quote", "")]),
                              {"технология": c["name_ru"][:90], "механизм": (c.get("mechanism") or "")[:200],
                               "цитата": (ev.get("quote") or "")[:400], "источник": host_of(url)}))
    cache_path = HACK / "learning/.summaries-cache.json"
    summaries: dict[str, str] = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    tasks = [t for t in tasks if t[0] not in summaries]
    print(f"выжимок в кеше {len(summaries)}, к запросу {len(tasks)}")
    for start in range(0, len(tasks), 8):
        chunk = tasks[start:start + 8]
        payload = {"записи": [{"index": i, **body} for i, (_, body) in enumerate(chunk)]}
        try:
            text, _, _ = llm.complete(SUMMARY_SYSTEM, payload)
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        except (ValueError, KeyError) as exc:
            print(f"  выжимка {start}: отказ {type(exc).__name__}")
            continue
        for item in data.get("items", []):
            idx = item.get("index")
            if isinstance(idx, int) and 0 <= idx < len(chunk):
                summaries[chunk[idx][0]] = str(item.get("summary_ru") or "").strip()[:700]
        print(f"  выжимки {start + len(chunk)}/{len(tasks)}")
        cache_path.write_text(json.dumps(summaries, ensure_ascii=False), encoding="utf-8")

    rows = build_rows(chosen, summaries, stats)
    if not rows:
        print("ни одной карточки с выжимками — пакет не собран")
        return 1
    dest = args.output
    dest.mkdir(parents=True, exist_ok=True)
    manifest = freeze_split(rows, test_pairs=min(args.test_pairs, max(2, len(rows) // 3)))
    validate_packet(rows, manifest)
    pending = [{"sample_id": r["sample_id"], "dossier_hash": manifest["row_hashes"][r["sample_id"]],
                "status": "pending", "label": None, "label_source": None, "reviewer": "", "reviewed_on": "",
                "rationale": "", "source_ids": [], "facts_checked": False, "stage_checked": False,
                "family_checked": False, "family_correction": ""} for r in rows]
    for name, records in [("dossiers.jsonl", rows), ("labels.pending.jsonl", pending)]:
        (dest / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                                 encoding="utf-8")
    (dest / "split.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    info = {"samples": len(rows), "packet_version": "pipeline/2",
            "provenance": "radar_live_pipeline_candidates",
            "sampling": "stratified diagnostic slice (source layer x stage), not the natural pipeline distribution",
            "origin_runs": sorted({r["origin_run"] for r in rows}),
            "selection_counters": dict(stats),
            "layer_shares_before_sampling": {a: dict(c) for a, c in before.items()},
            "layer_shares_after_sampling": {a: dict(c) for a, c in after.items()},
            "quote_check": "every source quote located in the saved snapshot text by the builder",
            "dates": "date = document publication metadata only; candidate event_date kept separately as event_date_claimed",
            "human_reviewed_dossiers": 0, "proposed_labels": 0,
            "customer_table_annotated": False,
            "split_counts": dict(collections.Counter(manifest["split"].values())),
            "group_count": len(set(manifest["groups"].values())),
            "area_counts": dict(collections.Counter(r["area"] for r in rows)),
            "sources": len({s["url"] for r in rows for s in r["sources"]}),
            "evidence_storage": "Verbatim quote from saved snapshot plus model paraphrase; quote not in model features",
            "known_risk": "Paraphrase register differs from the reference pilot; do not mix packets without a provenance control",
            "trained": False, "automatic_deployment": False}
    (dest / "manifest.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    template = HACK / "learning/review-neutral.html"
    if template.exists():
        payload = json.dumps({"rows": rows, "labels": pending, "hashes": manifest["row_hashes"]},
                             ensure_ascii=False)
        (dest / "review.html").write_text(
            template.read_text(encoding="utf-8").replace("__PACKET_JSON__", payload.replace("<", "\\u003c")),
            encoding="utf-8")
    # Предполагаемые семейства — отдельной таблицей и БЕЗ меток: формальная группировка
    # не может узнать, что два ключа означают один механизм. До ручной проверки этой
    # таблицы разделение train/test считается предварительным.
    words: dict[str, list[str]] = collections.defaultdict(list)
    for r in rows:
        for w in {w for w in (r["category"] + " " + r["mechanism"]).lower().split() if len(w) > 6}:
            words[w].append(r["sample_id"])
    overlaps = {w: ids for w, ids in words.items() if len(ids) > 1}
    lines = ["# Предполагаемые семейства: ручная проверка до заморозки контроля", "",
             "Формальные ключи `family` в пакете нейтральные (`fam-<хеш>`) и намеренно ничего",
             "не утверждают. Ниже — пары карточек, у которых совпадают значимые слова названия",
             "или механизма. Это подсказка для человека, а не установленное семейство.",
             "Если две карточки об одной технологии, их нужно объединить в одну группу,",
             "иначе одна попадёт в обучение, другая в контроль и оценка будет завышена.", "",
             "| Общее слово | Карточки | Названия |", "|---|---|---|"]
    by_id = {r["sample_id"]: r for r in rows}
    for w, ids in sorted(overlaps.items(), key=lambda kv: -len(kv[1]))[:40]:
        names = " / ".join(by_id[i]["category"][:46] for i in ids[:3])
        lines.append(f"| {w} | {len(ids)} | {names} |")
    (dest / "families-to-review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print(f"пар карточек с общими словами для ручной сверки: {len(overlaps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
