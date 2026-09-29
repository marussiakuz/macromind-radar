"""Сопоставление найденных кандидатов с закрытым эталоном.

Модель предлагает соответствия; итоговая оценка требует ручной проверки."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import RUNS_DIR, Settings, load_env_file
from .evaluate import name_similarity
from .extract import YandexLLM
from .pipeline import estimate_cost
from .reference import area_items, load_reference, normalize_tokens

JUDGE_SYSTEM = """Ты сверяешь кандидатов с эталонной категорией заказчика.

Совпадение засчитывается, только если у кандидата тот же технический механизм и
тот же объект применения, что у эталона. Уточняющие слова эталона необязательны:
«водяные знаки для текста LLM» и «водяные знаки для моделей» — одно и то же.

Не совпадение: кандидат называет продукт или компанию вместо категории; кандидат
описывает более широкую область целиком; кандидат описывает отдельный приём
внутри другой категории; совпадает только общая тема или общее слово.

Верни только JSON: {"match_index": <номер кандидата или null>, "why": "<одна фраза>"}.
При сомнении верни null."""


def load_run(run_dir: Path) -> list[dict]:
    """Кандидаты одного прогона: нужно, чтобы мерить вклад источника изолированно."""
    rows = []
    for line in (run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row["run_id"] = run_dir.name
        rows.append(row)
    return rows


def load_pool(area_slug: str) -> list[dict]:
    """Кандидаты живых прогонов области без точных повторов по набору слов названия.

    Прогоны на фикстурах исключены: фикстуры написаны по таблице заказчика, их
    названия совпадают с эталоном дословно и завышают любую оценку покрытия.
    Проверено 26.09.2026: судья засчитал по ним две категории из фикстур.
    """
    seen: dict[str, dict] = {}
    for run in sorted(RUNS_DIR.glob(f"2026*-{area_slug}")):
        path, manifest = run / "candidates.jsonl", run / "manifest.json"
        if not path.exists() or not manifest.exists():
            continue
        if json.loads(manifest.read_text(encoding="utf-8")).get("mode") != "live":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            row["run_id"] = run.name
            key = " ".join(sorted(normalize_tokens(row["name_ru"])))
            seen.setdefault(key, row)
    return list(seen.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar.judge", description="Оценка сверху по пулу прогонов")
    parser.add_argument("--area", default="Защита ИИ")
    parser.add_argument("--top", type=int, default=5, help="сколько кандидатов показывать судье")
    parser.add_argument("--numbers", default="", help="проверить только эти номера эталона, через запятую")
    parser.add_argument("--run", default="", help="только этот прогон вместо общего пула")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)

    load_env_file()
    settings = Settings()
    reference, _ = load_reference()
    items = area_items(reference, args.area)
    if args.numbers:
        keep = {int(x) for x in args.numbers.replace(" ", "").split(",") if x}
        items = [i for i in items if i.number in keep]
    pool = (load_run(Path(args.run)) if args.run
            else load_pool(args.area.split()[0].lower()))
    source = f"прогона {Path(args.run).name}" if args.run else "всех прогонов"
    print(f"Пул: {len(pool)} кандидатов из {source}; эталон: {len(items)} категорий")
    if not pool:
        print("Пул пуст: сначала нужен хотя бы один прогон области.")
        return 1
    if not args.confirm:
        print(f"Судья сделает {len(items)} вызовов модели, примерно 3 ₽. Запустите с --confirm.")
        return 0

    llm = YandexLLM(settings, max_tokens=200)
    found, in_tok, out_tok, rows = 0, 0, 0, []
    for item in items:
        ranked = sorted(
            pool,
            # Русское имя, исходное английское и имя с механизмом: эталон бывает
            # написан по-английски, и без name_orig «Data unlearning» терялся.
            key=lambda c: max(
                name_similarity(normalize_tokens(c["name_ru"]), item.tokens),
                name_similarity(normalize_tokens(c.get("name_orig") or ""), item.tokens),
                0.99 * name_similarity(
                    normalize_tokens(f"{c['name_ru']} {c.get('name_orig') or ''} {c['mechanism']}"),
                    item.tokens),
            ),
            reverse=True,
        )
        top = ranked[: args.top]
        payload = {
            "эталон": item.name,
            "кандидаты": [
                {"index": i, "название": c["name_ru"], "исходное_название": c.get("name_orig"),
                 "механизм": c["mechanism"][:250], "объект": c.get("object_affected")}
                for i, c in enumerate(top)
            ],
        }
        try:
            text, i_tok, o_tok = llm.complete(JUDGE_SYSTEM, payload)
            in_tok += i_tok
            out_tok += o_tok
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
            idx = data.get("match_index")
            why = str(data.get("why", ""))[:200]
        except (RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            idx, why = None, f"судья не ответил: {exc}"
        if isinstance(idx, int) and 0 <= idx < len(top):
            found += 1
            rows.append({"number": item.number, "reference": item.name,
                         "candidate": top[idx]["name_ru"], "source": top[idx].get("source_url"),
                         "run_id": top[idx].get("run_id"),
                         "why": why, "status": "pending"})
            print(f"  + №{item.number:3d} {item.name[:44]:44s} <- {top[idx]['name_ru'][:44]}")
        else:
            rows.append({"number": item.number, "reference": item.name, "candidate": None, "why": why})
            print(f"  - №{item.number:3d} {item.name[:44]:44s}")

    cost = estimate_cost(settings, 0, in_tok, out_tok)
    suffix = f"-top{args.top}" if args.numbers else ""
    suffix += f"-{Path(args.run).name}" if args.run else ""
    out = RUNS_DIR / f"judge-{args.area.split()[0].lower()}{suffix}.json"
    out.write_text(json.dumps(
        {"area": args.area, "pool_size": len(pool), "upper_bound": found, "total": len(items),
         "tokens": {"input": in_tok, "output": out_tok}, "cost_rub": cost,
         "note": "оценка сверху, пары помечены pending: засчитывает человек", "rows": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nОценка сверху: {found} из {len(items)} (C по подтверждённым парам = 2).")
    print(f"Токены: {in_tok} вход / {out_tok} выход, стоимость ≈ {cost} ₽. Детали: {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
