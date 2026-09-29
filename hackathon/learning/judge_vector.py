"""Судья с векторным предотбором: тот же промпт, другой способ выбрать короткий список.

Сравнение с лексическим предотбором идёт на одном и том же пуле. Цель — узнать, сколько
совпадений теряет измеритель, а не улучшить выдачу.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HACK))

from radar.config import Settings, load_env_file                      # noqa: E402
from radar.extract import YandexLLM                                   # noqa: E402
from radar.judge import JUDGE_SYSTEM                                  # noqa: E402
from radar.reference import area_items, load_reference                # noqa: E402
from radar.vectors import candidate_text, rank                        # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--area", default="Финтех")
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args(argv)

    load_env_file()
    llm = YandexLLM(Settings(), max_tokens=700)
    ref, _ = load_reference()
    rows = area_items(ref, args.area)
    pool = [json.loads(l) for l in (args.run / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    texts = [candidate_text(c) for c in pool]
    print(f"пул {len(pool)} кандидатов, строк эталона {len(rows)}; модель считается локально\n")

    found, in_tok, out_tok = [], 0, 0
    for item in rows:
        order = rank(item.name, texts)[: args.top]
        short = [pool[i] for i, _ in order]
        payload = {"эталон": item.name,
                   "кандидаты": [{"index": k, "название": c["name_ru"],
                                  "исходное_название": c.get("name_orig"),
                                  "механизм": (c.get("mechanism") or "")[:220]}
                                 for k, c in enumerate(short)]}
        try:
            text, i_tok, o_tok = llm.complete(JUDGE_SYSTEM, payload)
            in_tok += i_tok or 0
            out_tok += o_tok or 0
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        except (ValueError, KeyError):
            print(f"  №{item.number:>3} ответ не разобран")
            continue
        idx = data.get("match_index")
        if isinstance(idx, int) and 0 <= idx < len(short):
            found.append(item.number)
            print(f"  + №{item.number:>3} {item.name[:44]:44s} <- {short[idx]['name_ru'][:42]} "
                  f"(косинус {order[idx][1]:.3f}, место {idx + 1})")
        else:
            print(f"  - №{item.number:>3} {item.name[:44]:44s} (лучший косинус "
                  f"{order[0][1]:.3f}: {short[0]['name_ru'][:34]})")
    from radar.config import Prices
    p = Prices()
    cost = in_tok / 1e6 * p.llm_input_rub_per_mtok + out_tok / 1e6 * p.llm_output_rub_per_mtok
    print(f"\nвекторный предотбор: {len(found)} из {len(rows)} — {sorted(found)}")
    print(f"стоимость судьи ≈ {cost:.2f} ₽, векторы бесплатны")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
