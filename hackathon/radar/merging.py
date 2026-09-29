"""Объединение действительно эквивалентных технологий, а не тематически близких.

Порядок в конвейере — после фильтров и до ранжирования. Цель: один механизм не должен
занимать несколько мест в выдаче пятнадцати позиций. Замер 28.09.2026: три случая на тридцать
позиций занимали пять слотов — две карточки про трансграничные стейблкоины и три про
контроль доступа агентов.

**Чем это отличается от прежней склейки.** Прежняя сводила по пересечению слов длиннее пяти
знаков: объединяла «управление рисками» с «управлением доступом» и не видела одно и то же под
разными словами. Здесь векторы только **предлагают** пары, а решение принимается по
механизму и объекту, и есть явные запреты.

**Запреты из задания** — это не подсказки планировщику, а регрессии оценки: близость имени и
высокий косинус склейку не разрешают.

  analog compute-in-memory ≠ любой compute-in-memory
  вычисления внутри пиксельной матрицы ≠ отдельный ускоритель рядом с сенсором
  доверенная среда на Cortex-M ≠ Intel SGX
  спекулятивный декодинг ≠ FlashAttention
  LoRA ≠ LoRaWAN
  локальный инференс ≠ обучение модели на смартфоне

Цепочка A≈B, B≈C основанием объединить A и C не является: объединяются только пары, каждая
из которых прошла проверку, и группа не расширяется транзитивно.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Порог предложения пары. Не порог склейки: после него пара идёт на проверку.
SUGGEST = 0.90

# Пары признаков, которые нельзя объединять, даже когда косинус высокий. Каждая строка —
# зафиксированная ошибка из задания или из разбора наших прогонов.
FORBIDDEN: tuple[tuple[str, str, str], ...] = (
    (r"\banalog\b|аналогов", r"\bdigital\b|цифров", "аналоговые вычисления в памяти — не цифровые"),
    (r"in-?pixel|внутри пиксел|processing-in-pixel", r"\bnpu\b|ускорител|accelerator",
     "вычисления внутри пиксельной матрицы — не ускоритель рядом с сенсором"),
    (r"cortex-?m|микроконтроллер", r"\bsgx\b|intel|серверн", "доверенная среда на Cortex-M — не SGX"),
    (r"speculative decod|спекулятивн", r"flashattention|attention",
     "спекулятивный декодинг — не механизм внимания"),
    (r"\blora\b(?!wan)|мульти-?lora", r"lorawan|\blpwan\b", "LoRA — не LoRaWAN"),
    (r"обучен|дообучен|fine-?tun|training", r"инференс|inference|вывод",
     "обучение на устройстве — не инференс на устройстве"),
)


# Признаки, определяющие семью технологии. Если наборы различаются, записи не эквивалентны,
# каким бы высоким ни был косинус. Правило выведено из ложных склеек, найденных 29.09.2026 на
# настоящем пуле Edge: «фотонные нейроморфные схемы» слились с аналоговой VLSI-архитектурой, а
# «интеграция ускорителей в микроконтроллеры» — с аппаратными корнями доверия. Обе поглощённые
# записи соответствуют строкам таблицы заказчика (№47 и №16), то есть склейка уничтожала
# эталонную категорию — ровно то, что задание запрещает.
MODIFIERS: tuple[tuple[str, str], ...] = (
    ("фотон", r"фотон|photonic|оптическ|optical"),
    ("аналог", r"аналогов|analog|смешанно-сигнальн|mixed-signal"),
    ("цифров", r"цифров|digital"),
    ("нейроморф", r"нейроморф|neuromorphic|спайков|spiking"),
    ("в_памяти", r"в памяти|in-?memory|compute-in-memory|кросс-барн|crossbar"),
    ("в_пикселе", r"в пиксел|in-?pixel|processing-in-pixel|внутри сенсора|in-?sensor"),
    ("квант", r"квантов|quantum"),
    ("npu", r"\bnpu\b|нейропроцессор|ускорител[ья] нейронн"),
    ("доверенная_среда", r"\btee\b|доверенн[ойая] сред|корн[ейи] доверия|root of trust|\bsgx\b|\bpuf\b"),
    ("федеративное", r"федеративн|federated"),
    ("lora_адаптеры", r"\blora\b(?!wan)|адаптер"),
    ("lorawan", r"lorawan|\blpwan\b"),
    ("слм", r"\bslm\b|мал[ыхые] языков|small language"),
    ("спекулятивный", r"спекулятивн|speculative"),
    ("событийный", r"событийн|event-based|event-driven|dvs\b"),
)


def modifiers_of(text: str) -> set[str]:
    """Признаки семьи, найденные в тексте записи."""
    low = text.lower()
    return {name for name, pattern in MODIFIERS if re.search(pattern, low)}


@dataclass
class MergeGroup:
    """Группа эквивалентных записей. Свойства участников не переносятся друг на друга."""

    leader: dict
    members: list[dict] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return 1 + len(self.members)


def text_of(cand: dict) -> str:
    return " ".join(filter(None, [cand.get("name_ru", ""), cand.get("name_orig") or "",
                                  (cand.get("mechanism") or "")[:300],
                                  cand.get("object_affected") or ""]))


def forbidden_reason(a: str, b: str) -> str | None:
    """Запрещена ли пара. Проверяется в обе стороны: порядок записей случайный."""
    low_a, low_b = a.lower(), b.lower()
    for left, right, why in FORBIDDEN:
        if ((re.search(left, low_a) and re.search(right, low_b))
                or (re.search(left, low_b) and re.search(right, low_a))):
            return why
    return None


def same_object(a: dict, b: dict) -> bool:
    """Объект применения совпадает хотя бы одним значимым словом либо не указан у обоих."""
    def words(cand: dict) -> set[str]:
        raw = (cand.get("object_affected") or "").lower()
        raw = raw.replace('интернета вещей', 'iot')
        raw = re.sub(r'\biot\b', 'интернетвещей', raw)
        return {w[:6] for w in re.findall(r"[0-9a-zа-яё-]{4,}", raw)}
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.5


def merge(pool: list[dict], suggest: float = SUGGEST) -> list[MergeGroup]:
    """Объединяет эквивалентные записи. Векторы предлагают, проверка решает."""
    texts = [text_of(c) for c in pool]
    pairs: list[tuple[int, int, float]] = []
    try:
        from .vectors import embed
        matrix = embed(texts, "passage")
        for i in range(len(pool)):
            for j in range(i + 1, len(pool)):
                score = float(matrix[i] @ matrix[j])
                if score >= suggest:
                    pairs.append((i, j, score))
    except Exception:
        # Без векторов объединение не делается вовсе: лексическая склейка уже дала
        # ложные объединения, повторять её нельзя.
        pairs = []

    groups: dict[int, MergeGroup] = {i: MergeGroup(leader=c) for i, c in enumerate(pool)}
    indices = {id(c): i for i, c in enumerate(pool)}
    similarities = {(i, j): score for i, j, score in pairs}
    merged_into: dict[int, int] = {}
    for i, j, score in sorted(pairs, key=lambda t: -t[2]):
        # Транзитивности нет: если запись уже присоединена, новые пары к ней не расширяют группу.
        if i in merged_into or j in merged_into:
            continue
        # Never drop a previously formed group or infer equivalence through its leader.
        if groups[j].members:
            continue
        compatible = True
        for member in groups[i].members:
            k = indices[id(member)]
            if (similarities.get(tuple(sorted((k, j))), 0.0) < suggest
                    or forbidden_reason(texts[k], texts[j])
                    or not same_object(member, pool[j])
                    or modifiers_of(texts[k]) != modifiers_of(texts[j])):
                compatible = False
                break
        if not compatible:
            continue
        why = forbidden_reason(texts[i], texts[j])
        if why:
            groups[i].reasons.append(f"не объединено с «{pool[j].get('name_ru','')[:40]}»: {why}")
            continue
        if not same_object(pool[i], pool[j]):
            groups[i].reasons.append(
                f"не объединено с «{pool[j].get('name_ru','')[:40]}»: разный объект применения")
            continue
        diff = modifiers_of(texts[i]) ^ modifiers_of(texts[j])
        if diff:
            groups[i].reasons.append(
                f"не объединено с «{pool[j].get('name_ru','')[:40]}»: различаются признаки "
                f"семьи ({', '.join(sorted(diff))})")
            continue
        groups[i].members.append(pool[j])
        groups[i].aliases.append(str(pool[j].get("name_ru", ""))[:120])
        groups[i].reasons.append(f"объединено с «{pool[j].get('name_ru','')[:40]}» "
                                 f"по близости {score:.3f} и совпадению объекта")
        merged_into[j] = i
        del groups[j]
    return [groups[i] for i in sorted(groups)]
