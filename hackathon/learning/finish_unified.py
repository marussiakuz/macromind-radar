"""Resumable acceptance commands for the unified pipeline. All paid calls use its ledger."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from radar.config import Settings, Limits, load_env_file
from radar.ledger import shared, _atomic_write


def spent(): return shared().remaining()['spent']


def cards(run, limit):
    os.environ['RADAR_FILTER_LIMIT'] = str(limit)
    from radar.server import build_cards, CARDS_VERSION
    from radar.search import MultiSearch, YandexSearch
    manifest = json.loads((run / 'manifest.json').read_text())
    before, started = spent(), time.monotonic()
    class Job(dict):
        def __setitem__(self, k, v):
            super().__setitem__(k, v)
            if k == 'stage':
                _atomic_write(run / 'cards-progress.json', {'stage': v, 'elapsed_s': round(time.monotonic()-started),
                              'spent': spent(), 'at': datetime.now(timezone.utc).isoformat()})
                print(v, flush=True)
    job = Job(query=manifest['query'], run_id=run.name)
    searcher = MultiSearch(YandexSearch(Settings(), cache_dir=run / 'search'))
    try:
        trends = build_cards(run, job, searcher)
    finally:
        searcher.close()
    counters = manifest['counters']
    job.update(version=CARDS_VERSION, trends=trends,
               funnel={'queries': counters.get('queries', 0), 'hits': counters.get('hits', 0),
                       'urls': counters.get('unique_urls', 0), 'documents': counters.get('parsed_ok', 0),
                       'candidates': counters.get('after_merge', 0), 'top': len(trends)},
               elapsed_s=round(time.monotonic()-started, 2),
               card_stage_cost=job.get('card_stage_cost', {'scope': 'unattributed'}))
    _atomic_write(run / 'cards.json', job)
    print(json.dumps({'run': str(run), 'top': len(trends), 'assessment': job.get('assessment'),
                      'filters': job.get('filters'), 'cost': job['card_stage_cost']}, ensure_ascii=False), flush=True)


def controls():
    from radar.extract import YandexLLM
    from radar.search import YandexSearch
    from radar.fetch import Fetcher
    from radar.sequential import run_filters
    run = ROOT / 'radar-runs/acceptance-controls-20260929'
    run.mkdir(exist_ok=True)
    pool = [{'name_ru': name, 'name_orig': name, 'mechanism': mech, 'object_affected': obj,
             'area': 'negative_controls', 'evidence': []} for name, mech, obj in [
        ('Kubernetes', 'orchestration of containerized applications in production clusters', 'containerized applications'),
        ('MQTT', 'publish-subscribe message delivery in IoT networks', 'IoT messages'),
        ('TLS 1.3', 'authenticated encrypted network connections with the TLS 1.3 protocol', 'network connections')]]
    _atomic_write(run/'controls.json', pool)
    before = spent()
    settings = Settings(); searcher = YandexSearch(settings, cache_dir=run/'search')
    with Fetcher(settings, raw_dir=run/'raw') as fetcher:
        outcome = run_filters(pool, run, '2026-09-29', YandexLLM(settings, max_tokens=2200),
                               limit=3, searcher=searcher, fetcher=fetcher)
    searcher.close()
    result = {'summary': outcome.summary, 'cost': {k:spent()[k]-before[k] for k in before},
              'per_candidate': [{'name':c['name_ru'], 'maturity': d.get('maturity',{})}
                                for c,d in zip(pool, [outcome.decisions.get(__import__('radar.sequential',fromlist=['candidate_key']).candidate_key(c),{}) for c in pool])],
              'note': 'Three known broad controls; not a statistical validation or a test of narrower descendants.'}
    _atomic_write(run/'audit.json',result)
    print(json.dumps({'summary':outcome.summary,'cost':result['cost']},ensure_ascii=False))


def pool(area, direction, queries, packets):
    from radar.pipeline import run_pool
    before = spent()
    settings = Settings(limits=Limits(discovery_queries=queries, extraction_packets=packets))
    run = run_pool(area, direction, 'live', settings, plan='tree')
    _atomic_write(run/'pool-cost.json', {'cost':{k:spent()[k]-before[k] for k in before},
                                       'queries_limit':queries, 'extraction_packets':packets})
    print('RUN_DIRECTORY=' + str(run), flush=True)
    return run


def batch_remaining():
    targets = [('Защита ИИ','Защита систем искусственного интеллекта: безопасность моделей, данных и агентных приложений'),
               ('Финтех','Финансовые технологии: платежи, кредитование, инвестиции, банковские операции и регуляторные технологии'),
               ('Индустриальный ИИ','Индустриальный искусственный интеллект для производства, управления процессами и инженерии'),
               ('Инфраструктура ИИ','Инфраструктура искусственного интеллекта: вычисления, хранение, сети, обучение и обслуживание моделей')]
    report = ROOT/'radar-runs/acceptance-six-areas-20260929.json'
    completed = json.loads(report.read_text()) if report.exists() else []
    for area, direction in targets:
        if any(r['area']==area and r.get('cards_done') for r in completed):continue
        ledger=json.loads((ROOT/'radar-runs/ledger.json').read_text());grant=ledger['active_campaign']
        left=grant['limits']['llm']-(ledger['spent']['llm']-grant['opening_spent']['llm'])
        if left < 25:
            print('STOP: campaign model reserve below 25 RUB',flush=True);break
        prior=next((r for r in completed if r['area']==area and r.get('run')),None)
        run=Path(prior['run']) if prior else pool(area,direction,40,28)
        row=prior or {'area':area,'run':str(run),'cards_done':False}
        if not prior:completed.append(row)
        _atomic_write(report,completed)
        try:
            cards(run,8)
            row['cards_done']=True
        except Exception as exc:
            row['error']=type(exc).__name__
            print('CARD_ERROR',area,type(exc).__name__,flush=True)
        _atomic_write(report,completed)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd',required=True)
    c=sub.add_parser('cards'); c.add_argument('--run',type=Path,required=True); c.add_argument('--limit',type=int,default=15)
    sub.add_parser('controls')
    sub.add_parser('batch')
    p=sub.add_parser('pool'); p.add_argument('--area',required=True);p.add_argument('--direction',required=True)
    p.add_argument('--queries',type=int,default=48);p.add_argument('--packets',type=int,default=40)
    args=ap.parse_args(); load_env_file()
    if args.cmd=='cards': cards(args.run,args.limit)
    elif args.cmd=='controls': controls()
    elif args.cmd=='batch': batch_remaining()
    else: pool(args.area,args.direction,args.queries,args.packets)
