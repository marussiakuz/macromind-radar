"""Объединение пулов нескольких прогонов одной области.

Зачем. Измерено: один прогон даёт 5–7 эталонных строк из 16–17, а судья по объединению
пяти прогонов — 10 из 16. Планировщик разбросан (на почти одинаковых запросах 16 и 36
запросов), поэтому разные прогоны перекрываются неполно, и объединение прибавляет
механизмы, а не повторы.

Для живого запроса это не путь: заказчик ждёт ответ за 20 минут. Объединение полезно там,
где мы готовим область заранее — для показа и для отчёта о достижимом покрытии.

Повторы убираются по паре (название, адрес источника) и по каноническому английскому
термину, если он есть: две записи об одном механизме не должны занимать два слота.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

HACK = Path(__file__).resolve().parents[1]


def key_of(cand: dict) -> tuple:
    term = (cand.get("name_orig") or "").strip().lower()
    return (term or cand["name_ru"].strip().lower(), cand.get("source_url", ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="каталоги прогонов одной области")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    union: list[dict] = []
    seen: set[tuple] = set()
    per_run: dict[str, int] = {}
    docs: list[str] = []
    for r in args.runs:
        run = Path(r) if Path(r).exists() else HACK / "radar-runs" / r
        rows = [json.loads(l) for l in (run / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
        added = 0
        for c in rows:
            k = key_of(c)
            if k in seen:
                continue
            seen.add(k)
            c = {**c, "_origin_run": run.name}
            union.append(c)
            added += 1
        per_run[run.name] = added
        if (run / "documents.jsonl").exists():
            docs.append((run / "documents.jsonl").read_text(encoding="utf-8"))
        print(f"  {run.name}: {len(rows)} кандидатов, новых {added}")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "candidates.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in union), encoding="utf-8")
    (args.out / "documents.jsonl").write_text("".join(docs), encoding="utf-8")
    base = Path(args.runs[0]) if Path(args.runs[0]).exists() else HACK / "radar-runs" / args.runs[0]
    man = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    man["counters"]["after_merge"] = len(union)
    man["branch"] = "union"
    man["union_of"] = per_run
    man["note"] = ("объединение пулов нескольких прогонов одной области; повторы убраны по "
                   "каноническому термину и адресу источника")
    (args.out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    origins = collections.Counter(c["_origin_run"] for c in union)
    print(f"\nобъединённый пул: {len(union)} кандидатов из {len(args.runs)} прогонов")
    print("  вклад прогонов:", dict(origins))
    print(f"  сохранено: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
