"""Безопасная загрузка и разбор документов.

Контракт раздела 3.3 ответа GPT: загрузчик работает отдельно от модели, не имеет
инструментов и секретов, проверяет адрес до соединения и заново на каждом
редиректе, уважает robots.txt и лимиты размера и времени.

Остаточный риск: между проверкой DNS и соединением адрес может смениться
(DNS rebinding). Для прототипа это принято сознательно и отмечено в отчёте;
закрывается пинингом IP на соединение при переходе в сервис.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import time
import unicodedata
import urllib.robotparser as robotparser
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
