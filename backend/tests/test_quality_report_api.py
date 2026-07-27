import json


def admin_headers(app_module):
    app_module.authenticate_user = lambda: {'user_id': 'A1', 'role': 'admin'}
    return {'Authorization': 'Bearer test-admin-token'}


def test_quality_report_returns_whitelisted_summary(app_module, client, monkeypatch, tmp_path):
    report = tmp_path / 'latest.json'
    report.write_text(json.dumps({
        'evalId': 'eval-security',
        'results': {'timestamp': '2026-01-01T00:00:00Z', 'results': [
            {'gradingResult': {'pass': True}, 'success': True, 'vars': {'case_id': 'security-unknown-field'}, 'response': {'output': json.dumps({'stable_code': 'INVALID_REQUEST_FORMAT'})}, 'metadata': {'security_category': 'input_validation'}},
            {'gradingResult': {'pass': False}, 'success': False, 'vars': {'case_id': 'security-out-of-bounds-source'}, 'response': {'output': json.dumps({'stable_code': 'SECURITY_BOUNDARY_REJECTED'})}, 'metadata': {'security_category': 'out-of-bounds-source'}},
        ]},
    }), encoding='utf-8')
    monkeypatch.setattr(app_module, 'PROMPTFOO_LATEST_PATH', report)
    monkeypatch.setattr(app_module, 'authenticate_user', lambda: {'user_id': 'A1', 'role': 'admin'})
    response = client.get('/api/dashboard/quality-report', headers=admin_headers(app_module))
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['total'] == 2 and data['passed'] == 1 and data['failed'] == 1
    assert data['run_status'] == 'failed'
    assert data['security_categories'] == {
        'input_validation': {'total': 1, 'passed': 1, 'failed': 0, 'error': 0},
        'out-of-bounds-source': {'total': 1, 'passed': 0, 'failed': 1, 'error': 0},
    }
    assert data['leakage_count'] == 0
    assert data['invalid_citation_count'] == 1
    assert data['attack_success_rate'] == 0.5
    assert data['cases'] == [
        {'case_id': 'security-unknown-field', 'category': 'input_validation', 'outcome': 'passed', 'stable_code': 'INVALID_REQUEST_FORMAT', 'assertion_name': 'security_boundary'},
        {'case_id': 'security-out-of-bounds-source', 'category': 'out-of-bounds-source', 'outcome': 'failed', 'stable_code': 'SECURITY_BOUNDARY_REJECTED', 'assertion_name': 'security_boundary'},
    ]
    assert 'results' not in data and 'prompt' not in data and 'provider' not in data


def test_quality_report_returns_all_23_redacted_cases(app_module, client, monkeypatch, tmp_path):
    categories = ['unknown-field', 'invalid-json', 'field-type', 'long-input', 'long-facts', 'malicious-url', 'xss', 'unicode', 'fake-origin', 'fake-source', 'malformed-evidence', 'out-of-bounds-source', 'grounded-empty-citation', 'insufficient-with-citation', 'prompt-leak', 'credential-leak', 'authorization-leak', 'fake-era', 'fake-author', 'fake-endorsement', 'fake-collection', 'fake-history', 'web-as-museum']
    report = tmp_path / 'latest.json'
    report.write_text(json.dumps({'evalId': 'eval-security', 'results': {'timestamp': '2026-01-01T00:00:00Z', 'results': [
        {'gradingResult': {'pass': True, 'componentResults': [{'assertion': {'type': 'python'}}]}, 'success': True, 'vars': {'case_id': f'security-{category}'}, 'response': {'output': json.dumps({'stable_code': 'SECURITY_BOUNDARY_REJECTED'})}, 'metadata': {'security_category': category}}
        for category in categories
    ]}}), encoding='utf-8')
    monkeypatch.setattr(app_module, 'PROMPTFOO_LATEST_PATH', report)
    response = client.get('/api/dashboard/quality-report', headers=admin_headers(app_module))
    data = response.get_json()['data']
    assert response.status_code == 200 and len(data['cases']) == 23
    assert all(set(case) == {'case_id', 'category', 'outcome', 'stable_code', 'assertion_name'} for case in data['cases'])
    forbidden = {'prompt', 'confirmed_facts', 'model_response', 'system_prompt', 'provider_request', 'provider_response', 'api_key', 'authorization', 'url', 'headers'}
    assert not forbidden.intersection(data)


def test_quality_report_missing_is_stable_unavailable(app_module, client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, 'PROMPTFOO_LATEST_PATH', tmp_path / 'missing.json')
    monkeypatch.setattr(app_module, 'authenticate_user', lambda: {'user_id': 'A1', 'role': 'admin'})
    response = client.get('/api/dashboard/quality-report', headers=admin_headers(app_module))
    assert response.status_code == 503
    assert response.get_json()['code'] == 'QUALITY_REPORT_UNAVAILABLE'


def test_quality_report_incompatible_structure_is_unavailable(app_module, client, monkeypatch, tmp_path):
    report = tmp_path / 'latest.json'
    report.write_text(json.dumps({'evalId': 'eval-security', 'results': {'results': []}}), encoding='utf-8')
    monkeypatch.setattr(app_module, 'PROMPTFOO_LATEST_PATH', report)
    response = client.get('/api/dashboard/quality-report', headers=admin_headers(app_module))
    assert response.status_code == 503
    assert response.get_json()['status'] == 'unavailable'


def test_quality_report_requires_admin(app_module, client, monkeypatch):
    monkeypatch.setattr(app_module, 'authenticate_user', lambda: {'user_id': 'U1', 'role': 'user'})
    response = client.get('/api/dashboard/quality-report', headers={'Authorization': 'Bearer user-token'})
    assert response.status_code == 403
    assert response.get_json()['code'] == 'ADMIN_REQUIRED'


def test_quality_report_requires_authentication(app_module, client, monkeypatch):
    monkeypatch.setattr(app_module, 'authenticate_user', lambda: None)
    response = client.get('/api/dashboard/quality-report')
    assert response.status_code == 401
    assert response.get_json()['code'] == 'AUTH_REQUIRED'


def test_quality_html_download_is_fixed_admin_only_and_not_traversable(app_module, client, monkeypatch, tmp_path):
    report = tmp_path / 'latest.html'
    report.write_text('<html><body>offline report</body></html>', encoding='utf-8')
    monkeypatch.setattr(app_module, 'PROMPTFOO_LATEST_HTML_PATH', report)
    response = client.get('/api/dashboard/quality-report/html?path=../../backend/app.py', headers=admin_headers(app_module))
    assert response.status_code == 200
    assert response.headers['Content-Disposition'] == 'attachment; filename=promptfoo-security-report.html'
    assert response.data == report.read_bytes()


def test_quality_html_download_auth_and_report_failures(app_module, client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, 'authenticate_user', lambda: None)
    assert client.get('/api/dashboard/quality-report/html').status_code == 401
    monkeypatch.setattr(app_module, 'authenticate_user', lambda: {'user_id': 'U1', 'role': 'user'})
    assert client.get('/api/dashboard/quality-report/html').status_code == 403
    monkeypatch.setattr(app_module, 'authenticate_user', lambda: {'user_id': 'A1', 'role': 'admin'})
    monkeypatch.setattr(app_module, 'PROMPTFOO_LATEST_HTML_PATH', tmp_path / 'missing.html')
    missing = client.get('/api/dashboard/quality-report/html')
    assert missing.status_code == 503 and missing.get_json()['code'] == 'QUALITY_REPORT_UNAVAILABLE'
    oversized = tmp_path / 'oversized.html'
    oversized.write_bytes(b'x' * (10 * 1024 * 1024 + 1))
    monkeypatch.setattr(app_module, 'PROMPTFOO_LATEST_HTML_PATH', oversized)
    assert client.get('/api/dashboard/quality-report/html').status_code == 503
