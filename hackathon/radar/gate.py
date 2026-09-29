"""Предварительная проверка запроса по поисковым результатам.

Помогает заметить двусмысленность, слишком широкую тему и нехватку материала.
Пороги являются эвристиками; аналитик может уточнить запрос или продолжить."""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field

from .relevance import direction_of

# Пороги. MIN_HITS/MIN_HOSTS — ниже этого материала просто нет. SPLIT_SHARE — какую долю
# выдачи должен занимать второй смысл, чтобы считаться отдельным чтением запроса.
# SPLIT_SIM — насколько центры кластеров должны быть непохожи. BROAD_CLUSTERS/BROAD_TOP —
# признак расползания: много мелких кластеров и ни одного заметного.
MIN_HITS = 6
MIN_HOSTS = 4
SPLIT_SHARE = 0.25
SPLIT_SIM = 0.80
BROAD_CLUSTERS = 5
BROAD_TOP = 0.30
# ТРИ ПОПЫТКИ ИЗМЕРИТЬ ШИРОТУ ЗАПРОСА, ВСЕ НЕУДАЧНЫЕ — не повторять, а читать:
#
# 1. Кластеры затравочной выдачи. 29.09.2026: «технологии» (заведомо широкий) против
#    «Микрофлюидный чип» и «Биотехнологии и генетика» (законные узкие) — слои источников
#    одинаковые (всё «прочее»), годов 2023+ у всех 0–3 из 20, латинских терминов 0–4 из 20.
# 2. Повтор лексики запроса в выдаче. У «Микрофлюидного чипа» три отличительных слова из
#    четырёх — свои же, как и у «технологий»: признак бракует законные узкие запросы.
# 3. Расхождение плана с запросом по векторам. Настоящие планы: «технологии» дал среднюю
#    близость ветвей к запросу 0,776, «Edge-вычисления» 0,818, «финансовые технологии»
#    0,819. Порядок верный, но зазор 0,04 при диапазоне модели 0,78–0,88 — порог
#    недостоверен.
#
# Поэтому широта здесь не детектируется автоматически. Вместо этого план показывается
# аналитику до дорогого этапа: у запроса «технологии» планировщик выдал ветви про
# авторизацию платежей агентов, MCP и red teaming — человек видит подмену темы мгновенно,
# а алгоритм на этих числах не видит.
#
# Широту по затравочной выдаче измерить не удалось, и это замер, а не лень. 29.09.2026
# сравнил «технологии» (заведомо широкий) с «Микрофлюидный чип» и «Биотехнологии и генетика»
# (законные узкие): слои источников одинаковые (всё «прочее»), годов 2023+ у всех 0–3 из 20,
# латинских терминов 0–4 из 20. Повтор лексики тоже не разделяет: у «Микрофлюидного чипа»
# три отличительных слова из четырёх — свои же, как и у «технологий». Поэтому порога на
# широту здесь нет; широта проверяется на плане функцией `assess_plan` — после дешёвого
# планировщика и до дорогих загрузки с извлечением.
PLAN_GENERIC_SHARE = 0.5
# Признаки потребительской и справочной выдачи. Калибровка: запрос «Edge» дал 85 % выдачи
# про скачивание браузера Microsoft Edge и словарный перевод — привратник обязан это
# поймать, иначе конвейер пятнадцать минут ищет технологии в карточках товара.
CONSUMER = re.compile(r"(скачать|download|купить|цена|цены|перевод|translate|"
                      r"википедия|wikipedia|dictionary|словар|browser|браузер|"
                      r"инструкц|отзыв)", re.IGNORECASE)
CONSUMER_SHARE = 0.4

# Служебные слова: из них складывались подсказки вида «ягуар when used» — проверено
# 29.09.2026 на запросе «ягуар», где отличительными словами чтения оказались when и used.
STOP = {"the", "and", "for", "with", "from", "that", "this", "your", "you", "are", "was",
        "how", "what", "why", "when", "where", "which", "used", "use", "using", "have",
        "has", "been", "will", "would", "can", "could", "should", "about", "into", "over",
        "than", "then", "there", "their", "these", "those", "such", "also", "more", "most",
        "other", "others", "here", "very", "much", "many", "some", "any", "not", "but",
        "все", "если", "чтобы", "этот", "быть", "может", "также",
        "который", "которые", "только", "более", "очень", "самый", "https", "www", "com"}


@dataclass
class Sense:
    """Одно чтение запроса: во что превращается выдача, если понимать запрос так."""

    terms: list[str]
    titles: list[str]
    share: float


@dataclass
class Verdict:
    status: str                      # ok | ambiguous | too_broad | no_material
    direction: str                   # что мы фактически будем искать
    message: str                     # человеку, по-русски
    senses: list[Sense] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    hits: int = 0
    hosts: int = 0
    paid_calls: int = 0
    stripped: bool = False           # убирали ли слова нашей задачи


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[0-9A-Za-zА-Яа-яёЁ][0-9A-Za-zА-Яа-яёЁ-]{3,}", (text or "").lower())
            if w not in STOP]


def _distinctive(texts: list[str], others: list[str], limit: int = 5) -> list[str]:
    """Слова, которыми это чтение отличается от остальной выдачи."""
    mine = collections.Counter(w for t in texts for w in set(_words(t)))
    rest = collections.Counter(w for t in others for w in set(_words(t)))
    scored = []
    for w, n in mine.items():
        if n < 2:
            continue
        scored.append((n / (1 + rest.get(w, 0)), n, w))
    scored.sort(reverse=True)
    return [w for _, _, w in scored[:limit]]


def assess(query: str, searcher, hits_per_query: int = 10) -> Verdict:
    """Пригоден ли запрос. Два поисковых запроса, остальное локально и бесплатно."""
    direction = direction_of(query)
    v = Verdict(status="ok", direction=direction, message="",
                stripped=direction.strip().lower() != (query or "").strip().lower())

    hits = []
    for lang in ("ru", "en"):
        try:
            found = searcher.search(direction, lang, "seed", hits_per_query)
        except Exception:
            continue
        v.paid_calls += 1
        hits.extend(found)
    v.hits = len(hits)
    hosts = {(h.url.split("/")[2] if "://" in (h.url or "") else "") for h in hits}
    hosts.discard("")
    v.hosts = len(hosts)

    if v.hits < MIN_HITS or v.hosts < MIN_HOSTS:
        v.status = "no_material"
        v.message = (f"По запросу «{direction}» материала почти нет: {v.hits} страниц с "
                     f"{v.hosts} сайтов. Попробуйте назвать технологию или задачу другими "
                     f"словами — например, добавить область применения или английский термин.")
        return v

    texts = [f"{h.title} {h.snippet}"[:400] for h in hits]
    try:
        from .vectors import embed
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering
        m = embed(texts, "passage")
        labels = AgglomerativeClustering(n_clusters=None, distance_threshold=0.18,
                                         metric="cosine", linkage="average").fit_predict(m)
    except Exception as exc:                      # без векторов привратник не блокирует работу
        v.message = (f"Кластеризация выдачи не выполнена ({type(exc).__name__}), "
                     f"запрос пропущен без проверки на двусмысленность.")
        return v

    groups: dict[int, list[int]] = collections.defaultdict(list)
    for i, lab in enumerate(labels):
        groups[int(lab)].append(i)
    order = sorted(groups.values(), key=len, reverse=True)
    top_share = len(order[0]) / len(texts)

    senses: list[Sense] = []
    for grp in order[:3]:
        others = [texts[i] for i in range(len(texts)) if i not in grp]
        senses.append(Sense(terms=_distinctive([texts[i] for i in grp], others),
                            titles=[hits[i].title[:70] for i in grp[:2]],
                            share=round(len(grp) / len(texts), 2)))
    v.senses = senses

    # 1. Потребительская или справочная выдача: запрос понят как товар или слово.
    top_texts = [texts[i] for i in order[0]]
    top_urls = [hits[i].url for i in order[0]]
    consumer = sum(1 for t, u in zip(top_texts, top_urls) if CONSUMER.search(t) or CONSUMER.search(u))
    if consumer / max(1, len(top_texts)) >= CONSUMER_SHARE:
        v.status = "wrong_sense"
        hint = next((", ".join(sn.terms[:3]) for sn in senses[1:] if sn.terms), "")
        v.message = (f"Запрос «{direction}» выдача понимает как товар или слово, а не как "
                     f"технологическое направление: {consumer} из {len(top_texts)} страниц "
                     f"крупнейшей группы — скачивание, покупка, перевод или справка "
                     f"(например «{senses[0].titles[0] if senses[0].titles else ''}»). "
                     f"Назовите область: добавьте, где эта технология работает и что делает."
                     + (f" В выдаче есть и другое чтение: {hint}." if hint else ""))
        # Предложения из потребительских чтений бесполезны: «Edge русский перевод» это не
        # уточнение области. Берём только те чтения, в которых нет признаков товара и справки.
        v.suggestions = [f"{direction} {' '.join(sn.terms[:2])}".strip()
                         for sn in senses[1:]
                         if sn.terms and not any(CONSUMER.search(t) for t in sn.terms)][:2]
        if not v.suggestions:
            # Выдумывать уточнение нельзя: если технического чтения в выдаче нет, честнее
            # сказать это прямо, чем предложить формулировку из воздуха.
            v.message += (" Технического чтения этого слова в выдаче не нашлось вовсе, "
                          "поэтому предложить уточнение по найденному не могу.")
        return v

    if len(order) >= 2 and len(order[1]) / len(texts) >= SPLIT_SHARE:
        c0 = m[order[0]].mean(axis=0)
        c1 = m[order[1]].mean(axis=0)
        sim = float(c0 @ c1 / ((c0 @ c0) ** 0.5 * (c1 @ c1) ** 0.5))
        if sim < SPLIT_SIM:
            v.status = "ambiguous"
            a = ", ".join(senses[0].terms[:3]) or "первое чтение"
            b = ", ".join(senses[1].terms[:3]) or "второе чтение"
            v.message = (f"Запрос «{direction}» читается двумя способами: «{a}» "
                         f"({senses[0].share:.0%} выдачи) и «{b}» ({senses[1].share:.0%}). "
                         f"Уточните, какой смысл нужен, или запустим обе ветви — это два "
                         f"прогона вместо одного.")
            v.suggestions = [f"{direction} {' '.join(s.terms[:2])}".strip() for s in senses[:2]]
            return v

    if len(order) >= BROAD_CLUSTERS and top_share < BROAD_TOP:
        v.status = "too_broad"
        v.message = (f"Запрос «{direction}» слишком широкий: выдача распадается на "
                     f"{len(order)} несвязанных групп, крупнейшая занимает "
                     f"{top_share:.0%}. Сузьте до задачи или подотрасли — иначе план "
                     f"вернёт структуру отрасли, а не её край.")
        v.suggestions = [f"{direction} {' '.join(s.terms[:2])}".strip() for s in senses[:3]]
        return v

    v.message = (f"Запрос принят, искать будем «{direction}»"
                 + (" (слова о слабых сигналах убраны: это наша постановка задачи, "
                    "а не тема поиска)" if v.stripped else "")
                 + f". Выдача связная: крупнейшая группа {top_share:.0%}, сайтов {v.hosts}.")
    return v


def assess_plan(subsegments: list[dict], direction: str) -> Verdict:
    """Вторая ступень: показать план аналитику до дорогого этапа.

    Планировщик стоит несколько рублей, загрузка с извлечением — около девяноста. На
    коротком или общем запросе план уезжает в чужую тему, оставаясь при этом конкретным:
    измерено 29.09.2026, запрос «технологии» дал двенадцать ветвей про безопасность
    ИИ-агентов — авторизацию платежей, MCP, red teaming. Автоматически это не отличается
    от нормального плана (см. три неудачные попытки выше), а человеком отличается сразу.
    Поэтому на коротком запросе просим подтверждение, а не угадываем.
    """
    v = Verdict(status="ok", direction=direction, message="")
    if not subsegments:
        v.status = "no_material"
        v.message = (f"По запросу «{direction}» план не построился: в выдаче не нашлось ни "
                     f"одной конкретной задачи или предмета. Назовите область иначе или "
                     f"добавьте, что должно работать лучше.")
        return v
    branches = [str(i.get("ru") or i.get("en") or "")[:120] for i in subsegments]
    # Подтверждение спрашиваем только у односложного запроса: «технологии», «Edge», «ИИ».
    # Порог 2 слова оказался слишком строгим — под него попадал и «Edge-вычисления и
    # периферийный ИИ», вполне конкретный запрос. Ложное подтверждение стоит один щелчок,
    # пропущенная подмена темы — девяносто рублей и пятнадцать минут.
    significant = [w for w in _words(direction) if len(w) > 4]
    if len(significant) <= 1:
        v.status = "confirm"
        v.message = (f"Запрос «{direction}» короткий, и план по нему может уехать в соседнюю "
                     f"тему: на запросе «технологии» планировщик выдал ветви про "
                     f"безопасность ИИ-агентов. Посмотрите {len(branches)} ветвей ниже — "
                     f"если это не то, уточните запрос; если то, запускаем поиск.")
        v.suggestions = branches[:12]
        return v
    v.message = (f"План принят: {len(branches)} ветвей по запросу «{direction}». "
                 f"Идём в поиск.")
    v.suggestions = branches[:12]
    return v
