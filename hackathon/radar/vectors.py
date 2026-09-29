"""Локальные векторы для сопоставления и склейки. Без API и без оплаты.

Что здесь можно и чего нельзя — это измерено, а не предположено.

**Нельзя**: сделать поиск полным. Codex проверил это 26.09.2026 (H1b): векторы дают
перестановку уже имеющихся записей, включая ложных соседей, и «отсутствующие детали не
появляются при сохранении кандидатов в векторную базу». Если документ про токенизированные
паи фондов никто не скачивал, никакая близость его не достанет — вектор ищет среди того,
что уже есть.

**Можно**: перестать терять совпадения при сопоставлении с эталоном. Судья ранжирует
кандидатов пересечением слов названия, и 28.09.2026 адресная проверка нашла в пуле две
строки эталона (№92 стресс-тесты агентов, №93 депозитные токены), которых лексический
предотбор не донёс. Это потеря измерителя, а не выдачи, но без надёжного измерителя не
видно, улучшаемся ли мы.

Модель `intfloat/multilingual-e5-small` уже лежит в локальном кеше, работает на русском и
английском, требует префиксов `query:` и `passage:`.
"""
from __future__ import annotations

import functools

MODEL = "intfloat/multilingual-e5-small"


@functools.lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL, local_files_only=True)


def embed(texts: list[str], kind: str = "passage"):
    """Векторы для списка текстов. `kind` — passage для записей, query для запроса."""
    import numpy as np
    if not texts:
        return np.zeros((0, 384), dtype="float32")
    prefixed = [f"{kind}: {t[:512]}" for t in texts]
    return _model().encode(prefixed, normalize_embeddings=True, batch_size=32,
                           show_progress_bar=False)


def rank(query: str, texts: list[str]) -> list[tuple[int, float]]:
    """Индексы записей по убыванию косинусной близости к запросу."""
    import numpy as np
    if not texts:
        return []
    q = embed([query], "query")[0]
    m = embed(texts, "passage")
    scores = m @ q
    order = np.argsort(-scores)
    return [(int(i), float(scores[i])) for i in order]


def candidate_text(cand: dict) -> str:
    """Что именно векторизуем у кандидата: название, термин, механизм и объект."""
    return " ".join(filter(None, [
        cand.get("name_ru", ""), cand.get("name_orig") or "",
        (cand.get("mechanism") or "")[:300], cand.get("object_affected") or ""]))


def near_duplicates(texts: list[str], threshold: float = 0.93) -> list[tuple[int, int, float]]:
    """Пары записей об одном и том же. Замена склейке по пересечению слов.

    Склейка по словам длиннее пяти знаков объединяла разное («управление рисками» и
    «управление доступом») и пропускала одно и то же под разными словами. Порог 0,93
    выбран как точка, где на наших пулах пары перестают быть разными механизмами.
    """
    import numpy as np
    m = embed(texts, "passage")
    if len(texts) < 2:
        return []
    sim = m @ m.T
    pairs = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if sim[i, j] >= threshold:
                pairs.append((i, j, float(sim[i, j])))
    return sorted(pairs, key=lambda t: -t[2])
