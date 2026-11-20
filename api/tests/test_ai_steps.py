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
