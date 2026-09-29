"""Опыт с реранкером слабости сигнала: парная модель против текущего прозрачного балла.

Что здесь честно, а что нет.

**Метки** — приговоры агента-аналитика по рубрике 0–3, `label_source=agent_review`.
Человеческих подтверждений ноль. Поэтому это `silver_experimental`: диагностика, не
проверенная модель, и в продукт она подключается только при измеренном выигрыше.

**Размер** — 23 позиции, из них 16 с оценкой 0. Пары зависимы; простой интервал
биномиальной точности здесь не является доказательством выигрыша.

**Признаки** — только числовые, доступные сервису. Текст исключён намеренно: по аудиту
датасета «300» происхождение набора угадывается по стилю в 64–71 случае из 87.

**Сравнение** — с текущим баллом окна зрелости. Балл в признаки обучения не входит: иначе
модель просто воспроизведёт его и «выигрыш» будет тавтологией.

Проверка честности: та же модель прогоняется на перемешанных метках. Если она и там
показывает выигрыш, нужен повторный разбор процедуры; один контроль утечку не доказывает.
"""
from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

HACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HACK))

DATA = HACK / "learning/rank-dataset-20260929.json"
EXCLUDE = {"балл"}                       # текущий балл — эталон сравнения, не признак


def load() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def pairs_of(rows: list[dict]) -> list[tuple[dict, dict]]:
    """Пары внутри области с разной оценкой: порядок между областями не определён."""
    out = []
    for area in {r["area"] for r in rows}:
        items = [r for r in rows if r["area"] == area]
        for a, b in itertools.combinations(items, 2):
            if a["grade"] != b["grade"]:
                out.append((a, b) if a["grade"] > b["grade"] else (b, a))
    return out


def vectorize(rows: list[dict]) -> tuple[list[str], list[list[float]]]:
    names = [k for k in sorted(rows[0]["features"]) if k not in EXCLUDE]
    return names, [[r["features"][k] for k in names] for r in rows]


def pairwise_accuracy(score_of, rows: list[dict]) -> tuple[float, int]:
    good = 0
    prs = pairs_of(rows)
    for better, worse in prs:
        if score_of(better) > score_of(worse):
            good += 1
        elif score_of(better) == score_of(worse):
            good += 0.5
    return (good / len(prs) if prs else 0.0), len(prs)


def ndcg(score_of, rows: list[dict], k: int = 15) -> float:
    import math
    out = []
    for area in {r["area"] for r in rows}:
        items = [r for r in rows if r["area"] == area]
        order = sorted(items, key=lambda r: -score_of(r))[:k]
        gain = sum((2 ** r["grade"] - 1) / math.log2(i + 2) for i, r in enumerate(order))
        ideal_order = sorted(items, key=lambda r: -r["grade"])[:k]
        ideal = sum((2 ** r["grade"] - 1) / math.log2(i + 2) for i, r in enumerate(ideal_order))
        out.append(gain / ideal if ideal else 0.0)
    return sum(out) / len(out) if out else 0.0


def train_pairwise(rows: list[dict], seed: int = 42):
    """Парная логистическая модель: разность признаков → кто выше."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    names, matrix = vectorize(rows)
    index = {id(r): i for i, r in enumerate(rows)}
    X, y = [], []
    for better, worse in pairs_of(rows):
        diff = np.array(matrix[index[id(better)]]) - np.array(matrix[index[id(worse)]])
        X.append(diff); y.append(1)
        X.append(-diff); y.append(0)
    if len(set(y)) < 2 or not X:
        return None, names
    scaler = np.abs(np.array(X)).max(axis=0)
    scaler[scaler == 0] = 1.0
    model = LogisticRegression(max_iter=2000, C=0.5, random_state=seed)
    model.fit(np.array(X) / scaler, y)
    return (model, scaler), names


def scorer(fitted, names):
    import numpy as np
    model, scaler = fitted
    def score(row: dict) -> float:
        vec = np.array([row["features"][k] for k in names]) / scaler
        return float(model.decision_function([vec])[0])
    return score


def grouped_kfold(rows: list[dict], folds: int = 3, seed: int = 42) -> tuple[float, int]:
    """Честная оценка: пары считаются **только внутри отложенной части**.

    Первая версия сравнивала отложенную запись с обучающими, и контроль на перемешанных
    метках давал 0,746 вместо примерно 0,5 — модель выигрывала пары, запомнив положение
    обучающих записей, а не научившись порядку. Это была утечка в процедуре оценки, и её
    видно только по такому контролю.
    """
    families = sorted({r["family"] for r in rows})
    rng = random.Random(seed)
    rng.shuffle(families)
    buckets = [families[i::folds] for i in range(folds)]
    hits = total = 0
    for held in buckets:
        test = [r for r in rows if r["family"] in held]
        train = [r for r in rows if r["family"] not in held]
        if len(train) < 8 or len(test) < 2:
            continue
        fitted, names = train_pairwise(train)
        if fitted is None:
            continue
        score = scorer(fitted, names)
        for better, worse in pairs_of(test):        # только внутри отложенной части
            total += 1
            hits += 1 if score(better) > score(worse) else 0
    return (hits / total if total else 0.0), total


def paired_grouped_kfold(rows, folds=3, seed=42):
    families=sorted({r['family'] for r in rows});random.Random(seed).shuffle(families)
    baseline=model_hits=total=0.0
    for held in [families[i::folds] for i in range(folds)]:
        train=[r for r in rows if r['family'] not in held]
        test=[r for r in rows if r['family'] in held]
        if len(train)<8 or len(test)<2:continue
        fitted,names=train_pairwise(train)
        if fitted is None:continue
        score=scorer(fitted,names)
        for better,worse in pairs_of(test):
            total+=1
            delta=score(better)-score(worse)
            model_hits+=1 if delta>0 else .5 if delta==0 else 0
            delta=better['features']['балл']-worse['features']['балл']
            baseline+=1 if delta>0 else .5 if delta==0 else 0
    return {'n':int(total),'model':model_hits/total if total else 0,
            'baseline':baseline/total if total else 0,
            'delta':(model_hits-baseline)/total if total else 0}


def main() -> int:
    rows = load()
    print(f"позиций {len(rows)}; пар с разной оценкой {len(pairs_of(rows))}")
    base_acc, n_pairs = pairwise_accuracy(lambda r: r["features"]["балл"], rows)
    base_ndcg = ndcg(lambda r: r["features"]["балл"], rows)
    print(f"\nтекущий балл окна зрелости: парная точность {base_acc:.3f} на {n_pairs} парах, "
          f"NDCG@15 {base_ndcg:.3f}")

    fitted, names = train_pairwise(rows)
    if fitted is None:
        print("обучение невозможно: недостаточно пар")
        return 1
    score = scorer(fitted, names)
    fit_acc, _ = pairwise_accuracy(score, rows)
    fit_ndcg = ndcg(score, rows)
    print(f"модель на тех же данных (переобучение, не результат): точность {fit_acc:.3f}, "
          f"NDCG@15 {fit_ndcg:.3f}")

    honest_acc, honest_n = grouped_kfold(rows)
    print(f"\nчестная оценка (разбиение по семьям, пары только внутри отложенной части): "
          f"точность {honest_acc:.3f} на {honest_n} парах")

    random.seed(7)
    shuffled = [dict(r) for r in rows]
    grades = [r["grade"] for r in shuffled]
    random.shuffle(grades)
    for r, g in zip(shuffled, grades):
        r["grade"] = g
    control_acc, control_n = grouped_kfold(shuffled)
    print(f"контроль на перемешанных метках: точность {control_acc:.3f} на {control_n} парах")

    import numpy as np
    model, scaler = fitted
    weights = sorted(zip(names, model.coef_[0]), key=lambda t: -abs(t[1]))
    print("\nвеса признаков, по убыванию влияния:")
    for name, w in weights[:8]:
        print(f"   {name:24s} {w:+.3f}")

    card = {"эксперимент": "silver_experimental", "дата": "2026-09-29",
            "позиций": len(rows), "пар": n_pairs,
            "происхождение_меток": "agent_review (агент-аналитик банка), человеческих 0",
            "рубрика": "0 нет / 1 спорно скорее нет / 2 спорно скорее да / 3 да",
            "признаки": names, "исключено_из_признаков": sorted(EXCLUDE),
            "текущий_балл": {"парная_точность": round(base_acc, 3), "ndcg@15": round(base_ndcg, 3)},
            "модель_на_обучающих": {"парная_точность": round(fit_acc, 3), "ndcg@15": round(fit_ndcg, 3)},
            "модель_честная_оценка": {"парная_точность": round(honest_acc, 3), "пар": honest_n},
            "контроль_перемешанных_меток": {"парная_точность": round(control_acc, 3), "пар": control_n},
            "веса": {n: round(float(w), 4) for n, w in weights},
            "вывод": "", "подключено_в_продукт": False}
    paired = paired_grouped_kfold(rows)
    card['парное_сравнение_на_одних_контрольных_парах'] = paired
    gain = paired['delta']
    card["вывод"] = (
        f"На одних {paired['n']} контрольных парах: модель {paired['model']:.3f}, "
        f"базовый балл {paired['baseline']:.3f}, разница {gain:+.3f}. "
        "Пары зависимы, метки агентские; выигрыш на независимой человеческой разметке "
        "не подтверждён. Модель сохраняется как экспериментальная и не заменяет выдачу.")
    import hashlib
    artifact = {'version':'pairwise-weakness/1','feature_names':names,
                'weights':model.coef_[0].tolist(),'intercept':float(model.intercept_[0]),
                'scaler':scaler.tolist(),'dataset_sha256':hashlib.sha256(DATA.read_bytes()).hexdigest(),
                'evaluation':paired,'label_source':'agent_review','production_enabled':False}
    (HACK/'learning/reranker-experimental-20260929.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2))
    out = HACK / "learning/reranker-card-20260929.json"
    out.write_text(json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{card['вывод']}")
    print("карточка модели:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
