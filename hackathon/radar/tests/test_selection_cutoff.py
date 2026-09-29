"""Отсечка по дате публикации перед платным извлечением.

Порог выведен из источников заказчика: в его таблице самая старая ссылка — 2022 года,
дальше 2024 (одна строка), 2025 (13 строк) и 2026 (49). Отсечение всего старше 2025 года
не лишает источников ни одну строку, поэтому окно в 24 месяца безопасно.

Главное правило здесь — документы **без даты остаются**. Дата известна меньше чем у
половины корпуса (29.09.2026 на прогоне Edge: 74 из 161), и отбрасывать их означало бы
терять сигналы, а не старьё.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from radar.selection import select_documents


def _doc(name: str, published: str | None) -> NS:
    return NS(url=f"https://example{name}.test/a", final_url=f"https://example{name}.test/a",
              title=f"Документ {name}",
              text=("Технология описана подробно, с механизмом и примером применения. " * 12),
              text_sha256=f"hash-{name}", lang="ru", published_at=published,
              parser_version="html/1")


def _hit(name: str, position: int) -> NS:
    return NS(url=f"https://example{name}.test/a", query="периферийные вычисления",
              position=position)


def test_old_document_is_not_sent_to_extraction() -> None:
    docs = [_doc("old", "2019-03-01"), _doc("new", "2026-05-01")]
    hits = [_hit("old", 1), _hit("new", 2)]
    picked, report = select_documents(docs, hits, 10, min_published="2024-09-29")
    urls = [d.url for d in picked]
    assert "https://examplenew.test/a" in urls
    assert "https://exampleold.test/a" not in urls
    reasons = {row["url"]: row["reason"] for row in report["documents"]}
    assert reasons["https://exampleold.test/a"] == "older_than_cutoff"


def test_document_without_date_survives_the_cutoff() -> None:
    # Без этого правила отсечка выбрасывала бы больше половины корпуса.
    docs = [_doc("nodate", None), _doc("old", "2019-03-01")]
    hits = [_hit("nodate", 1), _hit("old", 2)]
    picked, _ = select_documents(docs, hits, 10, min_published="2024-09-29")
    assert [d.url for d in picked] == ["https://examplenodate.test/a"]


def test_empty_cutoff_keeps_everything() -> None:
    docs = [_doc("old", "2019-03-01"), _doc("new", "2026-05-01")]
    hits = [_hit("old", 1), _hit("new", 2)]
    picked, _ = select_documents(docs, hits, 10, min_published="")
    assert len(picked) == 2


def test_site_quota_is_configurable() -> None:
    """Квота на один сайт — настройка, а не константа: «безлимит» должен быть достижим."""
    docs = [NS(url=f"https://one.test/{i}", final_url=f"https://one.test/{i}",
               title=f"Статья {i}", text=("Механизм, применение, стадия, игроки, источники и даты описаны подробно. " * 12),
               text_sha256=f"h{i}", lang="ru", published_at="2026-05-01",
               parser_version="html/1") for i in range(5)]
    hits = [NS(url=f"https://one.test/{i}", query="периферийные вычисления", position=i)
            for i in range(5)]
    assert len(select_documents(docs, hits, 10, max_per_source=2)[0]) == 2
    assert len(select_documents(docs, hits, 10, max_per_source=99)[0]) == 5
