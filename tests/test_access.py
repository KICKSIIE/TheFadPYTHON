"""Exercise the access and approval boundaries independently of the page fixtures."""
import re
from datetime import datetime

import db
import attendance_store
from tests.test_smoke import client, login, token, fake_function, fake_access, CALLS


def access_mock(monkeypatch, **state):
    def call(name, *args, **kwargs):
        if name == 'fn_staff_access':
            result = fake_access(args[0])
            result.update(active=True, allowed=False, can_clock_in=False,
                          shop_now=datetime(2026,11,9,8), shift_end=datetime(2026,11,9,17))
            result.update(state)
            return result
        return fake_function(name, *args, **kwargs)
    monkeypatch.setattr(attendance_store, 'get_access', lambda user_id: call('fn_staff_access', user_id, one=True))


def test_login_always_prompts_attendance(client):
    response = client.post('/login?next=/admin/products/', data={'username':'dev_admin','password':'pw','_csrf':token(client)})
    assert response.location.endswith('/attendance/')


def test_off_shift_cannot_read_or_mutate_system(client, monkeypatch):
    login(client, "dev_admin")
    access_mock(monkeypatch)
    for path in ['/dashboard','/admin/products/','/attendance/schedule','/admin/audit/']:
        assert client.get(path).location.endswith('/attendance/')
    response=client.post('/admin/products/new', data={'product_name':'Hidden','approval_pin':'123456','_csrf':token(client,'/attendance/')})
    assert response.location.endswith('/attendance/')
    assert not CALLS
    assert client.get('/attendance/').status_code == 200
    assert 'disabled>Clock in' in client.get('/attendance/').text


def test_attendance_verification_fails_closed(client, monkeypatch):
    login(client, "dev_admin")
    def unavailable(*args, **kwargs): raise db.DbError('offline')
    monkeypatch.setattr(attendance_store,'get_access',unavailable)
    response = client.get('/dashboard')
    assert response.status_code == 503
    assert 'Go to sign in' in response.text and 'Sign out' in response.text
    # A signed-in visitor is sent into the app, never back to a second sign-in form.
    page = client.get('/login')
    assert page.status_code == 302 and page.location.endswith('/attendance/')
    csrf = re.search(r'name="_csrf" value="([^"]+)"', response.text).group(1)
    # Signing out does not depend on the database or weaken the attendance gate.
    response = client.post('/logout', data={'_csrf': csrf})
    assert response.location.endswith('/login')
    with client.session_transaction() as session:
        assert 'user_id' not in session


def test_signed_in_visitor_skips_the_sign_in_screen(client):
    login(client, 'dev_admin')
    page = client.get('/login')
    assert page.status_code == 302 and page.location.endswith('/attendance/')
    # Switching accounts is still possible: sign out, then sign in as someone else.
    with client.session_transaction() as session:
        session.clear()
    response = login(client, 'dev_cashier')
    assert response.location.endswith('/attendance/')
    with client.session_transaction() as session:
        assert session['username'] == 'dev_cashier'


def test_sign_in_reports_database_outage_without_disclosing_details(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise db.DbError('internal database detail')
    monkeypatch.setattr(db, 'call_function', unavailable)
    response = login(client, 'dev_admin')
    assert response.status_code == 503
    assert 'Sign-in is temporarily unavailable' in response.text
    assert 'internal database detail' not in response.text
    with client.session_transaction() as session:
        assert 'user_id' not in session


def test_inactive_session_is_revoked(client, monkeypatch):
    login(client, "dev_admin")
    monkeypatch.setattr(attendance_store,'get_access',lambda *args, **kwargs: {'active':False})
    assert client.get('/dashboard').location.endswith('/login')
    with client.session_transaction() as session: assert 'user_id' not in session


def test_missing_or_wrong_approval_never_mutates(client):
    login(client, "dev_admin")
    for pin in ['', '000000']:
        response=client.post('/admin/products/new', data={'product_name':'No','approval_pin':pin,'_csrf':token(client,'/admin/products/new')})
        assert response.status_code == 403
    assert not CALLS


def test_search_suggestions_are_public_and_bounded(client):
    assert client.get('/search-suggestions?q=d').json == []
    rows=client.get('/search-suggestions?q=Denim').json
    assert len(rows) == 1 and rows[0]['name']=='Denim Jacket'
    assert rows[0]['url'].startswith('/product/')


def test_audit_page_is_available_for_admin_only(client):
    login(client,'dev_cashier')
    assert client.get('/admin/audit/').status_code == 403


def test_photo_actions_require_a_valid_admin_pin(client):
    import io
    from tests.test_smoke import PNG
    login(client, 'dev_admin')
    csrf = token(client, '/admin/products/1/photos')
    for route in ('/admin/products/1/photos/5/cover', '/admin/products/1/photos/4/remove'):
        assert client.post(route, data={'_csrf': csrf, 'apply_all': '1'}).status_code == 403
        assert client.post(route, data={'_csrf': csrf, 'approval_pin': '000000', 'apply_all': '1'}).status_code == 403
    response = client.post('/admin/products/1/photos/upload', data={'_csrf': csrf, 'photos': (io.BytesIO(PNG), 'x.png')}, content_type='multipart/form-data')
    assert response.status_code == 403
    assert not CALLS
