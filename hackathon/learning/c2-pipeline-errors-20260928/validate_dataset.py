"""Проверки набора C2. Платных вызовов не делает, читает только локальные файлы.

Запуск из каталога набора:
    ../../.venv/bin/python validate_dataset.py
"""
from __future__ import annotations

import collections
import json
import statistics
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE.parents[1] / "radar-runs"
# Слова-подсказки, которых не должно быть в модельном входе: ни метки, ни оценки класса.
FORBIDDEN = ("слабый сигнал", "зарождающ", "зрелая технология", "перспективн", "weak signal",
             "mature", "ai_draft", "proposed", "reason_code", "балл", "score")


def load_doc_texts(run: str) -> dict[str, str]:
    out: dict[str, str] = {}
    path = RUNS / run / "documents.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        for key in (d.get("final_url"), d.get("url")):
            if key:
                out.setdefault(key, d.get("text") or "")
    return out


def main() -> int:
    records = json.loads((HERE / "dataset.json").read_text(encoding="utf-8"))
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    cutoff = date.fromisoformat(manifest["cutoff"])
    problems: list[str] = []
    checks: dict[str, str] = {}

    ids = [r["sample_id"] for r in records]
    checks["1. идентификаторы уникальны"] = "ок" if len(set(ids)) == len(ids) else "ПРОВАЛ"
    if len(set(ids)) != len(ids):
        problems.append("повторяющиеся sample_id")

    bad_refs = 0
    for r in records:
        srcs = {s["source_id"] for s in r["sources"]}
        evs = {e["evidence_id"] for e in r["model_input"]["evidence"]}
        for e in r["model_input"]["evidence"]:
            if e["source_id"] not in srcs:
                bad_refs += 1
        for c in r["model_input"]["claims"]:
            if not set(c["evidence_ids"]) <= evs:
                bad_refs += 1
    checks["2. ссылки claim→evidence→source разрешаются"] = "ок" if not bad_refs else f"ПРОВАЛ ({bad_refs})"

    quote_ok = quote_bad = no_snapshot = 0
    texts: dict[str, dict[str, str]] = {}
    for r in records:
        run = r["provenance"]["original_run_id"]
        texts.setdefault(run, load_doc_texts(run))
        for s in r["sources"]:
            q = s["quotes"][0]
            text = texts[run].get(s["url"], "")
            if not text:
                no_snapshot += 1
                continue
            if text[q["start_offset"]:q["end_offset"]] == q["text"]:
                quote_ok += 1
            else:
                quote_bad += 1
                problems.append(f"цитата не совпала по смещениям: {r['sample_id']}")
    checks["3. цитаты совпадают со снимком по смещениям"] = (
        f"ок ({quote_ok})" if not quote_bad else f"ПРОВАЛ ({quote_bad} из {quote_ok + quote_bad})")
    if no_snapshot:
        checks["3a. записи без доступного снимка"] = str(no_snapshot)

    late = invented = 0
    for r in records:
        for s in r["sources"]:
            pub = s.get("publication_date")
            if pub:
                try:
                    if date.fromisoformat(pub) > cutoff:
                        late += 1
                except ValueError:
                    invented += 1
    checks["4. даты источников не позже среза"] = "ок" if not late else f"ПРОВАЛ ({late})"
    checks["5. даты в формате ISO или отсутствуют"] = "ок" if not invented else f"ПРОВАЛ ({invented})"

    # Проверяем только те поля, которые сочиняем мы. Дословную цитату и её контекст
    # проверять этим правилом нельзя: слова источника менять запрещено, а «has matured»
    # в тексте статьи — это свидетельство, а не наша подсказка класса. Первая версия
    # правила дала здесь ложное срабатывание.
    leaks = 0
    source_words = 0
    for r in records:
        mi = r["model_input"]
        composed = " ".join(str(mi.get(k) or "") for k in
                            ("category_ru", "category_en", "mechanism", "application",
                             "neutral_summary")).lower()
        composed += " " + " ".join(c["text"].lower() for c in mi["claims"])
        for word in FORBIDDEN:
            if word in composed:
                leaks += 1
                problems.append(f"подсказка «{word}» в наших полях {r['sample_id']}")
        verbatim = " ".join((e.get("excerpt") or "") + " " + (e.get("context") or "")
                            for e in mi["evidence"]).lower()
        if any(w in verbatim for w in ("mature", "matured", "зрел")):
            source_words += 1
    checks["6. в наших полях модельного входа нет меток и оценок класса"] = (
        "ок" if not leaks else f"ПРОВАЛ ({leaks})")
    checks["6a. источник сам употребляет слово зрелости (не дефект, но короткий путь)"] = (
        f"{source_words} записей")

    human = sum(1 for r in records if r["annotations"]["status"] != "ai_draft"
                or not r["annotations"]["human_review_required"])
    stages = {r["annotations"]["stage_label"] for r in records}
    checks["7. человеческих меток нет, стадия не назначена"] = (
        "ок" if not human and stages == {"unknown"} else f"ПРОВАЛ ({human}, стадии {stages})")

    orig = sum(1 for r in records if not (r["provenance"]["original_claim"] or "").strip())
    synth = sum(1 for r in records if r["provenance"]["synthetic"])
    used = sum(1 for r in records if r["provenance"]["previously_used"] is not True)
    checks["8. исходная формулировка сохранена дословно"] = "ок" if not orig else f"ПРОВАЛ ({orig})"
    checks["9. синтетических записей нет"] = "ок" if not synth else f"ПРОВАЛ ({synth})"
    checks["10. история использования отмечена"] = "ок" if not used else f"ПРОВАЛ ({used})"

    by_type = collections.Counter(r["annotations"]["proposed_error_type"] for r in records)
    lens = collections.defaultdict(list)
    for r in records:
        lens[r["annotations"]["proposed_error_type"]].append(
            len(r["model_input"]["neutral_summary"].split()))
    print("=== проверки ===")
    for name, value in checks.items():
        print(f"  {value:<22} {name}")
    print("\n=== распределения (проверка №9 задания: обходные признаки) ===")
    for kind, n in by_type.most_common():
        vals = lens[kind]
        print(f"  {n:2d}  {kind:36s} слов в нейтральном тексте: "
              f"медиана {statistics.median(vals):.0f}, от {min(vals)} до {max(vals)}")
    all_lens = [v for vals in lens.values() for v in vals]
    spread = max(statistics.median(lens[k]) for k in lens) - min(statistics.median(lens[k]) for k in lens)
    print(f"  разница медиан длины между типами: {spread:.0f} слов "
          f"(при общей медиане {statistics.median(all_lens):.0f}) — "
          f"{'заметная, помечаю как возможный обходной признак' if spread > 25 else 'умеренная'}")
    print("\n=== области и прогоны ===")
    for area, n in collections.Counter(r["model_input"]["area"] for r in records).most_common():
        print(f"  {n:2d}  {area}")
    for run, n in collections.Counter(r["provenance"]["original_run_id"] for r in records).most_common():
        print(f"  {n:2d}  {run}")
    if problems:
        print("\n=== проблемы ===")
        for p in problems[:20]:
            print("  -", p)
    print(f"\nзаписей: {len(records)}; провалов проверок: "
          f"{sum(1 for v in checks.values() if 'ПРОВАЛ' in v)}")
    return 1 if any("ПРОВАЛ" in v for v in checks.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
