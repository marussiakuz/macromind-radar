"""Регрессии объединения: запреты из задания и отсутствие транзитивности."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from radar.merging import forbidden_reason, merge, same_object          # noqa: E402


def _c(name: str, mech: str = "", obj: str = "") -> dict:
    return {"name_ru": name, "name_orig": name, "mechanism": mech, "object_affected": obj}


def test_forbidden_pairs_from_the_task_are_rejected() -> None:
    # Каждая пара — зафиксированная ошибка: близость имени не разрешает склейку.
    cases = [("аналоговые вычисления в памяти", "цифровые вычисления в памяти"),
             ("processing-in-pixel вычисления в матрице", "NPU рядом с сенсором"),
             ("доверенная среда на Cortex-M", "Intel SGX на сервере"),
             ("спекулятивный декодинг", "FlashAttention"),
             ("мульти-LoRA на смартфоне", "LoRaWAN для датчиков"),
             ("дообучение модели на смартфоне", "инференс модели на смартфоне")]
    for left, right in cases:
        assert forbidden_reason(left, right), f"пара должна быть запрещена: {left} / {right}"
        assert forbidden_reason(right, left), "запрет обязан работать в обе стороны"


def test_unrelated_pair_is_not_forbidden() -> None:
    assert forbidden_reason("нейроморфный процессор", "событийный сенсор") is None


def test_same_object_requires_overlap() -> None:
    assert same_object(_c("а", obj="устройства интернета вещей"), _c("б", obj="IoT устройства"))
    assert not same_object(_c("а", obj="серверные приложения"), _c("б", obj="спутники"))
    assert not same_object(_c("а"), _c("б"))     # отсутствие объекта не доказывает эквивалентность


def test_merge_keeps_forbidden_pair_apart_even_when_texts_are_close() -> None:
    pool = [_c("аналоговые compute-in-memory чипы для инференса",
               "вычисления в памяти на аналоговых кросс-барных массивах", "edge-инференс"),
            _c("цифровые compute-in-memory чипы для инференса",
               "вычисления в памяти на цифровых массивах", "edge-инференс")]
    groups = merge(pool, suggest=0.5)             # порог занижен намеренно: пара близка
    assert len(groups) == 2, "аналоговое и цифровое объединять нельзя"
    assert any("не объединено" in r for g in groups for r in g.reasons)


def test_merge_joins_true_duplicates() -> None:
    pool = [_c("трансграничные переводы стейблкоинами",
               "перевод средств между странами через стейблкоины на публичных блокчейнах",
               "платежи"),
            _c("межграничные переводы стейблкоинами через публичные блокчейны",
               "перевод средств между странами через стейблкоины на публичных блокчейнах",
               "платежи")]
    groups = merge(pool, suggest=0.9)
    assert len(groups) == 1 and groups[0].size == 2
    assert groups[0].aliases and "объединено" in groups[0].reasons[0]


def test_merge_is_not_transitive() -> None:
    # A≈B и B≈C не дают объединения A и C: иначе группа расползается по цепочке.
    a = _c("локальный инференс языковой модели на ноутбуке", "запуск модели локально", "ноутбуки")
    b = _c("локальный инференс языковой модели на смартфоне", "запуск модели локально", "смартфоны")
    c = _c("локальный инференс языковой модели на сервере", "запуск модели локально", "серверы")
    groups = merge([a, b, c], suggest=0.5)
    assert sum(g.size for g in groups) == 3
    assert max(g.size for g in groups) <= 2, "цепочка не должна собирать всех в одну группу"


def test_distinct_family_modifiers_block_merge() -> None:
    # Ложные склейки, найденные на настоящем пуле Edge 29.09.2026: обе поглощённые записи
    # соответствовали строкам таблицы заказчика и исчезли бы из выдачи.
    from radar.merging import modifiers_of
    photonic = _c("фотонные нейроморфные схемы", "оптические схемы инференса", "чипы")
    analog = _c("аналоговая и смешанная VLSI-архитектура нейроморфных чипов",
                "аналоговые схемы спайковых сетей", "чипы")
    assert modifiers_of(photonic["name_ru"]) != modifiers_of(analog["name_ru"])
    groups = merge([photonic, analog], suggest=0.5)
    assert len(groups) == 2
    npu = _c("интеграция ускорителей нейронных сетей в микроконтроллеры", "NPU внутри MCU", "чипы")
    trust = _c("встраивание аппаратных корней доверия в IoT-чипы", "root of trust в чипе", "чипы")
    assert len(merge([npu, trust], suggest=0.5)) == 2


def test_same_family_still_merges() -> None:
    # Правило не должно запрещать объединение настоящих дублей внутри одной семьи.
    a = _c("развертывание малых языковых моделей на потребительском железе",
           "запуск SLM локально", "ноутбуки")
    b = _c("развертывание малых языковых моделей (SLM) на потребительских устройствах",
           "запуск SLM локально", "ноутбуки")
    groups = merge([a, b], suggest=0.9)
    assert len(groups) == 1 and groups[0].size == 2
