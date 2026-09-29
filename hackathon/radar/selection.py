"""Offline document selection. Retrieval provenance is not semantic validation."""
from __future__ import annotations

from collections import Counter, defaultdict
import re
from urllib.parse import unquote, urlsplit

from .hoststats import host_of, layer_of

VERSION = "selection/2"
_STOP = set("the and for with from this that using based into on of to in a an as by is are "
            "technology technologies research review system systems для или при это как из на по".split())


def terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[\w]+", text.casefold()) if len(w) > 2 and w not in _STOP}


def url_key(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


def source_unit(url: str) -> str:
    """Shared repositories are not single publishers; ordinary sites keep a host cap."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = unquote(parts.path).strip("/")
    if host in {"doi.org", "dx.doi.org"} and re.match(r"10\.\d{4,9}/\S+", path):
        return "doi:" + path.casefold()
    if host in {"arxiv.org", "export.arxiv.org"}:
        paper = re.sub(r"^(?:abs|pdf|html)/", "", path)
        paper = re.sub(r"(?:v\d+)?(?:\.pdf)?$", "", paper)
        if re.fullmatch(r"\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7}", paper):
            return "arxiv:" + paper
    if host == "openalex.org" and re.fullmatch(r"W\d+", path):
        return "openalex:" + path
    if host == "github.com" and len(path.split("/")) >= 2:
        return "github:" + "/".join(path.casefold().split("/")[:2])
    return "host:" + host


def document_source_unit(doc) -> str:
    original, final = source_unit(doc.url), source_unit(doc.final_url or doc.url)
    return original if not original.startswith("host:") else final


def useful_text(text: str) -> bool:
    """Reject clear navigation shells, not short scientific abstracts."""
    boilerplate = re.compile(
        r"^(?:IEEE Account|Change Username/Password|Purchase Details|Payment Options|"
        r"Order History|View Purchased Documents|Profile Information|Communications Preferences|"
        r"Profession and Education|Technical Interests|Need Help|US & Canada|Worldwide|"
        r"Contact & Support|About IEEE Xplore|Contact Us|Help|Accessibility|Terms of Use|"
        r"Nondiscrimination Policy|IEEE Ethics Reporting|Sitemap|Privacy & Opting Out|"
        r"A not-for-profit organization, IEEE is the world's largest technical professional organization|"
        r"Copyright|©|All rights reserved)", re.I)
    content = " ".join(line.strip() for line in text.splitlines()
                       if line.strip() and not boilerplate.search(line.strip()))
    return len(content) >= 160 and len(terms(content)) >= 6


def document_contexts(docs, hits, tree=None):
    """Keep *every* query/leaf link, including links through redirected URLs."""
    query_groups = defaultdict(set)
    order = []
    if tree:
        order = [leaf["id"] for leaf in tree["leaves"]]
        for q in tree.get("queries", []):
            query_groups[q["query"]].add(q["leaf_id"])
    urls = defaultdict(lambda: {"queries": set(), "groups": set(), "position": 9999})
    for h in hits:
        groups = query_groups[h.query] or {h.query}
        if not tree and h.query not in order:
            order.append(h.query)
        item = urls[url_key(h.url)]
        item["queries"].add(h.query)
        item["groups"].update(groups)
        item["position"] = min(item["position"], h.position)
    contexts = {}
    for d in docs:
        matches = [urls[url_key(u)] for u in (d.url, d.final_url)]
        contexts[d.url] = {
            "queries": sorted(set().union(*(m["queries"] for m in matches))),
            "groups": sorted(set().union(*(m["groups"] for m in matches))) or ["unassigned"],
            "position": min(m["position"] for m in matches),
        }
    for c in contexts.values():
        for group in c["groups"]:
            if group not in order:
                order.append(group)
    return contexts, order


def select_documents(docs, hits, limit, tree=None, max_per_source=None, min_published=None):
    """One document per unrepresented leaf, then balanced additional evidence.

    `max_per_source` и `min_published` по умолчанию берутся из настроек, то есть из
    окружения: «полный» режим включается переменными, без правки кода.
    """
    from .config import Limits
    lim = Limits()
    if max_per_source is None:
        max_per_source = lim.max_per_source
    if min_published is None:
        min_published = lim.min_published
    contexts, order = document_contexts(docs, hits, tree)
    queues = defaultdict(list)
    decisions = {}
    for i, d in enumerate(docs):
        ctx = contexts[d.url]
        decisions[d.url] = {"url": d.url, **ctx, "source_unit": document_source_unit(d),
                            "selected": False, "reason": "packet_limit"}
        if not useful_text(d.text):
            decisions[d.url]["reason"] = "insufficient_content"
            continue
        # Отсечка по дате публикации. Документы без даты остаются: дата известна меньше
        # чем у половины корпуса (29.09.2026: 74 из 161 на Edge), и отбрасывать их —
        # значит терять сигналы, а не старьё.
        published = (getattr(d, "published_at", "") or "")[:10]
        if min_published and published and published < min_published:
            decisions[d.url]["reason"] = "older_than_cutoff"
            decisions[d.url]["published_at"] = published
            continue
        title, body = terms(d.title), terms(d.text)
        relevance = max((len(terms(q) & body) / max(1, len(terms(q))) +
                         .5 * len(terms(q) & title) / max(1, len(terms(q)))
                         for q in ctx["queries"]), default=0)
        primary = d.parser_version.startswith("openalex") or layer_of(host_of(d.url)) == "первоисточник"
        rank = (-relevance, not primary, ctx["position"], i)
        for group in ctx["groups"]:
            queues[group].append((rank, d))
    for queue in queues.values():
        queue.sort(key=lambda pair: pair[0])
    picked, seen_hashes, seen_urls = [], set(), set()
    source_used, group_used = Counter(), Counter()
    order_index = {g: i for i, g in enumerate(order)}
    while len(picked) < max(0, limit):
        progress = False
        for group in sorted(order, key=lambda g: (group_used[g], order_index[g])):
            if len(picked) >= limit:
                break
            queue = queues[group]
            while queue:
                rank, d = queue.pop(0)
                row = decisions[d.url]
                if d.url in seen_urls:
                    continue
                if d.text_sha256 in seen_hashes:
                    row["reason"] = "duplicate_text"
                    continue
                if source_used[row["source_unit"]] >= max_per_source:
                    row["reason"] = "source_quota"
                    continue
                # Another leaf may already have received this document's shared context.
                if group_used[group] > min((group_used[g] for g in order if queues[g]), default=group_used[group]):
                    queue.insert(0, (rank, d))
                    break
                picked.append(d)
                seen_urls.add(d.url); seen_hashes.add(d.text_sha256)
                source_used[row["source_unit"]] += 1
                group_used.update(row["groups"])
                row.update(selected=True, reason="selected")
                progress = True
                break
        if not progress:
            break
    return picked, {"version": VERSION, "documents": list(decisions.values()),
                    "group_document_counts": dict(group_used),
                    "unrepresented_groups": [g for g in order if not group_used[g]],
                    "note": "Retrieval provenance only; not verified mechanism coverage."}
