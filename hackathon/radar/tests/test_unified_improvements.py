import json
from pathlib import Path
import pytest

from radar.ledger import Ledger, LimitReached
from radar.discovery import build_tree_queries, interleave, search_tree
from radar.rank import score_candidate, LOUD_MAX


def test_ledger_corruption_never_restores_budget(tmp_path):
    p = tmp_path / 'ledger.json'
    for invalid in ('{broken', 'null', '{}'):
        p.write_text(invalid)
        with pytest.raises(RuntimeError): Ledger(p).remaining()
        assert p.read_text() == invalid


def test_reservations_same_second_and_retries(tmp_path, monkeypatch):
    monkeypatch.setattr('radar.ledger._now', lambda: 'same-second')
    ledger = Ledger(tmp_path / 'ledger.json')
    start = ledger.remaining()
    a = ledger.reserve(10, 'search'); b = ledger.reserve(5, 'llm')
    assert a.reservation_id != b.reservation_id
    ledger.settle(a, 2); ledger.settle(a, 2); ledger.settle(b, 5)
    end = ledger.remaining()
    assert end['search'] == start['search'] - 2
    assert end['llm'] == start['llm'] - 5
    records = json.loads(ledger.path.read_text())['calls']
    assert [r['actual'] for r in records] == [2, 5]
    assert all(r['status'] == 'settled' for r in records)


def test_authorization_idempotent_and_cycle_cap(tmp_path):
    ledger = Ledger(tmp_path / 'ledger.json')
    before = ledger.remaining()
    ledger.authorize('grant', 5, 5, 'test')
    ledger.authorize('grant', 5, 5, 'test retry')
    assert ledger.remaining()['search'] == before['search'] + 5
    ledger.reserve(5, 'search')
    with pytest.raises(LimitReached): ledger.reserve(.01, 'search')
    with pytest.raises(ValueError): ledger.reserve(-1, 'search')


@pytest.mark.parametrize('stage,first,total,recent', [
    ('prototype', '1950-01-01', 10000, 0), ('scaled', '2026-06-01', 10000, 100),
    ('scaled', '2026-06-01', LOUD_MAX//4+1, 50)])
def test_age_and_volume_are_not_proof(stage, first, total, recent):
    class Probe:
        def probe(self, _): return first, total, recent
    candidate = {'name_ru': 'механизм', 'name_orig': 'mechanism', 'mechanism': 'mechanism',
                 'stage': stage, 'organizations': [], 'source_url': 'https://example.org',
                 'evidence': [{'quote': 'A mechanism acts on a specific device.'}]}
    assert score_candidate(candidate, Probe()).tier == 'review'
    assert score_candidate({**candidate, 'evidence': []}, Probe()).tier == 'rejected'


def test_tree_visits_every_leaf_before_aliases():
    tree = {'leaves': [{'id': str(i), 'en': f'mechanism {i}', 'parent': 'b',
                         'aliases': [f'alternative {i}']} for i in range(8)]}
    q = build_tree_queries(tree, 12)
    assert len(q) == 12
    assert {r['leaf_id'] for r in q[:8]} == {str(i) for i in range(8)}
    assert all(r['depth'] == 0 for r in q[:8])
    assert interleave([[1, 3], [2, 4, 5]]) == [1, 2, 3, 4, 5]


def test_zero_results_retry_is_bounded():
    class Search:
        calls = 0
        def search(self, *args): self.calls += 1; return []
    tree = {'leaves': [{'id': str(i), 'en': f'topic {i}', 'parent': 'b',
                         'aliases': [f'alias {i}']} for i in range(3)], 'errors': []}
    search = Search()
    search_tree(tree, search, 6, 10)
    assert search.calls <= 6
    assert tree['coverage']['searched'] == 3
    assert tree['coverage']['with_hits'] == 0


def test_extra_evidence_cache_bound_to_base_and_full_packet():
    from radar.maturity import packet, decide, stored_decision
    c = {'name_ru': 'specific mechanism', 'evidence': [{'quote': 'Specific mechanism is being evaluated in a prototype.',
                                                     'source_url': 'https://example.org'}]}
    extra = [{'quote': 'Operators independently report production deployments of this mechanism.', 'url': 'https://operator.example'}]
    data = packet(c, '2026-09-29', extra)
    result = decide(data)
    result.update(base_input_hash=packet(c, '2026-09-29')['input_hash'], packet=data)
    assert stored_decision(c, result, '2026-09-29') is not None
    assert stored_decision({**c, 'name_ru': 'another mechanism'}, result, '2026-09-29') is None
    result['packet']['evidence'][-1]['quote'] = 'tampered'
    assert stored_decision(c, result, '2026-09-29') is None


def test_early_assessment_requires_exact_bound_quote():
    from radar.assessment import validate, priority
    c = {'evidence': [{'quote': 'We demonstrate a first working prototype with a measured new mechanism.'}]}
    row = {'domain': 'yes', 'stage': 'early', 'delta': 'A concrete new technical mechanism',
           'quote': 'We demonstrate a first working prototype', 'evidence_index': 0}
    assert validate(row, c)['stage'] == 'early'
    assert validate({**row, 'quote': 'An invented prototype announcement'}, c)['stage'] == 'unknown'
    assert validate({**row, 'evidence_index': -1}, c)['stage'] == 'unknown'
    assert priority({'domain':'yes', 'stage':'unknown'}, 0) > priority({'domain':'no', 'stage':'early'}, 100)


def test_partial_dates_do_not_crash_or_hide_uncertainty():
    from radar.server import recent_event
    from radar.assessment import dated_assessment
    assert recent_event('2025','2026-09-29')
    assert recent_event('2025-02','2026-09-29')
    assert not recent_event('2027','2026-09-29')
    assert not recent_event('bad','2026-09-29')
    a={'stage':'early'}
    assert dated_assessment(a,None,None,'2026-09-29')['stage']=='unknown'
    assert dated_assessment(a,'2010-01-01',None,'2026-09-29')['stage']=='unknown'
    assert dated_assessment(a,'2025-01-01',None,'2026-09-29')['stage']=='early'


def test_date_bounds_invalid_and_leap_month():
    from radar.maturity import date_bounds
    assert str(date_bounds('2024-02')[1]) == '2024-02-29'
    assert str(date_bounds('2025-02')[1]) == '2025-02-28'
    assert date_bounds('0000') is None
    assert date_bounds('2025-13') is None


def test_filter_residual_includes_unchecked():
    from radar.sequential import FilterOutcome
    result = FilterOutcome(remaining=[{}], unchecked=[{}, {}], mature=[{}])
    assert result.summary['пул'] == 4
    assert result.summary['осталось кандидатов'] == 3
    assert result.summary['проверено и оставлено'] == 1


def test_repeated_click_reuses_running_job(monkeypatch):
    from radar import server
    started = []
    class Thread:
        def __init__(self, **kw): started.append(kw)
        def start(self): pass
    monkeypatch.setattr(server.threading, 'Thread', Thread)
    monkeypatch.setattr(server, 'JOBS', {})
    first = server.search(server.SearchRequest(query='Edge'))
    second = server.search(server.SearchRequest(query=' edge '))
    assert first['job_id'] == second['job_id']
    assert len(started) == 1
    assert server.search(server.SearchRequest(query='Роботы'))['job_id'] != first['job_id']


@pytest.mark.parametrize('provider', ['llm', 'search'])
def test_cache_only_blocks_network_and_reservations(tmp_path, monkeypatch, provider):
    from radar.config import Settings
    from radar import extract, search
    monkeypatch.setenv('RADAR_CACHE_ONLY', '1')
    monkeypatch.setattr(extract, 'RUNS_DIR', tmp_path)
    monkeypatch.setattr(search, 'RUNS_DIR', tmp_path)
    settings = Settings(yandex_api_key='test-only', yandex_folder_id='test-only')
    client = extract.YandexLLM(settings) if provider == 'llm' else search.YandexSearch(settings)
    def forbidden(*args, **kwargs): raise AssertionError('Network must not be attempted')
    monkeypatch.setattr(client._client, 'post', forbidden)
    with pytest.raises(LimitReached, match='cache-only'):
        if provider == 'llm': client.complete('test cache miss', {'x': 1})
        else: client.search('test cache miss', 'en', 'mechanism', 1)
    assert client.spent_rub == 0
    client._client.close()
