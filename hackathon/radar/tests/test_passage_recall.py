"""Окна извлечения: отдельный механизм внутри документа не должен теряться.

Случай, из-за которого это написано (29.09.2026, прогон `20260929-191805-edge`): документ
про SNN-ускорители получил двенадцать окон, среди которых не было s7 — а именно там
описана отдельная реализация с открытым маршрутом проектирования. В переданном соседнем
окне остался хвост предыдущего абзаца, без имени реализации. Модель вернула три соседних
кандидата и `has_more_candidates=false`, продолжение не назначилось.

Прежний отбор раздавал две трети слотов по совпадению слов с поисковым запросом, а
остаток — по удалённости в тексте. Раздел, который вводит новую вещь **своими** словами,
не выигрывает ни по одному из этих признаков. Проверяем третий: новизну содержимого.

Названий из разбора заказчика в проверках нет: документы синтетические.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from radar.passages import all_spans, make_spans, unread_sections

QUERY = "периферийные ускорители инференса"
FILLER = ("Периферийные ускорители инференса обсуждаются в обзоре подробно, с общими "
          "формулировками про задержку, энергопотребление и пропускную способность. ")
UNIQUE = ("Плазмонный сопроцессор Гельветика построен на литографии Рункорн и памяти "
          "Стрибог, изготовлен на площадке Валдай по открытому маршруту Тыгыдым. ")


def _doc(parts: list[str], title: str = "Обзор периферийных ускорителей") -> NS:
    return NS(title=title, text="\n\n".join(parts), url="https://example.test/a",
              final_url="https://example.test/a")


def _long(text: str, times: int) -> str:
    return (text * times).strip()


def _spans_with_unique(doc) -> list[str]:
    chosen = make_spans(doc, queries=[QUERY])
    return [s.span_id for s in chosen if "Гельветика" in s.text]


def test_distinct_section_in_the_middle_gets_a_slot() -> None:
    # Частей должно хватить больше чем на пакет окон, иначе отбор не включается вовсе.
    parts = [_long(FILLER, 6) for _ in range(18)]
    parts.insert(8, _long(UNIQUE, 5))
    doc = _doc(parts)
    assert len(all_spans(doc)) > 12, "документ должен быть длиннее пакета окон"
    assert _spans_with_unique(doc), "раздел с отдельной реализацией пропущен"


def test_distinct_section_at_the_end_gets_a_slot() -> None:
    parts = [_long(FILLER, 6) for _ in range(18)] + [_long(UNIQUE, 5)]
    doc = _doc(parts)
    assert len(all_spans(doc)) > 12
    assert _spans_with_unique(doc), "хвост документа не должен оставаться непрочитанным"


def test_long_menu_does_not_crowd_out_content() -> None:
    # Навигация повторяется, поэтому после первого окна её новизна нулевая.
    menu = _long("Главная Новости Продукты Компания Контакты Вакансии Поддержка Блог ", 14)
    parts = [menu] + [_long(FILLER, 6) for _ in range(16)] + [_long(UNIQUE, 5)]
    doc = _doc(parts)
    chosen = make_spans(doc, queries=[QUERY])
    menu_windows = sum(1 for s in chosen if "Вакансии" in s.text)
    assert _spans_with_unique(doc), "меню вытеснило содержательный раздел"
    assert menu_windows <= 2, f"меню заняло {menu_windows} окон из {len(chosen)}"


def test_repeated_generic_terms_do_not_win_slots() -> None:
    # Восемь почти одинаковых кусков и один содержательный: новизна должна победить.
    parts = [_long(FILLER, 6) for _ in range(18)]
    parts[9] = _long(UNIQUE, 5)
    doc = _doc(parts)
    chosen = make_spans(doc, queries=[QUERY])
    assert any("Гельветика" in s.text for s in chosen)


def test_document_without_extra_mechanism_needs_no_continuation() -> None:
    # Всё однородно: непрочитанного нового содержимого нет, продолжение не назначается.
    doc = _doc([_long(FILLER, 6) for _ in range(18)])
    shown = [s.span_id for s in make_spans(doc, queries=[QUERY])]
    assert unread_sections(doc, shown) == []


def test_unread_novel_section_is_reported_for_continuation() -> None:
    doc = _doc([_long(FILLER, 6) for _ in range(18)] + [_long(UNIQUE, 5)])
    # Сознательно показываем только начало: остаток обязан быть назван непрочитанным.
    shown = [s.span_id for s in all_spans(doc)[:3]]
    left = unread_sections(doc, shown)
    assert left, "непрочитанный раздел с новым содержимым не обнаружен"
    assert all(s.span_id not in shown for s in left)


def test_window_offsets_stay_exact() -> None:
    doc = _doc([_long(FILLER, 6) for _ in range(18)] + [_long(UNIQUE, 5)])
    for span in make_spans(doc, queries=[QUERY]):
        assert doc.text[span.start:span.end] == span.text


FROZEN = (Path(__file__).resolve().parents[2] / "learning" / "edge-progress-runs"
          / "20260929-191805-edge" / "documents.jsonl")
FROZEN_SHA = "704d8f65e00c48d15d8fc6678ddc4c3fd13c305e769c90d0738cf631c6cd3182"


@pytest.mark.skipif(not FROZEN.exists(), reason="замороженный прогон доступен только локально")
def test_frozen_document_keeps_the_section_that_was_lost() -> None:
    """Диагностическая регрессия на настоящем документе, из-за которого правка сделана."""
    doc = None
    for line in FROZEN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("text_sha256") == FROZEN_SHA:
            doc = NS(**row)
            break
    assert doc is not None, "документ не найден в замороженном прогоне"
    plan = json.loads((FROZEN.parent / "extraction-plan.json").read_text(encoding="utf-8"))
    queries = next((row["queries"] for row in plan["documents"] if row["url"] == doc.url), [])
    chosen = [s.span_id for s in make_spans(doc, queries=queries)]
    assert "s7" in chosen, f"окно с пропущенной реализацией снова не попало: {chosen}"
