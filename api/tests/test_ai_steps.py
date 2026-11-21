from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_conflict_fixture_has_source_linked_placeholder_and_manual_review():
    response = client.post('/api/comparison/steps', json={
        'step': 'comparison',
        'lv': {'name': 'Synthetic bridge repair', 'quelle': 'synthetic:comparison-v1',
               'positionen': [{'oz': '01.001'}]},
        'specifications': [
            {'id': 'S10', 'oz': '01.001', 'text': '10 cm', 'source': 'user'},
            {'id': 'S12', 'oz': '01.001', 'text': '12 cm', 'source': 'internet'},
        ],
    })
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'placeholder'
    assert body['findings'] == []
    note = body['notes'][0]
    assert note['oz'] == '01.001' and note['id'] == 'Note1'
    assert note['placeholder'] and note['source'] == 'model_mock'
    assert note['manual_review']
    assert {item['reference_id'] for item in body['evidence']} == {'S10', 'S12'}


def test_missing_history_preserves_earlier_note_and_returns_structured_error():
    first = client.post('/api/comparison/steps', json={
        'step': 'comparison',
        'lv': {'name': 'Synthetic bridge repair', 'quelle': 'synthetic:comparison-v1',
               'positionen': [{'oz': '01.001'}]},
        'specifications': [
            {'id': 'S10', 'oz': '01.001', 'text': '10 cm', 'source': 'user'},
            {'id': 'S12', 'oz': '01.001', 'text': '12 cm', 'source': 'internet'},
        ],
    }).json()
    result = client.post('/api/comparison/steps', json={
        'step': 'historical_adjustment',
        'lv': {'name': 'Parsed plan', 'quelle': 'synthetic', 'positionen': [{'oz': '01.001'}]},
        'previous_notes': first['notes'],
    }).json()
    assert result['status'] == 'error' and result['notes'] == first['notes']
    assert result['errors'][0]['step'] == 'historical_adjustment'
    assert result['errors'][0]['code'] == 'history_unavailable'
    assert result['findings'] == [] and result['evidence'] == []


def contract_fixtures():
    import json
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / 'docs/comparison-api.md').read_text()
    block = text.split('<!-- contract-fixtures -->\n```json\n', 1)[1].split('\n```', 1)[0]
    return json.loads(block)


def test_documented_four_steps_accumulate_notes_with_distinct_estimate_pools():
    fixtures = contract_fixtures()
    previous = []
    results = []
    for step in ('comparison', 'standards', 'historical_adjustment', 'what_if'):
        request = fixtures[step]
        request['previous_notes'] = previous
        response = client.post('/api/comparison/steps', json=request)
        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'placeholder' and body['errors'] == []
        assert body['notes'][:-1] == previous
        previous = body['notes']
        results.append(previous[-1])
    assert [n['id'] for n in previous] == ['Note1', 'Note2', 'Note3', 'Note4']
    assert all(n['placeholder'] and n['manual_review'] and n['approval_required'] for n in results)
    assert 'no verified norm breach' in results[1]['text']
    assert {e['reference_id'] for e in results[1]['evidence']} == {'S10', 'S12'}
    assert results[2]['estimated_value'] == 60 and results[3]['estimated_value'] == 70
    assert results[2]['case_ids'] == ['H1', 'H2', 'H3']
    assert results[3]['case_ids'] == ['W1', 'W2', 'W3']
    for note in results[2:]:
        assert note['oz'] == '01.001' and note['case_count'] == 3
        assert note['base_value'] == 50 and note['unit'] == 'h'
        assert note['selection_reason'] and note['assumption'] and note['uncertainty']


def test_arbitrary_input_never_receives_fixed_domain_claims():
    request = contract_fixtures()['comparison']
    request['lv']['quelle'] = 'real-project.x83'
    body = client.post('/api/comparison/steps', json=request).json()
    assert body['status'] == 'error' and body['notes'] == [] and body['findings'] == []
    assert body['errors'][0]['code'] == 'placeholder_unavailable'
    request = contract_fixtures()['historical_adjustment']
    request['history_records'][0]['real_values'][0]['value'] = None
    body = client.post('/api/comparison/steps', json=request).json()
    assert body['status'] == 'error' and body['notes'] == []


def test_invalid_step_oz_and_ambiguous_ids_are_rejected():
    from copy import deepcopy

    original = contract_fixtures()['comparison']
    invalid = []
    for field, value in [('step', 'unsupported')]:
        request = deepcopy(original)
        request[field] = value
        invalid.append(request)
    request = deepcopy(original)
    request['specifications'][0]['oz'] = '99.999'
    invalid.append(request)
    request = deepcopy(original)
    request['lv']['positionen'][0]['oz'] = ' '
    invalid.append(request)
    request = deepcopy(original)
    request['lv']['positionen'].append({'oz': '01.001'})
    invalid.append(request)
    request = deepcopy(original)
    request['specifications'][1]['id'] = 'S10'
    invalid.append(request)
    request = contract_fixtures()['historical_adjustment']
    request['history_records'][1]['case_id'] = 'H1'
    invalid.append(request)
    for request in invalid:
        assert client.post('/api/comparison/steps', json=request).status_code == 422


def test_failed_step_preserves_notes_and_sanitizes_error(monkeypatch):
    from app.ai import step_api

    request = contract_fixtures()['comparison']
    notes = client.post('/api/comparison/steps', json=request).json()['notes']
    request['previous_notes'] = notes

    def failing_step(_request):
        raise RuntimeError('private-provider-error')

    monkeypatch.setattr(step_api, 'synthetic_note', failing_step)
    response = client.post('/api/comparison/steps', json=request)
    body = response.json()
    assert response.status_code == 200 and body['status'] == 'error'
    assert body['notes'] == notes and body['errors'][0]['code'] == 'step_failed'
    assert 'private-provider-error' not in response.text


def test_step_openapi_exposes_request_and_response_examples():
    schema = client.get('/openapi.json').json()
    assert schema['components']['schemas']['StepRequest']['examples'][0]['step'] == 'comparison'
    success = schema['paths']['/api/comparison/steps']['post']['responses']['200']
    assert success['content']['application/json']['example']['status'] == 'placeholder'


# --- #23: real adapters to the #19 (Notes 1/2) and #20 (Notes 3/4) contracts ------------------

import json as _json
import re as _re
from pathlib import Path as _Path

import pytest

_ROOT = _Path(__file__).resolve().parents[2]
SPEC = _json.loads((_ROOT / 'data/architektur/spezifikationen.json').read_text(encoding='utf-8'))
SPEC_SCENARIOS = {s['id']: s for s in SPEC['scenarios']}
EST = _json.loads((_ROOT / 'data/architektur/schaetzszenarien.json').read_text(encoding='utf-8'))
EST_SCENARIOS = {s['id']: s for s in EST['scenarios']}
CLAIM_WORDS = _re.compile(r'violat|breach|deviat|non-?complian|verstoß|verstoss', _re.IGNORECASE)


def source_request(step, scenario_id, **extra):
    from copy import deepcopy

    scenario = deepcopy(SPEC_SCENARIOS[scenario_id])
    return {'step': step, 'lv': scenario['lv'], 'sources': scenario['sources'],
            'checked_on': scenario['checked_on'], **extra}


def estimate_request(scenario_id, **extra):
    from copy import deepcopy

    scenario = deepcopy(EST_SCENARIOS[scenario_id])
    return {'step': scenario['expected_note']['step'], 'lv': deepcopy(SYNTHETIC_LV_FOR_ESTIMATES),
            'history_records': deepcopy(EST['history_pools'][scenario['history_pool']]),
            'estimates': [{'position': scenario['position'], 'assumptions': scenario['assumptions'],
                           'limit': scenario['limit']}], **extra}


SYNTHETIC_LV_FOR_ESTIMATES = {'name': 'Synthetic bridge repair', 'quelle': 'synthetic:comparison-v1',
                              'positionen': [{'oz': '01.001', 'kurztext': 'Synthetic concrete repair',
                                              'titel_pfad': ['Bridge']}]}


def without_priority(detail):
    return _re.sub(r', priority \d', '', detail)


@pytest.mark.parametrize('scenario_id', sorted(SPEC_SCENARIOS))
def test_specification_context_matches_the_19_package(scenario_id):
    from datetime import date
    from app.ai import step_api
    from app.modelle import LV

    scenario = SPEC_SCENARIOS[scenario_id]
    context = step_api.build_specification_context(
        LV.model_validate(scenario['lv']),
        [step_api.SourceRecord.model_validate(s) for s in scenario['sources']],
        checked_on=date.fromisoformat(scenario['checked_on'])).model_dump(mode='json')
    for item in context['items']:
        for entry in item['sources']:
            del entry['record']
    assert context == scenario['expected_context']


def test_acceptance_conflict_gives_source_linked_notes_1_2_and_manual_review():
    notes = []
    for step in ('comparison', 'standards'):
        body = client.post('/api/comparison/steps', json=source_request(
            step, 'acceptance_conflict_unverified', previous_notes=notes)).json()
        assert body['status'] == 'complete' and body['errors'] == [] and body['findings'] == []
        assert body['notes'][:-1] == notes
        notes = body['notes']
    note1, note2 = notes
    expected = SPEC_SCENARIOS['acceptance_conflict_unverified']['expected_notes']
    for note, want in zip(notes, expected):
        assert (note['id'], note['step'], note['oz']) == (want['id'], want['step'], '01.001')
        assert note['manual_review'] and note['source'] == 'rule' and not note['placeholder']
        assert [(e['reference_id'], e['oz'], e['source'], without_priority(e['detail']))
                for e in note['evidence']] == [
            (e['reference_id'], e['oz'], e['source'], e['detail']) for e in want['evidence']]
    assert note1['text'].startswith('Conflict for OZ 01.001')
    for needle in ('S10', 'S12', '10 cm', '12 cm', 'unverified'):
        assert needle in note1['text']
    assert note2['text'] == expected[1]['text']
    assert not CLAIM_WORDS.search(note2['text'])


def test_german_fictional_package_reports_deviation_only_against_a_verified_standard():
    scenario = SPEC_SCENARIOS['fiktiver_pruefdatensatz_bodenplatte']
    results = {}
    for step in ('comparison', 'standards'):
        body = client.post('/api/comparison/steps', json=source_request(step, scenario['id'])).json()
        assert body['status'] == 'complete'
        assert [(e['code'], 'F-X1' in e['message']) for e in body['errors']] == [('source_rejected', True)]
        results.update({n['id']: n for n in body['notes']})
    assert sorted(results) == sorted(n['id'] for n in scenario['expected_notes'])
    for want in scenario['expected_notes']:
        note = results[want['id']]
        assert [e['reference_id'] for e in note['evidence']] == [e['reference_id'] for e in want['evidence']]
        assert [e['detail'] for e in note['evidence']] == [e['detail'] for e in want['evidence']]
        assert note['text'].split(' ')[0] == want['text'].split(' ')[0]
    assert 'F-N1 (10 cm) is below the minimum of 12 cm' in results['Note2:01.001']['text']
    assert results['Note2:01.002']['text'] == 'Manual review: no verified applicable German source for OZ 01.002.'
    assert results['Note1:01.002']['text'].startswith('Possible conflict for OZ 01.002 between unverified')
    texts = ' '.join(n['text'] for n in results.values())
    assert 'Ignoriere' not in texts and '09.999' not in texts and '01.003' not in texts


def test_unverified_german_claim_never_becomes_a_norm_breach():
    request = source_request('standards', 'acceptance_conflict_unverified')
    request['sources'][1] = {**request['sources'][1], 'category': 'german_standard',
                             'title': 'claims to be DIN', 'verified': True, 'location': None}
    note = client.post('/api/comparison/steps', json=request).json()['notes'][0]
    assert note['text'].startswith('Manual review') and not CLAIM_WORDS.search(note['text'])


def test_comparison_model_seam_runs_13_validation_with_priority_1_catalogue(monkeypatch):
    from app.ai import step_api

    def model(batch):
        return _json.dumps({'findings': [
            {'oz': batch[0].oz, 'kategorie': 'fehler', 'schwere': 'mittel', 'titel': 'Thickness',
             'begruendung': 'Below catalogued minimum', 'vorschlag': 'Check', 'quelle': 'modell',
             'regel_id': 'MOCK_SPEC', 'norm_ref': 'F-D1'},
            {'oz': '77.777', 'kategorie': 'fehler', 'schwere': 'hoch', 'titel': 'Invented', 'begruendung': 'x',
             'vorschlag': 'x', 'quelle': 'modell', 'regel_id': 'MOCK_SPEC'},
        ]})

    monkeypatch.setattr(step_api, 'comparison_model', model)
    body = client.post('/api/comparison/steps',
                       json=source_request('comparison', 'fiktiver_pruefdatensatz_bodenplatte')).json()
    findings = {f['oz']: f for f in body['findings']}
    # F-D1 is priority 1 only for 01.001; for 01.002 the same citation is rejected.
    assert list(findings) == ['01.001'] and 'Catalogue: F-D1' in findings['01.001']['begruendung']
    assert findings['01.001']['quelle'] == 'modell' and 'Demonstration' in findings['01.001']['titel']
    assert 'model_output_rejected' in [e['code'] for e in body['errors']]
    assert body['status'] == 'complete'


@pytest.mark.parametrize('scenario_id', sorted(EST_SCENARIOS))
def test_estimate_adapter_reproduces_every_20_expected_note(scenario_id, monkeypatch):
    from app.ai import step_api

    expected = EST_SCENARIOS[scenario_id]['expected_note']
    request = estimate_request(scenario_id)
    if not request['history_records']:
        # An empty pool comes from a connected history service, not from a missing one.
        request.pop('history_records')
        monkeypatch.setattr(step_api, 'history_service', lambda position, mode: [])
    body = client.post('/api/comparison/steps', json=request).json()
    assert body['status'] == 'complete', body
    note = body['notes'][-1]
    assert note['source'] == 'rule' and note['placeholder'] is False
    assert {k: v for k, v in note.items() if k not in ('source', 'placeholder')} == expected
    assert body['evidence'] == expected['evidence']


def test_acceptance_note3_note4_give_60_70_h_with_distinct_pools_and_approval():
    note3 = client.post('/api/comparison/steps', json=estimate_request('acceptance_note3_comparable')).json()
    request = estimate_request('acceptance_note4_what_if', previous_notes=note3['notes'])
    body = client.post('/api/comparison/steps', json=request).json()
    n3, n4 = body['notes']
    assert (n3['estimated_value'], n4['estimated_value']) == (60, 70)
    assert n3['case_ids'] == ['H1', 'H2', 'H3'] and n4['case_ids'] == ['W1', 'W2', 'W3']
    assert not set(n3['case_ids']) & set(n4['case_ids'])
    assert n3['approval_required'] and n4['approval_required']
    assert n3['text'].startswith('Estimate – approval required.') and 'EUR' not in n3['text']


def test_what_if_pool_overlapping_note3_cases_is_a_visible_error():
    note3 = client.post('/api/comparison/steps', json=estimate_request('acceptance_note3_comparable')).json()
    request = estimate_request('acceptance_note4_what_if', previous_notes=note3['notes'])
    request['estimates'][0]['position']['work_tags'] = ['bridge_other_wording']
    for record in request['history_records']:
        record['tags'] = ['other']
    body = client.post('/api/comparison/steps', json=request).json()
    assert body['status'] == 'error' and body['errors'][0]['code'] == 'case_pool_overlap'
    assert body['notes'] == note3['notes']


def test_estimate_without_history_or_failing_service_preserves_notes(monkeypatch):
    from app.ai import step_api

    first = client.post('/api/comparison/steps', json=source_request(
        'comparison', 'acceptance_conflict_unverified')).json()['notes']
    request = estimate_request('acceptance_note3_comparable', previous_notes=first)
    request.pop('history_records')
    body = client.post('/api/comparison/steps', json=request).json()
    assert body['status'] == 'error' and body['notes'] == first
    assert body['errors'] == [{'step': 'historical_adjustment', 'code': 'history_unavailable',
                               'message': 'No history records supplied; history service is not connected.',
                               'retryable': False}]

    def failing(position, mode):
        raise step_api.HistoryUnavailable('private-host:9000 refused')

    monkeypatch.setattr(step_api, 'history_service', failing)
    response = client.post('/api/comparison/steps', json=request)
    body = response.json()
    assert body['status'] == 'error' and body['notes'] == first
    assert body['errors'][0]['code'] == 'history_unavailable' and body['errors'][0]['retryable']
    assert 'private-host' not in response.text


def test_history_service_seam_supplies_records_when_request_has_none(monkeypatch):
    from app.ai import step_api

    calls = []

    def service(position, mode):
        calls.append((position.oz, mode))
        return EST['history_pools']['acceptance']

    monkeypatch.setattr(step_api, 'history_service', service)
    request = estimate_request('acceptance_note4_what_if')
    request.pop('history_records')
    body = client.post('/api/comparison/steps', json=request).json()
    assert body['status'] == 'complete' and body['notes'][0]['estimated_value'] == 70
    assert calls == [('01.001', 'what_if')]


def test_failed_adapter_preserves_earlier_notes_with_safe_error(monkeypatch):
    from app.ai import step_api

    first = client.post('/api/comparison/steps', json=source_request(
        'comparison', 'acceptance_conflict_unverified')).json()['notes']

    def broken(*_args, **_kwargs):
        raise RuntimeError('private-adapter-detail')

    monkeypatch.setattr(step_api, 'select_cases', broken)
    response = client.post('/api/comparison/steps', json=estimate_request(
        'acceptance_note3_comparable', previous_notes=first))
    body = response.json()
    assert body['status'] == 'error' and body['notes'] == first
    assert body['errors'][0]['code'] == 'step_failed' and 'private-adapter-detail' not in response.text


def test_open_specification_note_adds_caveat_without_changing_the_estimate():
    notes = client.post('/api/comparison/steps', json=source_request(
        'standards', 'acceptance_conflict_unverified')).json()['notes']
    body = client.post('/api/comparison/steps', json=estimate_request(
        'acceptance_note3_comparable', previous_notes=notes)).json()
    note3 = body['notes'][-1]
    assert note3['estimated_value'] == 60
    assert note3['uncertainty'].endswith('Estimate does not account for the open specification note (Note2:01.001).')


def test_rerun_replaces_same_note_id_in_place():
    first = client.post('/api/comparison/steps', json=source_request(
        'comparison', 'acceptance_conflict_unverified')).json()['notes']
    again = client.post('/api/comparison/steps', json=source_request(
        'comparison', 'acceptance_conflict_unverified', previous_notes=first)).json()['notes']
    assert again == first


def test_adapter_inputs_are_validated():
    bad = [
        source_request('historical_adjustment', 'acceptance_conflict_unverified'),
        {**source_request('comparison', 'acceptance_conflict_unverified'), 'checked_on': None},
        {**source_request('comparison', 'acceptance_conflict_unverified'),
         'specifications': contract_fixtures()['comparison']['specifications']},
        {**estimate_request('acceptance_note3_comparable'), 'step': 'comparison'},
    ]
    request = estimate_request('acceptance_note3_comparable')
    request['estimates'][0]['position']['oz'] = '99.999'
    bad.append(request)
    request = estimate_request('acceptance_note3_comparable')
    request['estimates'].append(request['estimates'][0])
    bad.append(request)
    request = source_request('comparison', 'acceptance_conflict_unverified')
    request['sources'][1]['source_url'] = 'http://insecure.example.invalid/x'
    bad.append(request)
    for request in bad:
        assert client.post('/api/comparison/steps', json=request).status_code == 422


def test_invalid_limit_is_a_visible_note_status_not_an_estimate():
    request = estimate_request('acceptance_note3_comparable')
    request['estimates'][0]['limit'] = 25
    note = client.post('/api/comparison/steps', json=request).json()['notes'][0]
    assert note['case_ids'] == [] and note['estimated_value'] is None
    assert 'invalid_limit' in note['text'] and note['approval_required']
