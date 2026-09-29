"""Почему строка таблицы заказчика не доходит до пула кандидатов.

Вопрос стоит так: из 17 строк «Финтеха» судья находит в пуле 5, изредка 9. Остальные —
это ошибка фильтра, ошибка извлечения, ошибка отбора ссылок или их вообще никто не искал?

Здесь строка ищется по всему сохранённому корпусу и определяется самая глубокая стадия,
до которой она дошла:

  candidate — её механизм есть среди извлечённых кандидатов (значит дошла, дальше вопрос
              к фильтру и к судье);
  document  — слова строки есть в тексте скачанного документа, но кандидата из него не
              извлекли (ошибка извлечения);
  hit       — слова есть в заголовке или сниппете поисковой выдачи, но страницу не
              качали (ошибка отбора ссылок);
  nowhere   — ни в одном запросе ничего похожего не нашлось (ошибка плана: мы об этом
              не спрашивали).

Платных вызовов нет: читаются только сохранённые прогоны.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HACK = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(HACK))

from radar.reference import area_items, load_reference          # noqa: E402

STOP = {"для", "или", "как", "при", "без", "над", "под", "из", "и", "в", "на", "с", "по",
        "не", "от", "до", "за", "the", "and", "for", "with", "of", "to", "in", "on"}


def keys_of(name: str) -> tuple[set[str], set[str]]:
    """Ключи строки: латинские токены (аббревиатуры, протоколы) и значимые русские слова.

    Латинские ключи сильнее: «x402», «AP2», «KYA», «PBM», «core banking OS» — это то, как
    технологию называют авторы, и именно они дают точное совпадение по корпусу.
    """
    latin = {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9./-]{1,}", name)
             if len(t) > 1 and t.lower() not in STOP}
    rus = {w.lower()[:7] for w in re.findall(r"[А-Яа-яёЁ]{5,}", name) if w.lower() not in STOP}
    return latin, rus


def hits_for(text: str, latin: set[str], rus: set[str]) -> tuple[int, int]:
    low = (text or "").lower()
    return (sum(1 for k in latin if k in low), sum(1 for k in rus if k in low))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", default="Финтех")
    ap.add_argument("--slug", default="финтех", help="часть имени прогонов области")
    args = ap.parse_args(argv)

    ref, _ = load_reference()
    rows = area_items(ref, args.area)
    runs = [d for d in sorted((HACK / "radar-runs").glob("2026*"))
            if args.slug in d.name and (d / "candidates.jsonl").exists()]
    print(f"строк эталона: {len(rows)}; прогонов области: {len(runs)}")

    cands, docs, hits = [], [], []
    for run in runs:
        for line in (run / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            quotes = " ".join((e.get("quote") or "") for e in (c.get("evidence") or []))
            cands.append((run.name, c.get("name_ru", "") + " " + (c.get("name_orig") or "")
                          + " " + (c.get("mechanism") or "") + " " + quotes))
        if (run / "documents.jsonl").exists():
            for line in (run / "documents.jsonl").read_text(encoding="utf-8").splitlines():
                d = json.loads(line)
                docs.append((run.name, d.get("url", ""), (d.get("title") or "") + " " + (d.get("text") or "")))
        if (run / "hits.jsonl").exists():
            for line in (run / "hits.jsonl").read_text(encoding="utf-8").splitlines():
                h = json.loads(line)
                hits.append((run.name, h.get("url", ""), h.get("query", ""),
                             (h.get("title") or "") + " " + (h.get("snippet") or "")))
    fetched = {u for _, u, _ in docs}
    print(f"корпус: кандидатов {len(cands)}, документов {len(docs)}, позиций выдачи {len(hits)}\n")

    verdict = {}
    for item in rows:
        latin, rus = keys_of(item.name)
        need_latin = 1 if latin else 0
        need_rus = 2 if len(rus) > 2 else max(1, len(rus))

        def ok(text: str) -> bool:
            nl, nr = hits_for(text, latin, rus)
            return (nl >= need_latin and need_latin > 0) or nr >= need_rus

        in_cand = [r for r, t in cands if ok(t)]
        in_doc = [(r, u) for r, u, t in docs if ok(t)]
        in_hit = [(r, u, q) for r, u, q, t in
                  [(a, b, c, d) for a, b, c, d in hits] if ok(t)]
        if in_cand:
            stage, detail = "candidate", f"{len(in_cand)} кандидатов"
        elif in_doc:
            stage, detail = "document", f"{len(in_doc)} документов, напр. {in_doc[0][1][:52]}"
        elif in_hit:
            unfetched = [x for x in in_hit if x[1] not in fetched]
            stage = "hit"
            detail = (f"{len(in_hit)} позиций выдачи, из них не качали {len(unfetched)}; "
                      f"запрос: «{in_hit[0][2][:60]}»")
        else:
            stage, detail = "nowhere", f"ключи: {sorted(latin)[:3] or sorted(rus)[:3]}"
        verdict[item.number] = (stage, item.name, detail)

    order = {"candidate": 0, "document": 1, "hit": 2, "nowhere": 3}
    for num, (stage, name, detail) in sorted(verdict.items(), key=lambda kv: (order[kv[1][0]], kv[0])):
        mark = {"candidate": "дошла до кандидатов", "document": "была в документе",
                "hit": "была только в выдаче", "nowhere": "не искали вовсе"}[stage]
        print(f"№{num:>3}  {mark:22s} {name[:58]}")
        print(f"      {detail}")
    counts = {}
    for stage, _, _ in verdict.values():
        counts[stage] = counts.get(stage, 0) + 1
    print("\nитого:", {k: counts.get(k, 0) for k in ("candidate", "document", "hit", "nowhere")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
