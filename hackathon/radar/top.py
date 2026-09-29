"""Построение ранжированного списка из сохранённого пула кандидатов."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import Settings, load_env_file
from .corroborate import canonical_terms, cluster_by_term
from .extract import YandexLLM
from .rank import (SCORE_WITHOUT_TERM, HackerNewsProbe, MaturityProbe, OpenAlexProbe,
                   score_candidate)
from .reference import normalize_tokens


def load_pool(paths: list[Path]) -> list[dict]:
    """Одинаковые имена сливаются, но наблюдения не выбрасываются.

     прежняя версия оставляла первую запись и отбрасывала остальные,
    то есть теряла второй источник и второго игрока раньше, чем по ним считается
    независимость. Теперь повторы объединяются: цитаты, организации и документы копятся.
    """
    seen: dict[str, dict] = {}
    for path in paths:
        f = path / "candidates.jsonl"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            key = " ".join(sorted(normalize_tokens(c["name_ru"])))
            if not key:
                continue
            if key not in seen:
                seen[key] = {**c, "merged_sources": list(c.get("merged_sources") or [])}
                continue
            first = seen[key]
            quotes = {e.get("quote") for e in first.get("evidence") or []}
            for ev in c.get("evidence") or []:
                if ev.get("quote") not in quotes:
                    first.setdefault("evidence", []).append(ev)
            for org in c.get("organizations") or []:
                if org not in (first.get("organizations") or []):
                    first.setdefault("organizations", []).append(org)
            if c.get("source_url") and c["source_url"] != first.get("source_url"):
                if c["source_url"] not in first["merged_sources"]:
                    first["merged_sources"].append(c["source_url"])
            if not first.get("name_orig") and c.get("name_orig"):
                first["name_orig"] = c["name_orig"]
    return list(seen.values())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="radar.top")
    ap.add_argument("--run", action="append", required=True, help="каталог прогона, можно несколько")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--min-score", type=float, default=5.0)
    args = ap.parse_args(argv)

    pool = load_pool([Path(r) for r in args.run])
    print(f"пул: {len(pool)} кандидатов")

    # Канонический термин берётся из цитаты автора, а не из нашего пересказа: по нашему
    # русскому имени англоязычные индексы не находят ничего, и это ошибка измерения.
    load_env_file()
    llm = YandexLLM(Settings(), max_tokens=1200)
    terms = canonical_terms(pool, llm)
    named = sum(1 for t in terms.values() if t)
    clusters = cluster_by_term(pool, terms)
    print(f"термин извлечён у {named} из {len(pool)}; разных терминов: {len(clusters)}")

    # Независимые игроки считаются по пулу: один механизм, описанный в документах с
    # разных доменов разными компаниями, и есть конвергенция.
    players_of: dict[int, int] = {}
    sources_of: dict[int, int] = {}
    for cl in clusters:
        for cand in cl.candidates:
            players_of[id(cand)] = cl.players
            sources_of[id(cand)] = cl.independent_sources

    # Те же источники и тот же порядок, что в сервисе: иначе одна и та же запись
    # получает разные решения в зависимости от способа запуска.
    probe = MaturityProbe([OpenAlexProbe(), HackerNewsProbe()])
    scored = []
    for i, c in enumerate(pool):
        term = terms.get(i)
        if not term and not SCORE_WITHOUT_TERM:
            continue
        # Та же правка, что в server.build_cards: отсутствие термина — это отсутствие
        # прибора, а не свойство технологии, и по измерению 27.09.2026 он отсутствовал
        # именно у эталонных кандидатов чаще, чем у прочих (10 % против 42 % на «Финтехе»).
        c = {**c, "name_orig": term or ""}
        sig = score_candidate(c, probe, players=players_of.get(id(pool[i]), 0))
        if sources_of.get(id(pool[i]), 0) >= 2:
            sig.score += 1.5
            sig.notes.append(f"подтверждено с {sources_of[id(pool[i])]} разных доменов")
        scored.append((sig, c))
    probe.close()
    passed = [x for x in scored if x[0].score >= args.min_score]
    rejected = [x for x in scored if x[0].score < args.min_score]
    passed.sort(key=lambda x: -x[0].score)
    print(f"вызовов к Hacker News: {probe.calls} (бесплатно)")
    print(f"прошло окно зрелости: {len(passed)}, отбраковано: {len(rejected)}\n")

    out = []
    for i, (sig, c) in enumerate(passed[: args.top], 1):
        print(f"{i:2d}. {c['name_ru'][:70]}   [{sig.score}]")
        print(f"    механизм: {c['mechanism'][:110]}")
        print(f"    признаки: {'; '.join(sig.notes[:4])}")
        ev = (c.get("evidence") or [{}])[0]
        print(f"    цитата:   {(ev.get('quote') or '')[:100]}")
        print(f"    источник: {c.get('source_url','')[:80]}\n")
        out.append({"rank": i, "name_ru": c["name_ru"], "name_en": c.get("name_orig"),
                    "mechanism": c["mechanism"], "score": sig.score,
                    "signals": {"первое упоминание": sig.first_seen, "возраст_мес": sig.age_months,
                                "упоминаний всего": sig.total, "за 12 месяцев": sig.recent,
                                "игроков": sig.players, "стадия": sig.stage},
                    "why": sig.notes, "evidence": c.get("evidence"),
                    "source_url": c.get("source_url"), "origin": c.get("origin", "discovery")})

    reasons: dict[str, int] = {}
    for sig, _ in rejected:
        reasons[sig.verdict or "низкий балл"] = reasons.get(sig.verdict or "низкий балл", 0) + 1
    print("отбраковано по причинам:")
    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {v:3d}  {k}")

    dest = Path(args.run[0]) / "top.json"
    dest.write_text(json.dumps({"top": out, "rejected_reasons": reasons,
                                "pool_size": len(pool)}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"\nсохранено: {dest}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
