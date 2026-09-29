"""Адресная проверка: почему строка эталона не совпала у судьи.

Судья ранжирует кандидатов по похожести названий и показывает верхние N. Если строка
называется иначе, чем наш кандидат, правильный кандидат в эти N не попадает — и отсутствие
совпадения означает «не нашёл», а не «нет в пуле».

Здесь короткий список формируется **по ключам самой строки** (латинские токены и значимые
русские корни), а не по похожести названий, и показывается судье с тем же промптом.
Так отделяется «в пуле нет» от «предотбор не донёс».
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HACK))

from radar.config import Settings, load_env_file                      # noqa: E402
from radar.extract import YandexLLM                                   # noqa: E402
from radar.judge import JUDGE_SYSTEM                                  # noqa: E402
from radar.reference import area_items, load_reference                # noqa: E402

STOP = {"для", "или", "как", "при", "без", "над", "под", "из", "и", "в", "на", "с", "по",
        "не", "от", "до", "за", "the", "and", "for", "with", "of", "to", "in", "on", "os", "ai"}


def keys_of(name: str) -> tuple[set[str], set[str]]:
    latin = {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9./-]{2,}", name)
             if t.lower() not in STOP}
    rus = {w.lower()[:7] for w in re.findall(r"[А-Яа-яёЁ]{6,}", name) if w.lower() not in STOP}
    return latin, rus


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", default="Финтех")
    ap.add_argument("--pool", type=Path, default=HACK / "bench/union-all-финтех")
    ap.add_argument("--numbers", required=True, help="номера строк через запятую")
    ap.add_argument("--show", type=int, default=12)
    args = ap.parse_args(argv)

    load_env_file()
    llm = YandexLLM(Settings(), max_tokens=700)
    ref, _ = load_reference()
    wanted = {int(n) for n in args.numbers.split(",")}
    rows = [i for i in area_items(ref, args.area) if i.number in wanted]
    pool = [json.loads(l) for l in (args.pool / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    print(f"пул {len(pool)} кандидатов; проверяю строк: {len(rows)}\n")

    found = 0
    for item in rows:
        latin, rus = keys_of(item.name)
        scored = []
        for c in pool:
            blob = " ".join([c.get("name_ru", ""), c.get("name_orig") or "",
                             c.get("mechanism") or "",
                             " ".join((e.get("quote") or "") for e in (c.get("evidence") or []))]).lower()
            score = sum(2 for k in latin if k in blob) + sum(1 for k in rus if k in blob)
            if score:
                scored.append((score, c))
        scored.sort(key=lambda t: -t[0])
        short = [c for _, c in scored[: args.show]]
        if not short:
            print(f"№{item.number:>3} {item.name[:56]}")
            print(f"      в пуле нет ни одного кандидата с ключами {sorted(latin)[:4] or sorted(rus)[:4]}\n")
            continue
        payload = {"эталон": item.name,
                   "кандидаты": [{"index": i, "название": c["name_ru"],
                                  "исходное_название": c.get("name_orig"),
                                  "механизм": (c.get("mechanism") or "")[:220]}
                                 for i, c in enumerate(short)]}
        try:
            text, _, _ = llm.complete(JUDGE_SYSTEM, payload)
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        except (ValueError, KeyError) as exc:
            print(f"№{item.number:>3} разбор ответа не удался: {type(exc).__name__}\n")
            continue
        idx = data.get("match_index")
        print(f"№{item.number:>3} {item.name[:56]}")
        print(f"      кандидатов по ключам: {len(scored)}, показано {len(short)}")
        if isinstance(idx, int) and 0 <= idx < len(short):
            found += 1
            print(f"      СОВПАЛО: {short[idx]['name_ru'][:64]}")
            print(f"      почему: {str(data.get('why'))[:120]}")
        else:
            print(f"      не совпало. Судья: {str(data.get('why'))[:150]}")
            print(f"      ближайший по ключам: {short[0]['name_ru'][:60]}")
        print()
    print(f"итого адресной проверкой найдено совпадений: {found} из {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
