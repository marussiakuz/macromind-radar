"""Парный опыт: расширенная загрузка и отбор документов на зафиксированном снимке.

Протокол: `bench/protocol-expansion-2026-09-28.md`, задание Codex в
`radar-codex/reports/document-selection-2026-09-28.md`.

Ветвь A — сохранённый набор извлечения исходного прогона, ничего не перезапускается.
Ветвь B — очередь загрузки доводится до 160 уникальных URL из того же `hits.jsonl`, на
извлечение отбирается до 48 документов по разнообразию. Новый поиск не выполняется.

Измеренное до запуска (прогон 20260927-082453-финтех): 342 позиции поиска, 300 уникальных
URL, 54 попытки загрузки, 47 документов. То есть 246 уникальных URL до отбора не дошли,
и 144 из них принадлежат линзе «fix» — той, что ищет нерешённые проблемы.
"""
from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit

HACK = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(HACK))

from radar.config import Settings, load_env_file                     # noqa: E402
from radar.fetch import Fetcher, parse_document                      # noqa: E402
from radar.extract import YandexLLM, extract                         # noqa: E402
from radar.hoststats import host_of, layer_of                        # noqa: E402

TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "trk",
            "fbclid", "gclid", "yclid", "ref", "_ga"}


def norm_url(url: str) -> str:
    """Убирает фрагмент и известные метки отслеживания: это тот же документ."""
    parts = urlsplit(url or "")
    query = "&".join(p for p in parts.query.split("&")
                     if p and p.split("=")[0].lower() not in TRACKING)
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def load_snapshot(run: Path) -> dict:
    hits = [json.loads(l) for l in (run / "hits.jsonl").read_text(encoding="utf-8").splitlines()]
    fetches = [json.loads(l) for l in (run / "fetches.jsonl").read_text(encoding="utf-8").splitlines()]
    docs = [json.loads(l) for l in (run / "documents.jsonl").read_text(encoding="utf-8").splitlines()]
    cands = [json.loads(l) for l in (run / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    by_url: dict[str, list[dict]] = {}
    for h in hits:
        by_url.setdefault(norm_url(h["url"]), []).append(h)
    return {"hits": hits, "by_url": by_url, "attempted": {norm_url(f["url"]) for f in fetches},
            "docs": docs, "cands": cands}


def queue_extra(snap: dict, target_total: int, per_owner: int) -> list[tuple[str, dict]]:
    """Круговой отбор новых URL по запросам: ни один запрос не должен захватить квоту."""
    owner_used = collections.Counter(host_of(u) for u in snap["attempted"])
    by_query: dict[str, list[tuple[str, dict]]] = collections.defaultdict(list)
    for url, rows in snap["by_url"].items():
        if url in snap["attempted"]:
            continue
        row = rows[0]
        by_query[row.get("query", "")].append((url, row))
    for q in by_query:
        by_query[q].sort(key=lambda t: t[1].get("position", 99))
    queue: list[tuple[str, dict]] = []
    budget = max(0, target_total - len(snap["attempted"]))
    queries = sorted(by_query)
    while len(queue) < budget and any(by_query[q] for q in queries):
        for q in queries:
            if len(queue) >= budget or not by_query[q]:
                continue
            url, row = by_query[q].pop(0)
            owner = host_of(url)
            if owner_used[owner] >= per_owner:
                continue
            owner_used[owner] += 1
            queue.append((url, row))
    return queue


def select_diverse(docs: list[dict], limit: int) -> list[dict]:
    """Круговой отбор на извлечение: по запросу, затем по хосту, первоисточник вперёд.

    Тот же принцип, который на отборе ссылок поднял число работающих запросов с 7 до 34.
    На уровне документов его до сих пор не было: брались первые по порядку загрузки.
    """
    by_query: dict[str, list[dict]] = collections.defaultdict(list)
    for d in docs:
        by_query[d.get("_query", "")].append(d)
    for q in by_query:
        # Внутри запроса вперёд идут первоисточники, затем всё остальное; при равенстве —
        # по порядку выдачи. Слой считается тем же правилом, каким мы мерили долю
        # первоисточников в выдаче (3,3 %).
        by_query[q].sort(key=lambda d: (0 if layer_of(host_of(d.get("url", ""))) == "первоисточник"
                                        else 1, d.get("_position", 99)))
    picked: list[dict] = []
    host_used: collections.Counter = collections.Counter()
    queries = sorted(by_query)
    while len(picked) < limit and any(by_query[q] for q in queries):
        for q in queries:
            if len(picked) >= limit or not by_query[q]:
                continue
            d = by_query[q].pop(0)
            host = host_of(d.get("url", ""))
            if host_used[host] >= 3:
                continue
            host_used[host] += 1
            picked.append(d)
    return picked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=HACK / "radar-runs/20260927-082453-финтех")
    ap.add_argument("--out", type=Path, default=HACK / "bench/exp-expand-20260928")
    ap.add_argument("--target-urls", type=int, default=160)
    ap.add_argument("--per-owner", type=int, default=4)
    ap.add_argument("--extract-limit", type=int, default=48)
    ap.add_argument("--fetch-only", action="store_true", help="только загрузка, без оплаты извлечения")
    args = ap.parse_args(argv)

    load_env_file()
    settings = Settings()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    snap = load_snapshot(args.run)
    print(f"снимок: позиций {len(snap['hits'])}, уникальных URL {len(snap['by_url'])}, "
          f"попыток загрузки {len(snap['attempted'])}, документов {len(snap['docs'])}, "
          f"кандидатов {len(snap['cands'])}")

    extra_path = out / "documents-extra.jsonl"
    skip_path = out / "skip-log.jsonl"
    if extra_path.exists():
        new_docs = [json.loads(l) for l in extra_path.read_text(encoding="utf-8").splitlines()]
        print(f"повторный запуск: беру {len(new_docs)} уже загруженных документов из {extra_path.name}")
    else:
        queue = queue_extra(snap, args.target_urls, args.per_owner)
        print(f"в очередь на загрузку: {len(queue)} новых URL "
              f"(цель по сумме попыток {args.target_urls})")
        new_docs, skips = [], []
        started = time.time()
        with Fetcher(settings, raw_dir=out / "raw") as fetcher:
            for i, (url, row) in enumerate(queue, 1):
                if time.time() - started > 900:
                    skips.append({"url": url, "reason": "дедлайн загрузки 900 с"})
                    continue
                try:
                    result, body = fetcher.fetch(url)
                except Exception as exc:
                    skips.append({"url": url, "reason": f"{type(exc).__name__}: {exc}"[:120]})
                    continue
                if result.status != "ok" or body is None:
                    skips.append({"url": url, "reason": result.status,
                                  "http": result.http_status, "error": result.error})
                    continue
                doc = parse_document(body, url, result.final_url or url, result.content_type)
                if doc is None:
                    skips.append({"url": url, "reason": "не разобрано",
                                  "content_type": result.content_type})
                    continue
                item = json.loads(doc.model_dump_json()) if hasattr(doc, "model_dump_json") else dict(doc.__dict__)
                item["_query"] = row.get("query", "")
                item["_lens"] = row.get("lens", "")
                item["_position"] = row.get("position", 99)
                new_docs.append(item)
                if i % 20 == 0:
                    print(f"  загружено {len(new_docs)} из {i} попыток, {int(time.time()-started)} с")
        extra_path.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in new_docs),
                              encoding="utf-8")
        skip_path.write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in skips),
                             encoding="utf-8")
        reasons = collections.Counter(s["reason"] for s in skips)
        print(f"новых документов: {len(new_docs)}; пропусков {len(skips)}: {dict(reasons.most_common(6))}")

    # Старые документы получают те же служебные поля, чтобы отбор был честным для обеих ветвей.
    old_docs = []
    for d in snap["docs"]:
        rows = snap["by_url"].get(norm_url(d.get("url", ""))) or snap["by_url"].get(norm_url(d.get("final_url", "")))
        row = rows[0] if rows else {}
        d = dict(d)
        d["_query"] = row.get("query", "")
        d["_lens"] = row.get("lens", "")
        d["_position"] = row.get("position", 99)
        d["_origin"] = "A"
        old_docs.append(d)
    for d in new_docs:
        d["_origin"] = "B"

    pool = old_docs + new_docs
    selected = select_diverse(pool, args.extract_limit)
    from_a = sum(1 for d in selected if d.get("_origin") == "A")
    print(f"\nотобрано на извлечение: {len(selected)} документов — "
          f"{from_a} из исходного набора, {len(selected) - from_a} новых")
    print("  запросов охвачено:", len({d.get('_query') for d in selected}),
          "| хостов:", len({host_of(d.get('url','')) for d in selected}),
          "| первоисточников:", sum(1 for d in selected
                                    if layer_of(host_of(d.get('url',''))) == 'первоисточник'))
    (out / "selection.json").write_text(json.dumps(
        [{"url": d.get("url"), "origin": d.get("_origin"), "query": d.get("_query"),
          "lens": d.get("_lens"), "host": host_of(d.get("url", "")),
          "layer": layer_of(host_of(d.get("url", "")))} for d in selected],
        ensure_ascii=False, indent=1), encoding="utf-8")

    need_extract = [d for d in selected if d.get("_origin") == "B"]
    reuse = [d for d in selected if d.get("_origin") == "A"]
    print(f"\nстоимость до запуска: извлечь заново {len(need_extract)} документов; "
          f"переиспользовать {len(reuse)} без оплаты")
    if args.fetch_only:
        print("режим --fetch-only: извлечение не запускалось")
        return 0

    by_doc_sha = collections.defaultdict(list)
    for c in snap["cands"]:
        by_doc_sha[c.get("document_sha256")].append(c)
    cands: list[dict] = []
    for d in reuse:
        cands.extend(by_doc_sha.get(d.get("text_sha256"), []))
    print(f"переиспользовано кандидатов: {len(cands)}")

    llm = YandexLLM(settings)
    from radar.config import DocumentSnapshot
    in_tok = out_tok = 0
    for i, item in enumerate(need_extract, 1):
        payload = {k: v for k, v in item.items() if not k.startswith("_")}
        try:
            doc = DocumentSnapshot(**payload)
            res = extract(doc, llm, cutoff="2026-09-27")
        except Exception as exc:
            print(f"  извлечение отказало на {item.get('url','')[:60]}: {type(exc).__name__}")
            continue
        in_tok += res.input_tokens
        out_tok += res.output_tokens
        got = [json.loads(c.model_dump_json()) if hasattr(c, "model_dump_json") else dict(c.__dict__)
               for c in res.candidates]
        cands.extend(got)
        if i % 5 == 0 or i == len(need_extract):
            print(f"  извлечено {i}/{len(need_extract)}, кандидатов всего {len(cands)}")
    # Данные пишем ДО всего остального. Первый запуск упал на расчёте стоимости после
    # извлечения, и результат семнадцати оплаченных вызовов был потерян. Это ровно та
    # ошибка, на которой я уже терял прогон: сначала сохранить, потом считать.
    (out / "candidates.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cands), encoding="utf-8")
    from radar.config import Prices
    prices = Prices()
    cost = (in_tok / 1e6 * prices.llm_input_rub_per_mtok
            + out_tok / 1e6 * prices.llm_output_rub_per_mtok)
    manifest = {"query": json.loads((args.run / "manifest.json").read_text(encoding="utf-8"))["query"],
                "mode": "live", "branch": "B",
                "source_run": args.run.name, "cutoff": "2026-09-27",
                "counters": {"queries": 0, "hits": len(snap["hits"]),
                             "unique_urls": len(snap["by_url"]),
                             "parsed_ok": len(selected), "after_merge": len(cands)},
                "tokens": {"input": in_tok, "output": out_tok},
                "cost_rub": round(cost, 2),
                "note": "ветвь B парного опыта расширенной загрузки; поиск не вызывался"}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    print(f"\nветвь B: кандидатов {len(cands)}, токены {in_tok}/{out_tok}, "
          f"стоимость извлечения ≈ {cost:.2f} ₽")
    print(f"результат: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
