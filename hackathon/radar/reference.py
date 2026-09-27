"""Эталон из таблицы заказчика: категории по областям и их хэш.

Исходный XLSX не изменяется. В эталон берём только номер, область и название
(столбцы B, D, C). Столбцы F и I — объяснение эксперта и балл — в конвейер не
попадают: это готовое решение, по разделу 14 их нельзя подавать ни модели, ни
оценщику.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import openpyxl

from .config import CUSTOMER_XLSX, EVAL_DIR


@dataclass(frozen=True)
class ReferenceItem:
    number: int
    area: str
    name: str

    @property
    def tokens(self) -> frozenset[str]:
        return normalize_tokens(self.name)


STOP = {
    "для", "и", "в", "на", "с", "по", "как", "без", "от", "до", "при", "из", "the", "a", "an",
    "of", "for", "and", "in", "on", "to", "with", "as", "at", "by",
}


def normalize_tokens(text: str) -> frozenset[str]:
    """Грубая нормализация названия: строчные буквы, без пунктуации и стоп-слов.

    Морфологию не трогаем: она даёт ложные склейки на узких названиях.
    Этого достаточно, чтобы предложить пару человеку, но не чтобы засчитать её.
    """
    words = re.findall(r"[0-9a-zA-Zа-яёА-ЯЁ]+", text.lower())
    return frozenset(w for w in words if len(w) > 2 and w not in STOP)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def load_reference(xlsx: Path = CUSTOMER_XLSX) -> tuple[list[ReferenceItem], str]:
    """Читает лист «Слабые сигналы», строки 3–102. Возвращает эталон и хэш файла."""
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb["Слабые сигналы"]
    items: list[ReferenceItem] = []
    for row in ws.iter_rows(min_row=3, max_row=102, min_col=2, max_col=4, values_only=True):
        number, name, area = row
        if number is None or not name:
            continue
        items.append(ReferenceItem(number=int(number), area=str(area).strip(), name=str(name).strip()))
    wb.close()
    if len(items) != 100:
        raise ValueError(f"ожидали 100 строк эталона, получили {len(items)}")
    return items, file_sha256(xlsx)


def area_items(items: list[ReferenceItem], area: str) -> list[ReferenceItem]:
    return [i for i in items if i.area == area]


def export(path: Path | None = None) -> Path:
    """Сохраняет эталон в JSONL рядом с кодом. Файл не публикуем: это материал заказчика."""
    items, sha = load_reference()
    out = path or (EVAL_DIR / "reference.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"_meta": {"source_sha256": sha, "count": len(items)}}, ensure_ascii=False) + "\n")
        for i in items:
            f.write(json.dumps({"number": i.number, "area": i.area, "name": i.name}, ensure_ascii=False) + "\n")
    return out


# Соседние пары одной области, которые нельзя склеивать: раздел 14, правка 16.
DO_NOT_MERGE: list[tuple[int, int]] = [(67, 69), (2, 91), (44, 84), (47, 60), (18, 59)]


if __name__ == "__main__":  # pragma: no cover
    p = export()
    items, sha = load_reference()
    print(f"эталон: {len(items)} категорий, файл {p}")
    print(f"sha256 исходной таблицы: {sha}")
    for a in sorted({i.area for i in items}):
        print(f"  {a:22s} {len(area_items(items, a)):2d}")
