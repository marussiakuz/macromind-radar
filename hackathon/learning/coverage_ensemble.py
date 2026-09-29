"""Полнота покрытия эталона ансамблем сопоставителей.

Измерено 29.09.2026: один способ сопоставления видит 8–9 строк из 17, и разные способы
видят разные строки. Лексический предотбор нашёл №41 и №93, векторный — №71, адресная
проверка по ключам строки — №42 и №65. Объединение трёх видит больше любого одного,
поэтому «сколько строк в пуле» считается ансамблем, а не одним прибором.

Это измеритель, а не улучшение выдачи: он говорит, что в пуле есть, а не что попало в
карточки. Векторы считаются локально и бесплатно.
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
from radar.evaluate import name_similarity                            # noqa: E402
from radar.extract import YandexLLM                                   # noqa: E402
from radar.judge import JUDGE_SYSTEM                                  # noqa: E402
from radar.reference import area_items, load_reference, normalize_tokens  # noqa: E402
from radar.vectors import candidate_text, rank                        # noqa: E402

STOP = {"для", "или", "как", "при", "the", "and", "for", "with", "of", "to", "in", "on",
        "os", "ai"}


def key_shortlist(item, pool: list[dict], size: int) -> list[int]:
    latin = {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9./-]{2,}", item.name)
             if t.lower() not in STOP}
    rus = {w.lower()[:7] for w in re.findall(r"[А-Яа-яёЁ]{6,}", item.name)}
    scored = []
    for i, c in enumerate(pool):
        blob = json.dumps(c, ensure_ascii=False).lower()
        score = sum(2 for k in latin if k in blob) + sum(1 for k in rus if k in blob)
        if score:
            scored.append((score, i))
    scored.sort(reverse=True)
    return [i for _, i in scored[:size]]


def lexical_shortlist(item, pool: list[dict], size: int) -> list[int]:
    scored = []
    for i, c in enumerate(pool):
        text = f"{c['name_ru']} {c.get('name_orig') or ''} {c.get('mechanism') or ''}"
        scored.append((name_similarity(normalize_tokens(text), item.tokens), i))
    scored.sort(reverse=True)
    return [i for _, i in scored[:size]]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", default="Финтех")
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--size", type=int, default=10, help="кандидатов на способ")
    args = ap.parse_args(argv)

    load_env_file()
    llm = YandexLLM(Settings(), max_tokens=700)
    ref, _ = load_reference()
    rows = area_items(ref, args.area)
    pool = [json.loads(l) for l in (args.run / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    texts = [candidate_text(c) for c in pool]
    print(f"пул {len(pool)}; строк эталона {len(rows)}; по {args.size} кандидатов на способ\n")

    found, in_tok, out_tok = {}, 0, 0
    for item in rows:
        idxs: list[int] = []
        for src in (lexical_shortlist(item, pool, args.size),
                    [i for i, _ in rank(item.name, texts)[: args.size]],
                    key_shortlist(item, pool, args.size)):
            for i in src:
                if i not in idxs:
                    idxs.append(i)
        short = [pool[i] for i in idxs]
        payload = {"эталон": item.name,
                   "кандидаты": [{"index": k, "название": c["name_ru"],
                                  "исходное_название": c.get("name_orig"),
                                  "механизм": (c.get("mechanism") or "")[:200]}
                                 for k, c in enumerate(short)]}
        try:
            text, i_t, o_t = llm.complete(JUDGE_SYSTEM, payload)
            in_tok += i_t or 0
            out_tok += o_t or 0
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        except (ValueError, KeyError):
            print(f"  ?  №{item.number:>3} ответ не разобран")
            continue
        idx = data.get("match_index")
        if isinstance(idx, int) and 0 <= idx < len(short):
            found[item.number] = short[idx]["name_ru"]
            print(f"  +  №{item.number:>3} {item.name[:42]:42s} <- {short[idx]['name_ru'][:40]}")
        else:
            print(f"  -  №{item.number:>3} {item.name[:42]:42s} (показано {len(short)})")
    from radar.config import Prices
    p = Prices()
    cost = in_tok / 1e6 * p.llm_input_rub_per_mtok + out_tok / 1e6 * p.llm_output_rub_per_mtok
    print(f"\nансамблем найдено: {len(found)} из {len(rows)} — {sorted(found)}")
    print(f"не найдено: {sorted(i.number for i in rows if i.number not in found)}")
    print(f"стоимость ≈ {cost:.2f} ₽ (векторы бесплатны)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
