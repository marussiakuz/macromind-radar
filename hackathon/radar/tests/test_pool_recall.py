"""Recall regressions: evidence remains exact, and work stays within bounded quotas."""
import hashlib
import json
from dataclasses import replace

import pytest

from radar.config import DocumentSnapshot, SearchHit, Settings, Limits
from radar.extract import Span, make_spans, parse_extraction
from radar.passages import all_spans
from radar.selection import select_documents, source_unit, document_contexts
from radar.discovery import search_tree
from radar.versioning import pool_signature


def doc(text, url='https://example.org/doc', title='Specific mechanism'):
    return DocumentSnapshot(url=url, final_url=url, title=title, text=text,
                            text_sha256=hashlib.sha256(text.encode()).hexdigest())


def hit(url, query, position=1):
    return SearchHit(url=url, query=query, position=position, lang='en', lens='mechanism')


def answer(d, quote, span='s1'):
    return json.dumps({'document_id':d.text_sha256[:16], 'has_more_candidates':False,
        'candidates':[{'name_ru':'technology', 'mechanism':'specific mechanism',
                       'evidence':[{'span_id':span,'quote':quote}]}]})


def test_split_ellipsis_keeps_only_exact_ordered_fragments_with_offsets():
    a = 'The controller performs inference on a low power microcontroller.'
    b = 'The hardware accelerator computes matrix products in local memory.'
    d = doc(a + ' Additional implementation details are available. ' + b)
    spans = [Span('s1', d.title, d.text, 0, len(d.text))]
    r = parse_extraction(d, answer(d, a + ' ... ' + b), spans)
    assert len(r.candidates) == 1
    assert [e.quote for e in r.candidates[0].evidence] == [a, b]
    assert r.diagnostics[0]['repairs'][0]['method'] == 'split_ellipsis'
    for e in r.candidates[0].evidence:
        assert d.text[e.start:e.end] == e.quote


@pytest.mark.parametrize('bad', [
    'This completely invented statement describes a new device.',
    'The actual device uses a local hardware accelerator. ... It cures all known diseases without any tests.',
    'first ... device',
    'The second statement is also present in the source. ... The actual device uses a local hardware accelerator.',
])
def test_repair_never_accepts_invention_short_fragments_or_reversed_order(bad):
    d=doc('The actual device uses a local hardware accelerator. The second statement is also present in the source.')
    assert not parse_extraction(d, answer(d,bad), [Span('s1',d.title,d.text)]).candidates


def test_quote_cannot_migrate_from_another_span_or_document():
    d=doc('The actual device uses a local hardware accelerator. Another passage describes a completely different mechanism.')
    spans=[Span('s1',d.title,'Another passage describes a completely different mechanism.')]
    assert not parse_extraction(d,answer(d,'The actual device uses a local hardware accelerator.'),spans).candidates
    data=json.loads(answer(d,spans[0].text));data['document_id']='another-document'
    assert not parse_extraction(d,json.dumps(data),spans).candidates


def test_malformed_model_rows_are_logged_not_crashes():
    d=doc('A long enough sentence describing an actual technological mechanism for a test.')
    data={'document_id':d.text_sha256[:16], 'candidates':[None, {'name_ru':'a','mechanism':'b','evidence':'bad'}]}
    r=parse_extraction(d,json.dumps(data),make_spans(d))
    assert not r.candidates
    assert len(r.diagnostics)==2


def test_relevant_tail_is_read_and_every_window_has_exact_offsets():
    text='\n'.join(f'Chapter {i}: General background on manufacturing systems and operation. ' * 12 for i in range(40))
    target='The zeta actuator deploys magnetostrictive feedback inside the ceramic housing.'
    d=doc(text+'\n'+target)
    spans=make_spans(d,queries=['zeta actuator magnetostrictive feedback'])
    assert len(spans)<=12
    assert any(target in s.text for s in spans)
    assert all(s.text==d.text[s.start:s.end] and len(s.text)<=1200 for s in spans)
    second=make_spans(d,queries=['zeta actuator magnetostrictive feedback'],exclude_ids=[s.span_id for s in spans])
    assert not ({s.span_id for s in spans}&{s.span_id for s in second})
    assert len(all_spans(d))>12


def test_repositories_have_independent_units_but_versions_do_not():
    assert source_unit('https://doi.org/10.1234/a')!=source_unit('https://doi.org/10.1234/b')
    assert source_unit('https://arxiv.org/pdf/2601.12345v2.pdf')==source_unit('https://arxiv.org/abs/2601.12345v1')
    assert source_unit('https://github.com/org/a')!=source_unit('https://github.com/org/b')
    assert source_unit('https://example.org/a')==source_unit('https://example.org/b')


def test_leaf_selection_does_not_let_aliases_starve_another_leaf():
    qs=['aaa magnetic actuator','aab magnetic actuator','zzz ceramic sensor']
    ds=[doc((q+' operates a distinct device using measured feedback. ')*5,
            f'https://site{i}.org/doc',q) for i,q in enumerate(qs)]
    hs=[hit(d.url,q) for d,q in zip(ds,qs)]
    tree={'leaves':[{'id':'actuator'},{'id':'sensor'}], 'queries':[
        {'query':q,'leaf_id':'actuator' if i<2 else 'sensor'} for i,q in enumerate(qs)]}
    chosen,report=select_documents(ds,hs,2,tree)
    assert ds[2] in chosen and len(chosen)==2
    assert report['unrepresented_groups']==[]


def test_multiple_query_links_and_redirects_are_retained():
    d=doc('A sensor detects pressure through a local acoustic mechanism. '*5)
    d.final_url='https://new.example.org/doc'
    ctx,_=document_contexts([d],[hit(d.url,'first query'),hit(d.final_url,'second query')])
    assert ctx[d.url]['queries']==['first query','second query']


def test_redirects_preserve_paper_identity_and_candidate_provenance():
    from radar.selection import document_source_unit
    from radar.discovery import attach_document_coverage
    from radar.config import Candidate, Evidence
    d=doc('A sensor detects pressure through an acoustic mechanism. '*5,'https://doi.org/10.1234/paper')
    d.final_url='https://publisher.org/article'
    assert document_source_unit(d)=='doi:10.1234/paper'
    tree={'queries':[{'query':'acoustic sensor','leaf_id':'sensor'}],'coverage':{}}
    c=Candidate(name_ru='sensor',mechanism='acoustics',evidence=[Evidence(quote='sensor')],
                source_url=d.final_url,document_sha256=d.text_sha256)
    attach_document_coverage(tree,[d],[hit(d.url,'acoustic sensor')],[d],[c])
    assert tree['coverage']['leaf_ids_by_stage']['candidates']==['sensor']


def test_scientific_papers_not_capped_as_one_host_and_shell_not_selected():
    ds=[doc((f'Mechanism {i} processes acoustic signals in a battery operated sensor. ')*5,
            f'https://doi.org/10.1234/{i}',f'Mechanism {i}') for i in range(6)]
    shell=doc(('IEEE Account\nChange Username/Password\nPurchase Details\nContact & Support\n') +
              "A not-for-profit organization, IEEE is the world's largest technical professional organization "
              "dedicated to advancing technology for the benefit of humanity.© Copyright 2026 IEEE - All rights reserved.",
              'https://ieeexplore.ieee.org/shell')
    chosen,report=select_documents(ds+[shell],[hit(d.url,d.title) for d in ds+[shell]],7)
    assert len(chosen)==6 and shell not in chosen
    assert report['documents'][-1]['reason']=='insufficient_content'


def test_ordinary_source_cap_and_duplicate_text_still_apply():
    # Квота на обычный сайт задаётся явно: с 29.09.2026 по умолчанию она снята
    # (RADAR_MAX_PER_SOURCE=999), потому что решено читать весь скачанный корпус, а
    # единственным отсевом оставить дату публикации. Механизм квоты при этом обязан
    # работать — его и проверяем, а не значение по умолчанию.
    ds=[doc((f'Mechanism {i} processes acoustic signals in a different sensor. ')*5,
            f'https://example.org/{i}') for i in range(5)]
    duplicate=ds[0].model_copy(update={'url':'https://other.org/copy','final_url':'https://other.org/copy'})
    chosen,_=select_documents(ds+[duplicate],[hit(d.url,'acoustic signals') for d in ds+[duplicate]],10,
                              max_per_source=3)
    assert len(chosen)==3


def test_duplicate_text_is_dropped_even_without_source_cap():
    # Со снятой квотой повтор текста остаётся единственной защитой от того, чтобы одна и
    # та же статья с двух адресов читалась дважды за деньги.
    ds=[doc((f'Mechanism {i} processes acoustic signals in a different sensor. ')*5,
            f'https://example.org/{i}') for i in range(5)]
    duplicate=ds[0].model_copy(update={'url':'https://other.org/copy','final_url':'https://other.org/copy'})
    chosen,report=select_documents(ds+[duplicate],[hit(d.url,'acoustic signals') for d in ds+[duplicate]],10)
    assert len(chosen)==5
    reasons={row['url']:row['reason'] for row in report['documents']}
    assert reasons['https://other.org/copy']=='duplicate_text'


def test_search_spends_unused_recovery_slots_on_other_aliases_within_limit():
    tree={'leaves':[{'id':str(i),'en':f'mechanism {i}','parent':'b','aliases':[f'alias {i}',f'other {i}']}
                    for i in range(5)],'errors':[]}
    class Search:
        calls=0
        def search(self,q,lang,lens,count):
            self.calls+=1
            return [hit(f'https://example.org/{self.calls}/{i}',q) for i in range(5)]
    s=Search();search_tree(tree,s,9,5)
    assert s.calls==9
    assert len({(q['query'],q['lens']) for q in tree['queries']})==9
    assert tree['coverage']['searched']==5


def test_cached_pool_requires_matching_pipeline_limits_and_plan(tmp_path,monkeypatch):
    from radar import server
    settings=Settings()
    p=tmp_path/'20260929-000001-edge';p.mkdir();(p/'candidates.jsonl').write_text('')
    m={'mode':'live','query':'Edge','area':'Edge'};(p/'manifest.json').write_text(json.dumps(m))
    monkeypatch.setattr(server,'RUNS_DIR',tmp_path)
    assert server.cached_run('Edge',settings=settings) is None
    assert server.cached_run('Edge',settings=settings,allow_legacy=True)==p
    m.update(pool_signature=pool_signature(settings,'tree'),execution_complete=True)
    (p/'manifest.json').write_text(json.dumps(m))
    assert server.cached_run('Edge',settings=settings)==p
    assert server.cached_run('Edge',settings=replace(settings,limits=Limits(extraction_packets=28))) is None
    assert server.cached_run('Edge',settings=settings,plan='mixed') is None
    m['execution_complete']=False;(p/'manifest.json').write_text(json.dumps(m))
    assert server.cached_run('Edge',settings=settings) is None
    assert server.cached_run('Edge',settings=settings,allow_legacy=True)==p


def test_pipeline_continuation_and_journal_share_packet_budget(tmp_path,monkeypatch):
    from radar import pipeline,discovery
    from radar.config import FetchResult
    documents={f'https://example{i}.org/doc':doc(
        f'The sensor number {i} measures acoustic patterns using local processing and feedback. '*5,
        f'https://example{i}.org/doc') for i in range(5)}
    class Search:
        snapshots={};calls=0
        def search(self,q,lang,lens,count):
            self.calls+=1
            return [hit(url,q) for url in documents]
    class Fetch:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def fetch(self,url):return FetchResult(url=url,final_url=url,status='ok'),b'body'
    class Model:
        calls=0
        def complete(self,system,payload):
            self.calls+=1
            quote=payload['spans'][0]['text'][:70]
            return json.dumps({'document_id':payload['manifest']['document_id'],
                'has_more_candidates':not payload['existing_candidates'],
                'candidates':[{'name_ru':f'candidate {self.calls}','mechanism':'a specific mechanism',
                    'evidence':[{'span_id':payload['spans'][0]['span_id'],'quote':quote}]}]}),10,10
    search=Search();model=Model()
    monkeypatch.setattr(pipeline,'YandexSearch',lambda *a,**kw:search)
    monkeypatch.setattr(pipeline,'MultiSearch',lambda *a,**kw:search)
    monkeypatch.setattr(pipeline,'OpenAlexSearch',lambda:None)
    monkeypatch.setattr(pipeline,'YandexLLM',lambda *a,**kw:model)
    monkeypatch.setattr(pipeline,'Fetcher',Fetch)
    monkeypatch.setattr(pipeline,'parse_document',lambda body,url,*a:documents[url])
    monkeypatch.setattr(discovery,'plan_tree',lambda *a:{'version':'test','leaves':[
        {'id':'leaf','en':'acoustic sensors','parent':'b','aliases':[]}], 'errors':[]})
    settings=Settings(yandex_api_key='test',yandex_folder_id='test',limits=Limits(
        extraction_packets=5,fetch_attempts=5,discovery_queries=1))
    p=pipeline.run_pool('','acoustic sensors','live',settings,runs_dir=tmp_path)
    records=[json.loads(l) for l in (p/'extraction-results.jsonl').read_text().splitlines()]
    assert model.calls==5 and len(records)==5
    assert any(r['continuation'] for r in records)
    assert all(r['diagnostics'][0]['accepted'] for r in records)
    assert json.loads((p/'manifest.json').read_text())['pool_signature']==pool_signature(settings)
    assert len(json.loads((p/'extraction-selection.json').read_text()))<5
