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
