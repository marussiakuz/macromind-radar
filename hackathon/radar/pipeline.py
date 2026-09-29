"""Построение пула кандидатов: поиск, загрузка, извлечение и объединение.

CLI сохраняет результаты в RADAR_RUNS_DIR. Фильтры и карточки собирает HTTP-сервис."""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .config import (Candidate, DocumentSnapshot, Limits, RunManifest, SearchHit, Settings,
                     RUNS_DIR, FIXTURES_DIR, load_env_file)
from .evaluate import Funnel, compute_c, check_do_not_merge, read_review_file, report, suggest_matches, write_review_file
from .extract import PROMPT_VERSION, FixtureLLM, YandexLLM, extract, merge_candidates
from .selection import select_documents, document_contexts
from .passages import all_spans, unread_sections
from .versioning import pool_signature
from .dedup import accept as accept_candidates
from .fetch import Fetcher, FixtureFetcher, parse_document
from .hypotheses import generate as generate_hypotheses, verify as verify_hypothesis
from .reference import area_items, load_reference
from .openalex import OpenAlexSearch
from .search import (FixtureSearch, MultiSearch, YandexSearch, build_queries, plan_subsegments,
                     plan_subsegments_grounded, select_urls)


def _jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row if isinstance(row, dict) else row.model_dump(), ensure_ascii=False) + "\n")


def estimate_cost(settings: Settings, search_calls: int, in_tokens: int, out_tokens: int) -> float:
    p = settings.prices
    return round(
        search_calls * p.search_call_rub
        + in_tokens / 1_000_000 * p.llm_input_rub_per_mtok
        + out_tokens / 1_000_000 * p.llm_output_rub_per_mtok,
        2,
    )


def dry_run(area: str, settings: Settings) -> str:
    """Считает, во что обойдётся прогон, и ничего не тратит."""
    lim = settings.limits
    in_tok = lim.extraction_packets * 4000 + 2000
    out_tok = lim.extraction_packets * 700
    cost = estimate_cost(settings, lim.discovery_queries, in_tok, out_tok)
    return "\n".join([
        f"Область: {area}",
        f"поисковых вызовов        {lim.discovery_queries}",
        f"позиций выдачи           до {lim.discovery_queries * lim.results_per_query}",
        f"попыток загрузки         до {lim.fetch_attempts}",
        f"пакетов извлечения       до {lim.extraction_packets}",
        f"входных токенов ≈        {in_tok}",
        f"выходных токенов ≈       {out_tok}",
        f"стоимость ≈              {cost} ₽",
        "",
        "Это оценка этапа извлечения по заданным тарифам. Проверки и карточки оплачиваются отдельно.",
    ])


def run_pool(
    area: str,
    direction: str,
    mode: str,
    settings: Settings,
    max_docs: int | None = None,
    runs_dir: Path = RUNS_DIR,
    lenses: tuple[str, ...] = ("product", "funding", "standard", "research"),
    plan: str = "tree",
) -> Path:
    """Один прогон: план → поиск → загрузка → разбор → извлечение → склейка → метрика."""
    lim: Limits = settings.limits
    started = time.monotonic()
    slug = (area or direction).split()[0].lower()[:24] if (area or direction) else "запрос"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + f"-{slug}"
    out = runs_dir / run_id
    out.mkdir(parents=True, exist_ok=True)

    # Область пустая — открытый запрос пользователя: эталона для него не существует,
    # метрика C не считается, конвейер работает как обычно.
    if area:
        reference, ref_sha = load_reference()
        items = area_items(reference, area)
    else:
        reference, ref_sha, items = [], "", []
    funnel = Funnel()

    if mode == "live":
        if not settings.has_keys:
            raise RuntimeError("для режима live нужны YANDEX_API_KEY и YANDEX_FOLDER_ID")
        # Линза research уходит в OpenAlex: бесплатно, и аннотация приходит сразу,
        # поэтому такие документы не нужно скачивать.
        searcher = MultiSearch(YandexSearch(settings, cache_dir=out / "search"),
                               {"research": OpenAlexSearch()})
        llm = YandexLLM(settings)
    else:
        searcher = FixtureSearch(FIXTURES_DIR / "search")
        llm = FixtureLLM(json.loads((FIXTURES_DIR / "llm.json").read_text(encoding="utf-8"))
                         if (FIXTURES_DIR / "llm.json").exists() else {})

    tree = None
    if mode == "live" and plan == "tree":
        from .discovery import plan_tree
        tree = plan_tree(direction, llm, searcher)
        (out / "discovery-tree.json").write_text(json.dumps(tree, ensure_ascii=False, indent=2))
        subsegments, planner_source = tree['leaves'], tree['version']
    elif mode == "live":
        # Заземляем планировщик на свежую выдачу: из памяти модель даёт
        # таксономию атак образца 2020 года и нулевое покрытие эталона.
        subsegments, planner_source = plan_subsegments_grounded(direction, llm, searcher, plan=plan)
    else:
        subsegments, planner_source = plan_subsegments(direction, None)
    funnel.notes.append("подсегменты: " + planner_source + ", " +
                        ", ".join(x.get("en") or x.get("ru") for x in subsegments))

    hits: list[SearchHit] = []
    # Русские запросы имеют смысл только в вебе: в академических базах русских
    # работ по этим темам почти нет, а термины всё равно английские.
    ru_share = 0.0 if lenses == ("research",) else 0.2
    funnel.notes.append("режим плана: " + plan)
    if tree is not None:
        from .discovery import search_tree
        def save_search(t, found):
            (out / "discovery-tree.json").write_text(json.dumps(t, ensure_ascii=False, indent=2))
            _jsonl(out / "hits.jsonl", found)
        hits = search_tree(tree, searcher, lim.discovery_queries, lim.results_per_query,
                           started + lim.run_deadline_s, save_search)
        funnel.queries = len(tree['queries'])
    else:
        for query, lang, lens in build_queries(subsegments, lim.discovery_queries,
                                               ru_share=ru_share, lenses=lenses):
            hits.extend(searcher.search(query, lang, lens, lim.results_per_query))
            funnel.queries += 1
    funnel.notes.append("выполненные линзы: " + ", ".join(sorted({h.lens for h in hits})))
    funnel.hits = len(hits)

    api_snapshots = getattr(searcher, "snapshots", {}) or {}
    selected = select_urls(hits, lim.fetch_attempts, lim.max_per_owner,
                           exempt_urls=set(api_snapshots))
    funnel.unique_urls = len(selected)
    if max_docs:
        selected = selected[:max_docs]

    docs: list[DocumentSnapshot] = []
    fetches = []
    fetcher_ctx = (Fetcher(settings, raw_dir=out / "raw") if mode == "live"
                   else FixtureFetcher(FIXTURES_DIR / "docs"))
    # Загрузка идёт параллельно. Измерено 28.09.2026: последовательная давала 5,7 с на
    # ссылку, и расширение очереди до 160 добавляло десять минут — двадцатиминутный лимит
    # заказчика ломался. Пределы вежливости сохранены: к одному владельцу по очереди,
    # с задержкой, robots и запретом приватных адресов.
    with fetcher_ctx as fetcher:
        queue = [h for h in selected if api_snapshots.get(h.url) is None]
        for hit in selected:
            ready = api_snapshots.get(hit.url)
            if ready is not None:
                # Документ пришёл из API вместе с текстом: качать нечего.
                funnel.from_api += 1
                funnel.fetched_ok += 1
                funnel.parsed_ok += 1
                docs.append(ready)
        results: dict[int, tuple] = {}
        if queue:
            with ThreadPoolExecutor(max_workers=max(1, lim.concurrency)) as pool:
                futures = {pool.submit(fetcher.fetch, h.url): (i, h)
                           for i, h in enumerate(queue)}
                for fut in as_completed(futures):
                    i, h = futures[fut]
                    if time.monotonic() - started > lim.run_deadline_s:
                        funnel.notes.append("остановлено по дедлайну прогона")
                        break
                    try:
                        results[i] = (h, *fut.result())
                    except Exception as exc:          # отказ одной ссылки не валит прогон
                        funnel.notes.append(f"загрузка отказала: {type(exc).__name__}")
        for i in sorted(results):
            hit, result, body = results[i]
            funnel.fetch_attempts += 1
            fetches.append(result)
            if result.status != "ok" or body is None:
                continue
            funnel.fetched_ok += 1
            # Разбор по фактическому типу ответа: PDF раньше скачивался и выбрасывался,
            # а в PDF приходят как раз первоисточники — записки МВФ, доклады ЦБ, arXiv.
            snapshot = parse_document(body, hit.url, result.final_url or hit.url,
                                      result.content_type)
            if snapshot is None:
                continue
            funnel.parsed_ok += 1
            docs.append(snapshot)

    docs_for_extraction, selection_report = select_documents(
        docs, hits, lim.extraction_packets, tree=tree)
    contexts, _ = document_contexts(docs, hits, tree)
    _jsonl(out / "documents.jsonl", docs)
    _jsonl(out / "fetches.jsonl", fetches)
    (out / "extraction-plan.json").write_text(json.dumps(selection_report, ensure_ascii=False, indent=2))
    funnel.notes.append(f"на извлечение запланировано {len(docs_for_extraction)} из {len(docs)} "
                        "документов по листьям и содержательности; алиасы учитываются совместно")

    cutoff = datetime.now(timezone.utc).date().isoformat()
    candidates: list[Candidate] = []
    in_tok = out_tok = 0
    extraction_log, processed, continuations = [], [], []
    _jsonl(out / "extraction-results.jsonl", [])
    # Ключ повтора — документ плюс название; механизм модель пересказывает, см. dedup.py.
    candidate_keys: dict = {}
    accepted_stats = {"proposed": 0, "accepted": 0, "duplicates": 0,
                      "evidence_from_duplicates": 0}
    stopped = False
    reserve = min(4, max(0, lim.extraction_packets - len(tree['leaves']))) if tree else 0
    first_pass = min(len(docs_for_extraction), max(0, lim.extraction_packets - reserve))

    def process(doc, previous=None):
        nonlocal in_tok, out_tok, stopped
        if len(extraction_log) >= lim.extraction_packets:
            return
        if time.monotonic() - started >= lim.run_deadline_s:
            funnel.notes.append("извлечение остановлено по сроку; сохранён частичный пул")
            stopped = True
            return
        from .ledger import LimitReached
        exclude = previous.span_ids if previous and not previous.has_more_candidates else ()
        existing = [c.name_ru for c in candidates if c.document_sha256 == doc.text_sha256]
        try:
            res = extract(doc, llm, cutoff=cutoff, queries=contexts[doc.url]['queries'],
                          exclude_span_ids=exclude, existing_candidates=existing)
        except LimitReached:
            funnel.notes.append("извлечение остановлено по бюджету; сохранён частичный пул")
            stopped = True
            return
        in_tok += res.input_tokens
        out_tok += res.output_tokens
        stats = accept_candidates(candidates, candidate_keys, res.candidates)
        for name in ("proposed", "accepted", "duplicates", "evidence_from_duplicates"):
            accepted_stats[name] += stats[name]
        if doc not in processed:
            processed.append(doc)
        extraction_log.append({"url": doc.url, "document_sha256": doc.text_sha256,
            "continuation": previous is not None, "span_ids": res.span_ids,
            "candidate_count": len(res.candidates), "accepted": stats["accepted"],
            "duplicates": stats["duplicates"], "has_more_candidates": res.has_more_candidates,
            "no_technology_reason": res.no_technology_reason, "diagnostics": res.diagnostics,
            "input_tokens": res.input_tokens, "output_tokens": res.output_tokens})
        _jsonl(out / "extraction-results.jsonl", extraction_log)
        _jsonl(out / "candidates.partial.jsonl", candidates)
        (out / "extraction-selection.json").write_text(json.dumps(
            [d.url for d in processed], ensure_ascii=False, indent=2))
        # Причина продолжения записывается: «модель сказала, что всё» — это утверждение
        # о показанном тексте, а не о документе. 29.09.2026 документ 704d8f65… вернул три
        # кандидата и has_more_candidates=false, а непереданное окно s7 содержало
        # отдельную реализацию SNN-ускорителя с открытым маршрутом проектирования.
        reason = None
        if previous is None:
            unread = unread_sections(doc, res.span_ids)
            if res.has_more_candidates:
                reason = "модель сообщила о незавершённом чтении"
            elif not res.candidates and len(all_spans(doc)) > len(res.span_ids):
                reason = "пустой ответ при непрочитанном тексте"
            elif unread:
                reason = ("непрочитанные разделы с новым содержимым: "
                          + ",".join(s.span_id for s in unread[:6]))
            extraction_log[-1]["unread_sections"] = [s.span_id for s in unread]
            extraction_log[-1]["continuation_reason"] = reason
            if reason:
                continuations.append((doc, res))
            _jsonl(out / "extraction-results.jsonl", extraction_log)

    for doc in docs_for_extraction[:first_pass]:
        process(doc)
        if stopped: break
    # At most four follow-ups, inside the SAME packet cap. Explicit overflow comes first.
    if not stopped:
        for doc, previous in sorted(continuations, key=lambda pair: not pair[1].has_more_candidates)[:reserve]:
            process(doc, previous)
            if stopped: break
    if not stopped:
        for doc in docs_for_extraction[first_pass:]:
            process(doc)
            if stopped or len(extraction_log) >= lim.extraction_packets: break
    docs_for_extraction = processed
    (out / "extraction-selection.json").write_text(json.dumps(
        [d.url for d in processed], ensure_ascii=False, indent=2))
    funnel.notes.append(f"выполнено пакетов извлечения {len(extraction_log)}, "
                        f"разных документов {len(processed)}")
    funnel.extracted_candidates = len(candidates)
    funnel.proposed_candidates = accepted_stats['proposed']
    funnel.duplicate_candidates = accepted_stats['duplicates']

    # In tree mode keep categories intact until the downstream proof filters and
    # guarded semantic merge. Lexical overlap must not silently erase a narrower one.
    merged = candidates if tree is not None else merge_candidates(candidates)
    if tree is not None:
        from .discovery import attach_document_coverage
        attach_document_coverage(tree, docs, hits, docs_for_extraction, candidates)
        (out / "discovery-tree.json").write_text(json.dumps(tree, ensure_ascii=False, indent=2))
    funnel.after_merge = len(merged)

    for err in (getattr(searcher, "errors", []) or [])[:5]:
        funnel.notes.append(f"отказ источника: {err}")
    if getattr(searcher, "free_calls", 0):
        funnel.notes.append(f"бесплатных вызовов источников: {searcher.free_calls}")

    if items:
        suggestions = suggest_matches(merged, reference, area)
        review_path = write_review_file(out / "matches.json", suggestions, area, len(items))
        c_value, matched = compute_c(suggestions)  # pending: C считается после проверки человеком
    else:
        suggestions, c_value = [], 0
        review_path = out / "matches.json"
        review_path.write_text("{}", encoding="utf-8")
    funnel.matched_reference = c_value

    manifest = RunManifest(
        run_id=run_id, area=area or "открытый запрос", query=direction, mode=mode, cutoff=cutoff,
        model=getattr(settings, "model_uri", ""), prompt_version=PROMPT_VERSION,
        reference_sha256=ref_sha, limits=lim.__dict__,
        plan=plan, pool_signature=pool_signature(settings, plan, lenses),
        execution_complete=not stopped and time.monotonic() - started < lim.run_deadline_s,
        counters={**funnel.as_dict(), "input_tokens": in_tok, "output_tokens": out_tok,
                  "search_calls": getattr(searcher, "calls", 0),
                  "free_search_calls": getattr(searcher, "free_calls", 0)},
        cost_rub=round(getattr(searcher, 'spent_rub', 0.0) + getattr(llm, 'spent_rub', 0.0), 4),
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    (out / "manifest.json").write_text(json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    _jsonl(out / "hits.jsonl", hits)
    _jsonl(out / "fetches.jsonl", fetches)
    _jsonl(out / "documents.jsonl", docs)
    _jsonl(out / "candidates.jsonl", merged)
    text = report(area, funnel, c_value, len(items), [])
    text += f"\n\nВремя прогона: {time.monotonic() - started:.1f} с; стоимость ≈ {manifest.cost_rub} ₽."
    if items:
        text += f"\nПодтвердите соответствия в {review_path.name} и запустите «evaluate»."
    (out / "report.txt").write_text(text, encoding="utf-8")
    print(text)
    return out


def run_hypotheses(area: str, direction: str, settings: Settings, count: int = 30,
                   runs_dir: Path = RUNS_DIR) -> Path:
    """Путь гипотез: модель предлагает категории, поиск подтверждает их доказательствами.

    Отдельная команда, а не режим обычного прогона: метрики двух путей нельзя
    смешивать. В отчёте всегда указывается, сколько категорий закрыто гипотезами, а
    сколько обнаружением, потому что первое частично воспроизводит знания модели.
    """
    started = time.monotonic()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + f"-гипотезы-{area.split()[0].lower()}"
    out = runs_dir / run_id
    out.mkdir(parents=True, exist_ok=True)

    if not settings.has_keys:
        raise RuntimeError("для пути гипотез нужны YANDEX_API_KEY и YANDEX_FOLDER_ID")
    reference, ref_sha = load_reference()
    items = area_items(reference, area)
    searcher = MultiSearch(YandexSearch(settings, cache_dir=out / "search"),
                           {"research": OpenAlexSearch()})
    llm = YandexLLM(settings)
    funnel = Funnel()

    raw_log: list[str] = []
    hyps, in_tok, out_tok = generate_hypotheses(direction, llm, count, log=raw_log)
    (out / "generation-raw.txt").write_text("\n\n=== ответ ===\n\n".join(raw_log), encoding="utf-8")
    funnel.notes.append(f"гипотез предложено: {len(hyps)}")
    if not hyps:
        raise RuntimeError("модель не вернула ни одной гипотезы")

    candidates: list[Candidate] = []
    paid_calls = 0
    with Fetcher(settings, raw_dir=out / "raw") as fetcher:
        for hyp in hyps:
            if time.monotonic() - started > settings.limits.run_deadline_s:
                funnel.notes.append("остановлено по дедлайну прогона")
                break
            cand, i_tok, o_tok, paid = verify_hypothesis(hyp, searcher, llm, fetcher)
            in_tok += i_tok
            out_tok += o_tok
            paid_calls += paid
            funnel.queries += paid
            if cand is not None:
                candidates.append(cand)

    funnel.extracted_candidates = len(candidates)
    funnel.after_merge = len(candidates)
    funnel.fetched_ok = funnel.parsed_ok = len(candidates)
    by_status = Counter(h.status for h in hyps)
    funnel.notes.append("итог по гипотезам: " + ", ".join(f"{k} {v}" for k, v in by_status.items()))

    suggestions = suggest_matches(candidates, reference, area)
    review_path = write_review_file(out / "matches.json", suggestions, area, len(items))
    c_value, _ = compute_c(suggestions)
    funnel.matched_reference = c_value

    # Сначала данные, потом манифест: 26.09 прогон за 26 ₽ пропал из-за падения на
    # проверке манифеста, когда всё уже было посчитано.
    _jsonl(out / "hypotheses.jsonl", [h.__dict__ for h in hyps])
    _jsonl(out / "candidates.jsonl", candidates)

    manifest = RunManifest(
        run_id=run_id, area=area, query=direction, mode="hypotheses",
        cutoff=datetime.now(timezone.utc).date().isoformat(),
        model=getattr(settings, "model_uri", ""), prompt_version="hypotheses/0.1",
        reference_sha256=ref_sha, limits=settings.limits.__dict__,
        counters={**funnel.as_dict(), "input_tokens": in_tok, "output_tokens": out_tok,
                  "search_calls": paid_calls,
                  "free_search_calls": getattr(searcher, "free_calls", 0)},
        cost_rub=estimate_cost(settings, paid_calls, in_tok, out_tok),
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    (out / "manifest.json").write_text(json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    text = report(area, funnel, c_value, len(items), [])
    text += (f"\n\nПуть гипотез: предложено {len(hyps)}, подтверждено документом "
             f"{len(candidates)}.\nВремя {time.monotonic() - started:.1f} с, стоимость ≈ "
             f"{manifest.cost_rub} ₽.\nЭто не то же самое, что обнаружение: кандидаты помечены "
             f"origin=hypothesis и считаются отдельно.")
    (out / "report.txt").write_text(text, encoding="utf-8")
    print(text)
    return out


def evaluate_run(run_dir: Path) -> str:
    """Пересчитывает C после ручного подтверждения пар в matches.json."""
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    suggestions = read_review_file(run_dir / "matches.json")
    c_value, matched = compute_c(suggestions)
    errors = check_do_not_merge(suggestions)
    reference, _ = load_reference()
    items = area_items(reference, manifest["area"])
    funnel = Funnel(**{k: v for k, v in manifest["counters"].items() if k in Funnel().__dict__})
    funnel.matched_reference = c_value
    text = report(manifest["area"], funnel, c_value, len(items), errors)
    missing = [i.number for i in items if i.number not in matched]
    text += "\n\nНе найдены: " + (", ".join(f"№{n}" for n in missing) if missing else "нет")
    (run_dir / "report.txt").write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar", description="Пул кандидатов по направлению")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reference", help="выгрузить эталон из таблицы заказчика")

    p_dry = sub.add_parser("dry-run", help="оценить стоимость прогона без сети")
    p_dry.add_argument("--area", required=True)

    p_run = sub.add_parser("run", help="прогон пула кандидатов")
    p_run.add_argument("--area", default="", help="область закрытого эталона, только для оценки покрытия")
    p_run.add_argument("--direction", required=True, help="запрос пользователя, без названий из таблицы")
    p_run.add_argument("--mode", choices=["live", "fixtures"], default="fixtures")
    p_run.add_argument("--max-docs", type=int, default=None)
    p_run.add_argument("--plan", choices=["tree", "mixed", "segments", "pains"], default="tree",
                       help="segments — структура отрасли; pains — её нерешённые проблемы")
    p_run.add_argument("--lenses", default="product,funding,standard,research",
                       help="какие линзы включить; research уходит в OpenAlex")

    p_hyp = sub.add_parser("hypotheses", help="путь гипотез: модель предлагает, поиск проверяет")
    p_hyp.add_argument("--area", required=True)
    p_hyp.add_argument("--direction", required=True)
    p_hyp.add_argument("--count", type=int, default=30)

    p_eval = sub.add_parser("evaluate", help="пересчитать C после ручного подтверждения")
    p_eval.add_argument("--run", required=True)

    args = parser.parse_args(argv)
    load_env_file()  # ключи из hackathon/.env
    settings = Settings()
    if args.cmd == "reference":
        from .reference import export
        print(f"эталон сохранён: {export()}")
    elif args.cmd == "dry-run":
        print(dry_run(args.area, settings))
    elif args.cmd == "run":
        run_pool(args.area, args.direction, args.mode, settings, max_docs=args.max_docs,
                 lenses=tuple(x.strip() for x in args.lenses.split(",") if x.strip()),
                 plan=args.plan)
    elif args.cmd == "hypotheses":
        run_hypotheses(args.area, args.direction, settings, count=args.count)
    elif args.cmd == "evaluate":
        print(evaluate_run(Path(args.run)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
