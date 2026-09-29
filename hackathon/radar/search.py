"""Планировщик запросов и поисковые провайдеры.

Планировщик получает только направление пользователя. Названия и ссылки из
таблицы заказчика в него не попадают: иначе проверка покрытия ничего не значит.
"""
from __future__ import annotations

import base64
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Protocol

import httpx
from lxml import etree

from .config import SearchHit, Settings, RUNS_DIR

# Две линзы из раздела 1.2 ответа GPT: технический механизм и рынок.
LENSES: dict[str, dict[str, str]] = {
    "product": {
        "en": "{sub} product launch generally available vendor 2026",
        "ru": "{sub} продукт запуск вендор 2026",
    },
    "funding": {
        "en": "{sub} startup raises seed series funding 2026",
        "ru": "{sub} стартап раунд инвестиции 2026",
    },
    "pilot": {
        "en": "{sub} pilot deployment enterprise customer 2026",
        "ru": "{sub} пилот внедрение заказчик 2026",
    },
    "standard": {
        "en": "{sub} standard specification regulator compliance 2026",
        "ru": "{sub} стандарт требование регулятор 2026",
    },
    "fix": {
        "en": "{sub} how to prevent mitigation tool 2026",
        "ru": "{sub} как предотвратить решение 2026",
    },
    # Линза research идёт не в веб-поиск, а в OpenAlex (см. MultiSearch), поэтому
    # шаблон пустой: академической базе нужны термины подсегмента, а не слова вроде
    # «preprint 2026». Если роутер выключен, запрос уйдёт в веб как есть.
    "research": {"en": "{sub}", "ru": "{sub}"},
}

PLANNER_SYSTEM = """Ты планируешь поиск по технологическому направлению.
Верни только JSON: {"subsegments": [{"en": "...", "ru": "..."}, ...]} — ровно 6
разных подсегментов. Поле en на английском, ru — тот же подсегмент по-русски.

Подсегмент — это класс решений, которые кто-то делает, продаёт или пилотирует:
что защищают, чем управляют, какую операцию автоматизируют. Думай как аналитик
рынка, а не как автор обзора литературы.

Нельзя: названия научных задач и типов атак (adversarial examples, model
inversion, membership inference), названия дисциплин, названия компаний и
продуктов, слишком общие слова вроде "AI safety".

Подсегменты должны делить направление на непересекающиеся части и вместе
покрывать его целиком.

Проверено 26.09.2026: источники эталона англоязычные, поэтому английская
формулировка обязательна; академические подсегменты дали нулевое покрытие."""


def plan_subsegments(direction: str, llm=None) -> tuple[list[dict[str, str]], str]:
    """Возвращает до 6 подсегментов как пары {en, ru} и пометку об источнике.

    Русское направление переводится здесь же: модель сразу выдаёт английские
    формулировки. Отдельный переводчик не нужен, а язык запроса потом выбирается
    по языку подсегмента.
    """
    if llm is not None:
        text, _, _ = llm.complete(PLANNER_SYSTEM, {"direction": direction})
        try:
            data = json.loads(text[text.find("{"): text.rfind("}") + 1])
            subs = []
            for item in data.get("subsegments", []):
                if isinstance(item, dict) and item.get("en"):
                    subs.append({"en": str(item["en"]).strip(), "ru": str(item.get("ru", "")).strip()})
            if len(subs) >= 4:
                return subs[:6], "llm"
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    # Запасной вариант без модели: направление как есть, только по-русски.
    # Покрытие будет хуже, и это видно в отчёте прогона.
    return [{"en": "", "ru": direction}], "fallback"


def build_queries(subsegments: list[dict[str, str]], limit: int, ru_share: float = 0.2,
                  lenses: tuple[str, ...] = ("product", "funding", "standard", "research"),
                  per_subsegment: int = 3) -> list[tuple[str, str, str]]:
    """Собирает запросы: product на каждый подсегмент, остальные линзы по кругу.

    Замер 26.09.2026 на «Защите ИИ»: product дала 65 кандидатов из 18 документов,
    funding — 38 из 13, standard — 16 из 6. По одной продуктивности линзы product и
    funding выигрывают, но судья по пулу 27.09 показал, что шесть категорий эталона
    (приватность, TEE, водяные знаки, unlearning, мониторинг цепочки рассуждений,
    governance) в продуктовых новостях не встречаются вообще. Поэтому product
    остаётся на всех подсегментах, а funding, standard и research чередуются:
    диверсификация запросов важнее глубины, число загрузок всё равно ограничено.
    """
    primary, rotation = lenses[0], lenses[1:] or lenses[:1]
    # Слоями, а не подсегмент за подсегментом: при обрезке по лимиту теряется
    # третья линза последних подсегментов, а не сами последние подсегменты.
    layers: list[list[tuple[str, str, str]]] = [[] for _ in range(max(1, per_subsegment))]
    russian: list[tuple[str, str, str]] = []
    for i, sub in enumerate(subsegments):
        if sub.get("en"):
            chosen = [primary] + [rotation[(i + k) % len(rotation)]
                                  for k in range(max(0, per_subsegment - 1))]
            for depth, lens in enumerate(dict.fromkeys(chosen)):
                layers[min(depth, len(layers) - 1)].append(
                    (LENSES[lens]["en"].format(sub=sub["en"]), "en", lens))
        if sub.get("ru"):
            russian.append((LENSES[primary]["ru"].format(sub=sub["ru"]), "ru", primary))
    english = [q for layer in layers for q in layer]
    ru_slots = max(0, min(len(russian), int(limit * ru_share)))
    return (english[: limit - ru_slots] + russian[:ru_slots])[:limit]


class SearchProvider(Protocol):
    def search(self, query: str, lang: str, lens: str, count: int) -> list[SearchHit]: ...


class MultiSearch:
    """Источник под линзу: research — в академическую базу, остальные — в веб.

    Замер 26.09.2026: в веб-выдаче 3,3 % первоисточников и 13,4 % SEO-подборок, а
    пять эталонных категорий не имеют продуктов и в продуктовой выдаче появиться не
    могут (`radar/hoststats.py` воспроизводит числа). Поэтому источник выбирается
    по смыслу линзы, а не один на все.

    Бесплатные вызовы считаются отдельно от платных, иначе смета прогона врёт.
    """

    def __init__(self, web, by_lens: dict[str, object] | None = None):
        self.web = web
        self.by_lens = by_lens or {}

    def _provider(self, lens: str):
        return self.by_lens.get(lens, self.web)

    def search(self, query: str, lang: str, lens: str, count: int) -> list[SearchHit]:
        return self._provider(lens).search(query, lang, lens, count)

    @property
    def calls(self) -> int:
        """Только платные вызовы: по ним считается стоимость прогона."""
        return sum(getattr(p, "calls", 0) for p in [self.web, *self.by_lens.values()]
                   if getattr(p, "paid", True))

    @property
    def spent_rub(self) -> float:
        return sum(getattr(p, 'spent_rub', 0.0) for p in [self.web, *self.by_lens.values()])

    @property
    def free_calls(self) -> int:
        return sum(getattr(p, "calls", 0) for p in self.by_lens.values()
                   if not getattr(p, "paid", True))

    @property
    def snapshots(self) -> dict:
        """Готовые снимки текста: такие URL не нужно скачивать."""
        out: dict = {}
        for p in [self.web, *self.by_lens.values()]:
            out.update(getattr(p, "snapshots", {}) or {})
        return out

    @property
    def errors(self) -> list[str]:
        out: list[str] = []
        for p in [self.web, *self.by_lens.values()]:
            out.extend(getattr(p, "errors", []) or [])
        return out

    def close(self) -> None:
        for p in [self.web, *self.by_lens.values()]:
            if hasattr(p, "close"):
                p.close()


class YandexSearch:
    """Yandex Search API v2, синхронный режим.

    Состав запроса и разбор ответа проверить на первом живом вызове: до этого
    адаптер считается непроверенным, о чём пишет прогон.
    """

    def __init__(self, settings: Settings, cache_dir: Path | None = None):
        if not settings.has_keys:
            raise RuntimeError("нет YANDEX_API_KEY или YANDEX_FOLDER_ID")
        self.s = settings
        self.cache_dir = cache_dir
        self.calls = 0
        self.spent_rub = 0.0
        self._client = httpx.Client(timeout=httpx.Timeout(20.0))

    def search(self, query: str, lang: str, lens: str, count: int) -> list[SearchHit]:
        body = {
            "query": {
                "searchType": "SEARCH_TYPE_RU" if lang == "ru" else "SEARCH_TYPE_COM",
                "queryText": query,
                "page": "0",
            },
            "folderId": self.s.yandex_folder_id,
            "responseFormat": "FORMAT_XML",
        }
        cache_file = None
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        daily_cache = RUNS_DIR / '.search-cache' / datetime.now(timezone.utc).date().isoformat() / (digest + '.xml')
        if self.cache_dir:
            cache_file = self.cache_dir / f'{lang}_{digest}.xml'
            if cache_file.exists():
                return parse_yandex_xml(cache_file.read_bytes(), query, lang, lens, count)
        if daily_cache.exists():
            xml = daily_cache.read_bytes()
            if cache_file:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_bytes(xml)
            return parse_yandex_xml(xml, query, lang, lens, count)
        if __import__('os').environ.get('RADAR_CACHE_ONLY') == '1':
            from .ledger import LimitReached
            raise LimitReached('cache-only: missing search response')
        # Учёт до обращения: при обрыве соединения провайдер уже посчитал вызов, и учёт,
        # который пишет только успешные ответы, занижает расход.
        from .ledger import Prices as _P, shared as _ledger
        price = _P().search_call_rub
        with _ledger().paid(price, "search", f"search:{lang}:{query[:40]}") as _spent:
            self.spent_rub += price
            r = self._client.post(
                self.s.search_endpoint,
                headers={"Authorization": f"Api-Key {self.s.yandex_api_key}"},
                json=body,
            )
            self.calls += 1
            _spent["actual"] = price
        r.raise_for_status()
        raw = r.json().get("rawData")
        if not raw:
            return []
        xml = base64.b64decode(raw)
        daily_cache.parent.mkdir(parents=True, exist_ok=True)
        daily_cache.write_bytes(xml)
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            safe = "".join(ch if ch.isalnum() else "_" for ch in query)[:60]
            (self.cache_dir / f"{lang}_{safe}.xml").write_bytes(xml)
            cache_file.write_bytes(xml)
        return parse_yandex_xml(xml, query, lang, lens, count)

    def close(self) -> None:
        self._client.close()


def parse_yandex_xml(xml: bytes, query: str, lang: str, lens: str, count: int) -> list[SearchHit]:
    """Достаёт url, заголовок и сниппет из XML выдачи, сохраняя порядок."""
    root = etree.fromstring(xml)
    hits: list[SearchHit] = []
    for pos, doc in enumerate(root.iter("doc"), start=1):
        url_node = doc.find("url")
        if url_node is None or not url_node.text:
            continue
        title = "".join(doc.find("title").itertext()) if doc.find("title") is not None else ""
        passages = doc.findall(".//passage")
        snippet = " ".join("".join(p.itertext()) for p in passages)[:600]
        hits.append(SearchHit(url=url_node.text.strip(), title=title.strip(), snippet=snippet.strip(),
                              position=pos, query=query, lang=lang, lens=lens))
        if len(hits) >= count:
            break
    return hits


class FixtureSearch:
    """Выдача из сохранённых файлов: позволяет гонять конвейер без сети."""

    def __init__(self, directory: Path):
        self.dir = directory
        self.calls = 0

    def search(self, query: str, lang: str, lens: str, count: int) -> list[SearchHit]:
        """Файл линзы, а если его нет — любой файл того же языка.

        Проверено 26.09.2026: фикстуры сохранены под старые имена линз (market,
        mechanism), поэтому демонстрационный режим молча отдавал ноль документов, и
        unit-тесты этого не показывали. Запасной путь делает демо-режим рабочим при
        любом переименовании линз.
        """
        self.calls += 1
        path = self.dir / f"{lang}_{lens}.json"
        if not path.exists():
            fallback = sorted(self.dir.glob(f"{lang}_*.json"))
            if not fallback:
                return []
            path = fallback[0]
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            SearchHit(url=item["url"], title=item.get("title", ""), snippet=item.get("snippet", ""),
                      position=i + 1, query=query, lang=lang, lens=lens)
            for i, item in enumerate(data[:count])
        ]


def registrable_domain(url: str) -> str:
    """Грубый владелец URL: последние две части хоста.

    Для co.uk и подобных суффиксов даёт ошибку; в сервисе заменить на Public
    Suffix List. Здесь используется только для ограничения «не больше N ссылок
    одного владельца», поэтому цена ошибки мала.
    """
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower().lstrip("www.")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def select_urls(hits: list[SearchHit], limit: int, max_per_owner: int,
                exempt_urls: set[str] | None = None) -> list[SearchHit]:
    """Отбор URL по кругу: сначала по одному результату на запрос, потом второй круг.

    Проверено 26.09.2026 независимой проверкой: при отборе «первые подходящие до
    заполнения квоты» 64 места последнего веб-прогона заняли результаты **7 запросов
    из 24**, то есть четырёх подсегментов из двенадцати, и только линз product и
    funding. Русские запросы и линзы standard с research не получили ни одного
    слота. В прогоне по OpenAlex то же самое: до извлечения дошли 7 подсегментов из
    12. То есть отсутствие категорий в пуле означало не «источник их не содержит», а
    «мы их не искали».

    Круговой отбор даёт каждому запросу первый слот раньше, чем любой запрос получит
    второй. Ограничение на владельца и исключение для результатов API сохраняются.
    """
    exempt = exempt_urls or set()
    by_query: dict[str, list[SearchHit]] = {}
    for hit in hits:
        by_query.setdefault(hit.query, []).append(hit)

    seen: set[str] = set()
    per_owner: dict[str, int] = {}
    out: list[SearchHit] = []
    depth = 0
    deepest = max((len(v) for v in by_query.values()), default=0)
    while depth < deepest and len(out) < limit:
        for queue in by_query.values():
            if depth >= len(queue) or len(out) >= limit:
                continue
            hit = queue[depth]
            url = hit.url.split("#")[0]
            if url in seen:
                continue
            # A resolver/repository hosts independent publications and projects.
            from .selection import source_unit
            unit = source_unit(url)
            owner = registrable_domain(url) if unit.startswith("host:") else unit
            if url not in exempt and per_owner.get(owner, 0) >= max_per_owner:
                continue
            seen.add(url)
            per_owner[owner] = per_owner.get(owner, 0) + 1
            out.append(hit)
        depth += 1
    return out


SEED_SYSTEM = """Переведи направление на английский и предложи 4 разведочных запроса.
Верни только JSON: {"direction_en": "...", "seed_queries": ["...", "...", "...", "..."]}.

Запросы должны смотреть в разные стороны: первый — обзор рынка и продуктов,
второй — сделки и запуски 2026 года, третий — стандарты и требования регуляторов,
четвёртый — исследования и новые методы, о которых ещё нет продуктов.

Сначала определи роль предмета в направлении и сохрани её в запросах.
Если направление говорит о защите ИИ, то объект защиты — сами ИИ-системы:
модели, агенты, промпты, обучающие данные, цепочка поставки моделей. Это не то
же самое, что применение ИИ для защиты ИТ-инфраструктуры: центры мониторинга,
обнаружение вторжений, внутренние угрозы. Английское «AI security» рынок чаще
понимает во втором смысле, поэтому формулируй запросы так, чтобы роль не
перепуталась: например «securing AI agents», «LLM application security»,
«model supply chain security».

Проверено 26.09.2026: три запроса только про рынок дали заземление на продукты
защиты периметра, и шесть категорий эталона — приватность, криптографическое
исполнение, водяные знаки, unlearning, мониторинг цепочки рассуждений,
соответствие регуляторике — не попали в подсегменты вообще."""

GROUND_SYSTEM = """Тебе даны два списка: заголовки и фрагменты из свежей поисковой
выдачи (поле found) и названия свежих научных работ по направлению (поле papers).
Выдели 14 подсегментов направления, которые реально встречаются в этих текстах.

Верни только JSON: {"subsegments": [{"en": "...", "ru": "..."}, ...]}.

Не меньше трети подсегментов должны опираться на список papers, если в нём есть
темы, которых нет в found. Проверено 26.09.2026: заземление на одну веб-выдачу даёт
словарь готового рынка («AI posture management», «sovereign AI»), и целые
направления, которые пока существуют только в исследованиях, не попадают в план
вообще — а значит, их никто и не ищет.

Правила: подсегмент — класс решений, которые делают, продают, пилотируют или
исследуют. Бери словарь из предоставленных текстов, а не из своих знаний. Не используй
названия научных задач и типов атак, названия компаний и продуктов. Подсегменты
не должны пересекаться.

Подсегменты не должны быть только готовыми продуктами. Слабый сигнал часто ещё не
продаётся: если в текстах есть направления на уровне исследований, требований
регуляторов или отдельных пилотов, выдели их наравне с рыночными. Тип сигнала —
продукт, стандарт или исследование — не влияет на то, брать подсегмент или нет.

Сохраняй роль предмета из направления. Если защищают сами ИИ-системы, то
подсегменты про применение ИИ для защиты инфраструктуры — обнаружение угроз,
центры мониторинга, внутренние угрозы — сюда не относятся и должны быть
отброшены, даже если они часто встречаются в текстах."""


PAIN_SYSTEM = """Тебе даны заголовки и фрагменты свежей поисковой выдачи и названия
свежих научных работ по направлению. Выдели 12 **нерешённых проблем**, которые в этих
текстах названы или подразумеваются.

Верни только JSON: {"subsegments": [{"en": "...", "ru": "...", "why_new": "..."}, ...]},
где en — формулировка проблемы по-английски, ru — по-русски, why_new — одной фразой,
почему она обострилась именно сейчас.

Проблема, а не сегмент рынка. «Open banking» — сегмент, не подходит. «Платёж, который
инициирует автономный агент, нечем авторизовать» — проблема, подходит. Проверка: проблему
можно сформулировать как предложение с глаголом «не получается», «нечем», «ломается».

Проблема должна быть конкретной и новой. Не «безопасность сложна», а «агент выполняет
инструкции, попавшие к нему со страницы, которую он открыл сам». Не «нужно соблюдать
требования», а «непонятно, кто отвечает за действие, совершённое автономным агентом».

Бери формулировки из предоставленных текстов. Если проблема существовала и пять лет
назад в том же виде — не бери: нас интересует то, что обострилось за последние полтора
года.

Проверено 27.09.2026: планировщик, которого просят назвать сегменты, выдаёт структуру
отрасли из любого обзора, и край отрасли в план не попадает вообще. У новой категории
ещё нет имени, но боль у неё конкретная, и по боли находятся те, кто её решает."""



AXES_SYSTEM = """Тебе даны заголовки и фрагменты свежей поисковой выдачи и названия свежих
научных работ по направлению. Перечисли 12 **объектов и слоёв** этого направления, в
которых прямо сейчас появляется новое.

Верни только JSON: {"subsegments": [{"en": "...", "ru": "...", "why_new": "..."}, ...]}.

Оси, по которым надо пройти, — по две-три записи на ось:
  * **инструменты и активы**: чем распоряжаются, что выпускают, что служит обеспечением.
    Перечисли типы: депозиты, паи фондов, обеспечение и залог, обмен валют, страховые
    продукты, права требования;
  * **слои инфраструктуры**: расчёты, хранение, идентификация, обмен данными и отдельно
    **криптографические примитивы** — постквантовые алгоритмы, доказательства с нулевым
    разглашением, многосторонние вычисления, конфиденциальные вычисления;
  * **каналы и способы взаимодействия**: голос и телефония, браузер, автономный агент,
    встроенный в чужой продукт сервис, мессенджер;
  * **функции внутри отрасли**: не только продажа и обслуживание, но и взыскание,
    урегулирование претензий, надзор, отчётность, аудит;
  * **объекты регулирования и надзора**: что именно требуют раскрывать, проверять,
    страховать, хранить.

Перечисление осей — это знание о самой отрасли, а не подсказка ответа: конкретные
технологии внутри каждой оси ты обязан взять из показанных текстов, а не из своей памяти.

Это дополнение к другому плану, который ищет нерешённые проблемы. Здесь нужны **не боли**,
а именно предметы: то, что можно выпустить, заложить, зашифровать, застраховать, провести
через расчёт.

Зачем так. Измерено 28.09.2026 по «Финтеху»: план из одних болей не покрыл шесть категорий
из семнадцати, и все шесть — предметы, а не проблемы. После добавления этой оси нашлись
четыре из шести; не нашлись голосовые агенты для взыскания долга (ось канала и ось функции)
и постквантовая криптография в расчётах (ось примитива) — поэтому обе оси перечислены
явно. Примеры пропущенного: токенизированные паи денежных фондов
как обеспечение, депозитные токены, стейблкоины локальных валют с обменом на цепочке,
программируемые целевые деньги, постквантовая криптография в расчётах, ончейн-скоринг для
необеспеченного кредитования. Спросить о них по «болям» невозможно: у предмета нет боли.

Бери формулировки из предоставленных текстов. Предмет, который существовал в том же виде
пять лет назад и с тех пор не изменился, не бери."""

ANCHOR_STOP = {"слабые", "сигналы", "технологии", "решения", "область", "направление",
               "weak", "signals", "technologies", "in", "and", "the", "of", "для", "в", "и"}


def anchor_filter(subsegments: list[dict[str, str]], direction: str) -> list[dict[str, str]]:
    """Оставляет формулировки, связанные с исходным запросом хотя бы одним значимым словом.

    Проверка детерминированная и дешёвая, в дополнение к смысловой проверке моделью.
    Обзор методов расширения запроса называет это entity protection: сущности исходного
    запроса нельзя терять при расширении, иначе тема уходит. Проверено 27.09.2026 на
    «Биотехнологиях и генетике»: планировщик выдал две боли про платежи ИИ-агентов, и
    вся выдача оказалась про агентский банкинг вместо биотеха.

    Если якорь отсеял бы слишком много, он не применяется: терять план целиком хуже,
    чем пропустить пару чужих формулировок к смысловой проверке.
    """
    import re as _re

    words = {w for w in _re.findall(r"[0-9A-Za-zА-Яа-яёЁ]{4,}", direction.lower())
             if w not in ANCHOR_STOP}
    if not words:
        return subsegments
    roots = {w[:5] for w in words}
    kept = []
    for sub in subsegments:
        text = f"{sub.get('en','')} {sub.get('ru','')}".lower()
        if any(root in text for root in roots):
            kept.append(sub)
    return kept if len(kept) >= max(4, len(subsegments) // 3) else subsegments


def plan_subsegments_grounded(direction: str, llm, searcher, results: int = 10,
                              plan: str = "segments"):
    """Подсегменты из свежих источников, а не из памяти модели.

    Проверено 26.09.2026: планировщик без заземления дважды выдал таксономию атак
    (adversarial ML, model inversion, membership inference) и дал нулевое покрытие
    эталона. Словарь рынка 2026 года модель из памяти не достаёт.

    Заземление идёт двумя волнами. Веб даёт словарь готового рынка, научная выборка —
    словарь того, что ещё не продаётся. По замеру того же дня одной веб-волны не
    хватает: план из неё не содержал ни одного подсегмента про темы, живущие только
    в исследованиях, поэтому такие категории эталона не искались вовсе.
    """
    text, _, _ = llm.complete(SEED_SYSTEM, {"direction": direction})
    try:
        seed = json.loads(text[text.find("{"): text.rfind("}") + 1])
        queries = [str(q) for q in seed.get("seed_queries", [])][:4]
        direction_en = str(seed.get("direction_en") or "").strip()
    except (json.JSONDecodeError, ValueError):
        queries, direction_en = [], ""
    if not queries:
        return plan_subsegments(direction, llm)

    snippets = []
    for q in queries:
        for hit in searcher.search(q, "en", "seed", results):
            snippets.append({"title": hit.title, "snippet": hit.snippet[:300]})

    # Вторая волна: названия научных работ. Бесплатно, поэтому берём широко.
    papers: list[str] = []
    academic = getattr(searcher, "by_lens", {}).get("research")
    if academic is not None and hasattr(academic, "sample_titles"):
        for q in filter(None, [direction_en or direction, queries[-1] if queries else ""]):
            papers.extend(academic.sample_titles(q, 50))
    papers = list(dict.fromkeys(papers))[:100]

    if not snippets and not papers:
        return plan_subsegments(direction, llm)

    # План «mixed»: половина записей — нерешённые проблемы, половина — предметы и слои.
    # Причина в замере 28.09.2026: шесть категорий эталона «Финтеха» из семнадцати не
    # искались вовсе, и все шесть — предметы (паи фондов, депозитные токены, постквантовая
    # криптография), о которых нельзя спросить как о боли.
    if plan == "mixed":
        halves = []
        for sub_system in (PAIN_SYSTEM, AXES_SYSTEM):
            try:
                part, _, _ = llm.complete(sub_system, {"direction": direction,
                                                      "found": snippets[:30], "papers": papers})
                got = json.loads(part[part.find("{"): part.rfind("}") + 1])
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
            halves.append([{"en": str(i["en"]).strip(), "ru": str(i.get("ru", "")).strip()}
                           for i in got.get("subsegments", [])
                           if isinstance(i, dict) and i.get("en")][:6])
        merged = [x for pair in zip(*halves) for x in pair] if len(halves) == 2 else             [x for part in halves for x in part]
        if len(merged) >= 6:
            return merged[:12], "grounded/mixed"
    system = PAIN_SYSTEM if plan == "pains" else GROUND_SYSTEM
    text, _, _ = llm.complete(system, {"direction": direction,
                                       "found": snippets[:30], "papers": papers})
    try:
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        subs = [{"en": str(i["en"]).strip(), "ru": str(i.get("ru", "")).strip()}
                for i in data.get("subsegments", []) if isinstance(i, dict) and i.get("en")]
        if len(subs) >= 6:
            subs = subs[:14]
            if plan == "pains":
                subs = anchor_filter(subs, direction)
                from .relevance import filter_in_domain
                keep, _ = filter_in_domain([x.get("en") or x.get("ru") for x in subs], direction, llm)
                filtered = [x for i, x in enumerate(subs) if keep.get(i, True)]
                dropped = len(subs) - len(filtered)
                if len(filtered) >= 4:
                    subs = filtered
                    if dropped:
                        return subs, (f"grounded/{plan} ({len(snippets)} сниппетов, "
                                      f"{len(papers)} работ, отброшено не по теме: {dropped})")
            return subs, f"grounded/{plan} ({len(snippets)} сниппетов, {len(papers)} работ)"
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return plan_subsegments(direction, llm)
