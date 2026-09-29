"""Грубая классификация доменов найденных источников для диагностики поиска."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from urllib.parse import urlparse

from .config import RUNS_DIR

PRIMARY = re.compile(r"(arxiv\.org|openreview|acm\.org|ieee|nist\.gov|europa\.eu|iso\.org|ietf\.org|"
                     r"nvd\.nist|cve\.org|github\.com|huggingface\.co|openai\.com|anthropic\.com|"
                     r"google|microsoft|cloudflare|nvidia|aws\.amazon|cisa\.gov|owasp\.org|mitre\.org)")
NEWSY = re.compile(r"(techcrunch|venturebeat|reuters|bloomberg|calcalistech|darkreading|theregister|"
                   r"zdnet|forbes|axios|ft\.com|wsj|habr\.com|dev\.to|medium\.com)")
FARM = re.compile(r"(growthlist|pitchwise|roundfunded|seedtable|spectup|eu-startups|datapile|basg\.co|"
                  r"futureagi|securityelites|grieccotech|unite\.ai|aiagentsquare|intelscroll|"
                  r"nerdleveltech|thestackunderflow|securitywall|hub\.causo|ai-manual)")
SOCIAL = re.compile(r"(youtube|linkedin|twitter|x\.com|reddit|facebook|tiktok)")

LAYERS = ((PRIMARY, "первоисточник"), (SOCIAL, "видео/соцсети"),
          (FARM, "SEO-подборки"), (NEWSY, "СМИ/блоги"))


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def layer_of(host: str) -> str:
    """Первое совпадение по порядку LAYERS. Порядок важен: github.com — первоисточник,
    даже если когда-нибудь попадёт и в другой список."""
    for rx, name in LAYERS:
        if rx.search(host):
            return name
    return "прочее"


def live_runs(area_slug: str):
    for run in sorted(RUNS_DIR.glob(f"2026*-{area_slug}")):
        manifest = run / "manifest.json"
        if not manifest.exists():
            continue
        if json.loads(manifest.read_text(encoding="utf-8")).get("mode") != "live":
            continue
        yield run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar.hoststats")
    parser.add_argument("--area", default="защита", help="часть имени прогона, например «защита»")
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args(argv)

    hosts, layers, per_lens, cand_layers = Counter(), Counter(), {}, Counter()
    runs = list(live_runs(args.area))
    for run in runs:
        hits_file = run / "hits.jsonl"
        if hits_file.exists():
            for line in hits_file.read_text(encoding="utf-8").splitlines():
                hit = json.loads(line)
                host = host_of(hit["url"])
                layer = layer_of(host)
                hosts[host] += 1
                layers[layer] += 1
                per_lens.setdefault(hit.get("lens", "?"), Counter())[layer] += 1
        cand_file = run / "candidates.jsonl"
        if cand_file.exists():
            for line in cand_file.read_text(encoding="utf-8").splitlines():
                cand_layers[layer_of(host_of(json.loads(line)["source_url"]))] += 1

    total = sum(layers.values())
    if not total:
        print(f"Нет живых прогонов по «{args.area}» в {RUNS_DIR}")
        return 1
    print(f"Прогонов: {len(runs)} ({', '.join(r.name for r in runs)})")
    print(f"Позиций выдачи: {total}, разных хостов: {len(hosts)}\n")
    print("Слои выдачи:")
    for layer, n in layers.most_common():
        print(f"  {n:5d}  {100 * n / total:5.1f}%  {layer}")

    print("\nПо линзам:")
    for lens, counter in sorted(per_lens.items()):
        t = sum(counter.values())
        print(f"  {lens:9s} {t:4d} позиций | первоисточники {100 * counter['первоисточник'] / t:5.1f}%"
              f" | SEO-подборки {100 * counter['SEO-подборки'] / t:5.1f}%"
              f" | видео/соцсети {100 * counter['видео/соцсети'] / t:5.1f}%")

    tc = sum(cand_layers.values())
    if tc:
        print(f"\nОткуда пришли кандидаты ({tc}):")
        for layer, n in cand_layers.most_common():
            print(f"  {n:5d}  {100 * n / tc:5.1f}%  {layer}")

    print(f"\nТоп-{args.top} хостов:")
    for host, n in hosts.most_common(args.top):
        print(f"  {n:4d}  {layer_of(host):14s}  {host}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
