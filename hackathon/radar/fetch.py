"""Безопасная загрузка и разбор документов.

Загрузчик работает отдельно от модели, не имеет
инструментов и секретов, проверяет адрес до соединения и заново на каждом
редиректе, уважает robots.txt и лимиты размера и времени.

Остаточный риск: между проверкой DNS и соединением адрес может смениться
(DNS rebinding). Для прототипа это принято сознательно и отмечено в отчёте;
закрывается пинингом IP на соединение при переходе в сервис.
"""
from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import socket
import threading
import time
import unicodedata
import urllib.robotparser as robotparser
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx
from lxml import html as lxml_html

from .config import DocumentSnapshot, FetchResult, Limits, Settings

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443, None}
TEXT_TYPES = ("text/html", "application/xhtml+xml", "text/plain")


class AddressBlocked(Exception):
    pass


def _ip_allowed(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_url(url: str) -> str:
    """Проверяет схему, порт, отсутствие логина в URL и все адреса хоста."""
    p = urlparse(url)
    if p.scheme not in ALLOWED_SCHEMES:
        raise AddressBlocked(f"схема {p.scheme!r} запрещена")
    if p.username or p.password:
        raise AddressBlocked("учётные данные в URL запрещены")
    if not p.hostname:
        raise AddressBlocked("пустой хост")
    if p.port not in ALLOWED_PORTS:
        raise AddressBlocked(f"порт {p.port} запрещён")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror as e:
        raise AddressBlocked(f"DNS не разрешился: {e}") from e
    for info in infos:
        ip = info[4][0]
        if not _ip_allowed(ip):
            raise AddressBlocked(f"адрес {ip} во внутреннем диапазоне")
    return url


def origin_of(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, "", "", "", ""))


class RobotsCache:
    """robots.txt на origin. Запрет — это статус, а не повод сменить User-Agent."""

    def __init__(self, client: httpx.Client, user_agent: str, ttl_s: float = 86400.0):
        self._client = client
        self._ua = user_agent
        self._ttl = ttl_s
        self._cache: dict[str, tuple[float, robotparser.RobotFileParser | None]] = {}

    def allows(self, url: str) -> tuple[bool, str]:
        origin = origin_of(url)
        now = time.monotonic()
        cached = self._cache.get(origin)
        if cached and now - cached[0] < self._ttl:
            rp = cached[1]
        else:
            rp = self._load(origin)
            self._cache[origin] = (now, rp)
        if rp is None:
            return False, "robots_unknown"
        return (True, "ok") if rp.can_fetch(self._ua, url) else (False, "robots_denied")

    def _load(self, origin: str) -> robotparser.RobotFileParser | None:
        rp = robotparser.RobotFileParser()
        try:
            r = self._client.get(f"{origin}/robots.txt", timeout=8.0)
        except httpx.HTTPError:
            return None
        if r.status_code in (401, 403):
            return None  # консервативно считаем запретом проекта
        if r.status_code >= 400:
            rp.parse([])  # нет robots — правил нет, но это не лицензия
            return rp
        rp.parse(r.text.splitlines())
        return rp


class Fetcher:
    def __init__(self, settings: Settings, raw_dir: Path | None = None):
        self.s = settings
        self.limits: Limits = settings.limits
        self.raw_dir = raw_dir
        self._client = httpx.Client(
            follow_redirects=False,
            headers={"User-Agent": settings.user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(self.limits.fetch_timeout_s),
        )
        self.robots = RobotsCache(self._client, settings.user_agent)
        self._last_hit: dict[str, float] = {}
        # Загрузка стала параллельной (см. pipeline): запросы к разным владельцам идут
        # одновременно, а к одному — по очереди. Замок на владельца сохраняет задержку
        # между обращениями к одному сайту: она нужна не нам, а сайту.
        self._guard = threading.Lock()
        self._origin_locks: dict[str, threading.Lock] = {}

    def _origin_lock(self, url: str) -> threading.Lock:
        origin = origin_of(url)
        with self._guard:
            return self._origin_locks.setdefault(origin, threading.Lock())

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _respect_origin_delay(self, url: str) -> None:
        origin = origin_of(url)
        last = self._last_hit.get(origin)
        if last is not None:
            wait = self.limits.per_origin_delay_s - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[origin] = time.monotonic()

    def fetch(self, url: str) -> tuple[FetchResult, bytes | None]:
        """Один документ. Обращения к одному владельцу сериализуются замком владельца."""
        with self._origin_lock(url):
            return self._fetch_locked(url)

    def _fetch_locked(self, url: str) -> tuple[FetchResult, bytes | None]:
        started = time.monotonic()
        redirects: list[str] = []
        current = url
        try:
            validate_url(current)
        except AddressBlocked as e:
            return FetchResult(url=url, status="blocked_address", error=str(e)), None

        allowed, reason = self.robots.allows(current)
        if not allowed:
            return FetchResult(url=url, status=reason, error="robots"), None

        for _ in range(self.limits.max_redirects + 1):
            if time.monotonic() - started > self.limits.fetch_timeout_s:
                return FetchResult(url=url, status="timeout", redirects=redirects,
                                   elapsed_s=time.monotonic() - started), None
            self._respect_origin_delay(current)
            try:
                with self._client.stream("GET", current) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location", "")
                        nxt = str(httpx.URL(current).join(loc))
                        redirects.append(nxt)
                        try:
                            validate_url(nxt)  # каждый переход проверяем заново
                        except AddressBlocked as e:
                            return FetchResult(url=url, final_url=nxt, status="blocked_address",
                                               redirects=redirects, error=str(e)), None
                        allowed, reason = self.robots.allows(nxt)
                        if not allowed:
                            return FetchResult(url=url, final_url=nxt, status=reason,
                                               redirects=redirects, error="robots"), None
                        current = nxt
                        continue

                    ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
                    limit = self.limits.max_pdf_bytes if ctype == "application/pdf" else self.limits.max_html_bytes
                    if ctype and not (ctype in TEXT_TYPES or ctype == "application/pdf"):
                        return FetchResult(url=url, final_url=current, status="unsupported_type",
                                           http_status=r.status_code, content_type=ctype,
                                           redirects=redirects), None
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in r.iter_bytes():
                        size += len(chunk)
                        if size > limit:  # размер считаем после распаковки
                            return FetchResult(url=url, final_url=current, status="too_large",
                                               http_status=r.status_code, content_type=ctype,
                                               redirects=redirects), None
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    if r.status_code >= 400:
                        return FetchResult(url=url, final_url=current, status="http_error",
                                           http_status=r.status_code, content_type=ctype,
                                           redirects=redirects,
                                           elapsed_s=time.monotonic() - started), None
                    if not body:
                        return FetchResult(url=url, final_url=current, status="empty",
                                           http_status=r.status_code, redirects=redirects), None
                    digest = hashlib.sha256(body).hexdigest()
                    raw_path = None
                    if self.raw_dir:
                        self.raw_dir.mkdir(parents=True, exist_ok=True)
                        p = self.raw_dir / f"{digest[:16]}.bin"
                        p.write_bytes(body)
                        raw_path = str(p)
                    return FetchResult(url=url, final_url=current, status="ok",
                                       http_status=r.status_code, content_type=ctype,
                                       redirects=redirects, bytes_sha256=digest,
                                       elapsed_s=time.monotonic() - started, raw_path=raw_path), body
            except httpx.TimeoutException:
                return FetchResult(url=url, status="timeout", redirects=redirects,
                                   elapsed_s=time.monotonic() - started), None
            except httpx.HTTPError as e:
                return FetchResult(url=url, status="http_error", redirects=redirects,
                                   error=str(e), elapsed_s=time.monotonic() - started), None
        return FetchResult(url=url, status="http_error", redirects=redirects,
                           error="слишком много редиректов"), None


# --- разбор ----------------------------------------------------------------

DROP_TAGS = ("script", "style", "nav", "footer", "aside", "noscript", "form", "svg")


def normalize_text(text: str) -> str:
    """Одна версионируемая нормализация. Цитаты проверяются в этом же виде."""
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def parse_html(body: bytes, url: str, final_url: str) -> DocumentSnapshot | None:
    """HTML → заголовок и основной текст. Меню и скрипты убираем, абзацы сохраняем."""
    try:
        doc = lxml_html.fromstring(body)
    except Exception:
        return None
    for tag in DROP_TAGS:
        for node in doc.xpath(f"//{tag}"):
            node.getparent().remove(node)
    title_nodes = doc.xpath("//title/text()")
    title = normalize_text(title_nodes[0]) if title_nodes else ""
    blocks: list[str] = []
    for node in doc.xpath("//h1|//h2|//h3|//p|//li|//td|//blockquote"):
        chunk = normalize_text(node.text_content())
        if len(chunk) >= 40 or node.tag.startswith("h"):
            blocks.append(chunk)
    text = normalize_text("\n".join(b for b in blocks if b))
    if len(text) < 200:
        return None
    published = None
    for xp in ("//meta[@property='article:published_time']/@content",
               "//meta[@name='pubdate']/@content",
               "//time/@datetime"):
        found = doc.xpath(xp)
        if found:
            published = str(found[0])[:25]
            break
    return DocumentSnapshot(
        url=url,
        final_url=final_url,
        title=title,
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        published_at=published,
    )

# Первоисточники приходят в PDF: записки МВФ, доклады Банка России, статьи arXiv, тексты
# WIPO. До 27.09 такие ответы скачивались и выбрасывались — в `fetch.py` был только разбор
# HTML. Измерено на трёх живых прогонах: из девяти скачанных PDF семь не стали документами,
# и это были лучшие документы пула, тогда как в веб-выдаче первоисточников 3,3 %.
_PDF_PAGES = 14          # извлекателю достаётся 12 спанов по 1200 знаков, глубже он не смотрит
_SENT_END = tuple(".!?»\"”)›:;")


def _reflow(lines: list[str]) -> list[str]:
    """Склеивает строки, разорванные вёрсткой PDF, обратно в абзацы.

    Без этого цитата не находится в тексте документа: извлекатель возвращает предложение
    целиком, а в сыром тексте PDF оно разорвано переводом строки посреди фразы, и проверка
    «цитата — подстрока спана» отбрасывает кандидата. То есть без склейки PDF дал бы
    документы и ноль пригодных кандидатов.
    """
    out: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            if out and out[-1]:
                out.append("")
            continue
        if not out or not out[-1]:
            out.append(line)
            continue
        prev = out[-1]
        if prev.endswith("-") and line[:1].islower():
            out[-1] = prev[:-1] + line          # перенос по слогам: «регу-\nлирование»
        elif not prev.endswith(_SENT_END) and (line[:1].islower() or line[:1].isdigit()):
            out[-1] = prev + " " + line          # продолжение той же фразы
        else:
            out.append(line)
    return out


def _pdf_date(raw: object) -> str | None:
    """`D:20260115120000Z` → `2026-01-15`. Неправдоподобную дату лучше не иметь вовсе."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())[:8]
    if len(digits) != 8:
        return None
    year = int(digits[:4])
    if not (1990 <= year <= datetime.now(timezone.utc).year):
        return None
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def parse_pdf(body: bytes, url: str, final_url: str) -> DocumentSnapshot | None:
    """PDF → заголовок и текст. Колонтитулы и номера страниц убираем, абзацы склеиваем."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        pages = [(page.extract_text() or "") for page in reader.pages[:_PDF_PAGES]]
    except Exception:
        return None
    # Колонтитул повторяется на каждой странице и попадает в цитаты как часть фразы.
    repeats = Counter(ln.strip() for page in pages for ln in page.splitlines()
                      if 3 < len(ln.strip()) < 80)
    drop = {ln for ln, n in repeats.items() if n >= max(3, len(pages) // 2)}
    lines: list[str] = []
    for page in pages:
        for ln in page.splitlines():
            stripped = ln.strip()
            if stripped in drop or stripped.isdigit():
                continue
            lines.append(normalize_text(stripped))
    paras = _reflow(lines)
    # Обложка, выходные данные, адрес и правила цитирования занимали два-три спана из
    # двенадцати, которые вообще достаются извлекателю. Отрезаем всё до первого настоящего
    # абзаца: у преамбулы строки короткие, у текста — длинные.
    first = next((i for i, ln in enumerate(paras) if len(ln) >= 200), None)
    if first is not None and first < len(paras) // 2:
        paras = paras[first:]
    text = normalize_text("\n".join(paras).strip())
    if len(text) < 200:
        return None                              # скан без текстового слоя: нечего извлекать
    meta = getattr(reader, "metadata", None)
    title = normalize_text(str(getattr(meta, "title", "") or ""))
    if not title or len(title) < 4:
        title = next((ln for ln in text.split("\n") if 8 <= len(ln) <= 160), "")[:160]
    return DocumentSnapshot(
        url=url,
        final_url=final_url,
        title=title,
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        # Дата публикации у PDF остаётся неизвестной: `/CreationDate` — это когда файл
        # сверстали или пересобрали. Раньше она подставлялась сюда и уходила в промпт
        # извлечения как дата документа, то есть могла стать «датированным событием».
        published_at=None,
        pdf_creation_date=_pdf_date(getattr(meta, "creation_date_raw", None)),
    )


def parse_document(body: bytes, url: str, final_url: str,
                   content_type: str | None = None) -> DocumentSnapshot | None:
    """Разбор по фактическому типу ответа, а не по расширению в ссылке."""
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype == "application/pdf" or body[:5] == b"%PDF-":
        return parse_pdf(body, url, final_url)
    return parse_html(body, url, final_url)


class FixtureFetcher:
    """Отдаёт заранее сохранённые страницы. Нужен, чтобы гонять конвейер офлайн."""

    def __init__(self, directory: Path):
        self.dir = directory
        index = directory / "docs.json"
        self.map: dict[str, str] = json.loads(index.read_text(encoding="utf-8")) if index.exists() else {}

    def fetch(self, url: str) -> tuple[FetchResult, bytes | None]:
        name = self.map.get(url)
        if not name:
            return FetchResult(url=url, status="http_error", error="нет фикстуры"), None
        body = (self.dir / name).read_bytes()
        return FetchResult(url=url, final_url=url, status="ok", http_status=200,
                           content_type="text/html",
                           bytes_sha256=hashlib.sha256(body).hexdigest()), body

    def close(self) -> None:
        return None

    def __enter__(self) -> "FixtureFetcher":
        return self

    def __exit__(self, *exc) -> None:
        return None
