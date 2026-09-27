"""Расшифровка аббревиатур по алгоритму Шварца и Хёрст.

Schwartz A.S., Hearst M.A. «A simple algorithm for identifying abbreviation definitions
in biomedical text», Pacific Symposium on Biocomputing, 2003.

Зачем это нам. Окно зрелости меряет строку, и если строка — аббревиатура, измеряется не
технология. Проверено 27.09.2026: термин «AI-SBOM» даёт 6 работ, «HTTP 402» — 47 при
возрасте 147 месяцев, потому что HTTP 402 это код состояния протокола из 1997 года.
Полная форма измеряется осмысленно, сокращение — нет.

Алгоритм ищет пары вида «полная форма (АББР)» и «АББР (полная форма)» и проверяет
кандидата справа налево: каждая буква аббревиатуры должна найтись в полной форме в том же
порядке, а первая буква — в начале слова. Никаких словарей и моделей, только текст.
"""
from __future__ import annotations

import re

# Скобочная конструкция: до 120 символов слева и содержимое скобок.
_PAREN = re.compile(r"(?P<before>[^()]{0,120})\((?P<inside>[^()]{2,60})\)")


def _looks_like_abbrev(text: str) -> bool:
    """Аббревиатура: коротко, есть заглавные или цифры, не обычное слово."""
    text = text.strip()
    if not (2 <= len(text) <= 12) or " " in text.strip() and len(text.split()) > 2:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    caps = sum(1 for c in letters if c.isupper())
    return caps >= max(2, len(letters) // 2) or any(c.isdigit() for c in text)


def _match(short: str, long: str) -> str | None:
    """Проверка кандидата справа налево, как в исходной статье.

    Буквы аббревиатуры ищутся в полной форме в обратном порядке; первая буква обязана
    стоять в начале слова. Возвращает найденную полную форму или None.
    """
    short_chars = [c.lower() for c in short if c.isalnum()]
    if not short_chars:
        return None
    s = len(short_chars) - 1
    l = len(long) - 1
    while s >= 0:
        ch = short_chars[s]
        while l >= 0 and long[l].lower() != ch:
            l -= 1
        if l < 0:
            return None
        if s == 0:
            # первая буква аббревиатуры должна начинать слово
            if l > 0 and long[l - 1].isalnum():
                # ищем левее ещё одно вхождение, начинающее слово
                j = l - 1
                while j >= 0:
                    if long[j].lower() == ch and (j == 0 or not long[j - 1].isalnum()):
                        l = j
                        break
                    j -= 1
                else:
                    return None
            return long[l:].strip(" -—,;:")
        s -= 1
        l -= 1
    return None


def find_pairs(text: str) -> dict[str, str]:
    """Пары «аббревиатура → полная форма», найденные в тексте.

    Обрабатываются оба порядка: «Model Context Protocol (MCP)» и «MCP (Model Context
    Protocol)». Возвращается словарь с ключом в нижнем регистре.
    """
    out: dict[str, str] = {}
    for m in _PAREN.finditer(text):
        before, inside = m.group("before"), m.group("inside").strip()
        if _looks_like_abbrev(inside):
            # «полная форма (АББР)»: полную форму ищем среди последних слов слева
            words = before.split()
            span = " ".join(words[-min(len(words), len(inside) + 4):])
            full = _match(inside, span)
            if full and len(full.split()) >= 2:
                out.setdefault(inside.lower(), full)
        else:
            # «АББР (полная форма)»: аббревиатура — последнее слово слева
            words = before.split()
            if words and _looks_like_abbrev(words[-1]) and len(inside.split()) >= 2:
                full = _match(words[-1], inside)
                if full:
                    out.setdefault(words[-1].lower().strip(",;:"), full)
    return out


def expand(term: str, text: str) -> tuple[str, str | None]:
    """Разворачивает термин-аббревиатуру по тексту источника.

    Возвращает пару «чем мерить, пояснение». Если расшифровки нет, термин остаётся
    как есть: выдумывать полную форму нельзя, иначе измерим несуществующее.
    """
    pairs = find_pairs(text)
    key = term.strip().lower()
    if key in pairs:
        return pairs[key], f"{term} = {pairs[key]}"
    # Термин может содержать аббревиатуру: «AI-SBOM management» → «AI-SBOM»
    for token in re.findall(r"[A-Za-z0-9-]{2,12}", term):
        if token.lower() in pairs and _looks_like_abbrev(token):
            full = pairs[token.lower()]
            return term.replace(token, full), f"{token} = {full}"
    return term, None
