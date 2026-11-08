"""Audit privacy and accuracy at the rendering boundary; changed staff workflows."""
from datetime import datetime

import db
from modules.audit import _readable
from tests.test_smoke import client, login, fake_function


def event(**kw):
    return dict(dict(occurred_at=datetime(2026, 11, 9, 10), actor='dev_admin', approved_by=None,
                     entity='product', action='UPDATE', before_data={}, after_data={}), **kw)


def test_audit_shows_only_changed_fields_and_never_credentials():
    row = event(before_data={'product_name': 'Tee', 'base_price': 100, 'password_hash': 'SECRET_OLD',
                             'master_pin_code': 'SECRET_PIN', 'unknown': {'password': 'NESTED'}},
                after_data={'product_name': 'Tee', 'base_price': 150, 'password_hash': 'SECRET_NEW'})
    result = _readable([row], {})[0]
    assert result['changes'] == [{'field': 'Base price', 'before': '₱100.00', 'after': '₱150.00'}]
    assert 'SECRET' not in str(result) and 'NESTED' not in str(result)


def test_audit_receipt_creation_and_delete_values():
    row = event(entity='sales', action='INSERT', after_data={'sale_id': 7, 'total_amount': 500})
    result = _readable([row], {})[0]
    assert result['details'] == 'Receipt created' and result['subject'] == '#7'
    assert result['changes'][-1] == {'field': 'Total amount', 'before': '—', 'after': '₱500.00'}
    result = _readable([event(action='DELETE', before_data={'product_name': 'Tee'})], {})[0]
    assert result['changes'][0] == {'field': 'Product name', 'before': 'Tee', 'after': '—'}


def test_audit_preserves_recorded_staff_identity():
    row = event(actor_name='Original Name', actor_role='CA')
    result = _readable([row], {'dev_admin': {'name': 'Changed Name', 'role': 'Admin'}})[0]
    assert result['name'] == 'Original Name' and result['role'] == 'Cashier'


def test_audit_html_escapes_values_and_keeps_server_pagination(client, monkeypatch):
    login(client, 'dev_admin')
    def routine(name, *args, **kwargs):
        if name == 'fn_audit_logs':
            return [event(after_data={'product_name': '<script>alert(1)</script>', 'current_stock': 2})] * 51
        return fake_function(name, *args, **kwargs)
    monkeypatch.setattr(db, 'call_function', routine)
    html = client.get('/admin/audit/?actor=dev_admin&entity=product').text
    assert '<th>Staff name</th><th>Role</th>' in html and 'Before' in html and 'After' in html
    assert '&lt;script&gt;' in html and '<script>alert(1)</script>' not in html
    assert 'page=2' in html and 'actor=dev_admin' in html and 'data-pagination="server"' in html


def test_promo_view_then_edit_is_read_only(client):
    login(client, 'dev_admin')
    page = client.get('/admin/promos/1/view')
    assert page.status_code == 200 and 'Campaign overview' in page.text and 'Edit promo' in page.text
    assert '<form' not in page.text.split('Campaign overview')[1].split('</main>')[0]
    assert client.get('/admin/promos/1').status_code == 200


def test_pos_moves_sold_out_variants_after_available_ones(client):
    login(client, 'dev_cashier')
    html = client.get('/pos/').text
    assert html.index('name="product_id" value="1"') < html.index('name="product_id" value="3"') < html.index('name="product_id" value="2"')


def test_promo_view_groups_display_names_by_the_underlying_style(client, monkeypatch):
    login(client, 'dev_admin')
    def routine(name, *args, **kwargs):
        if name == 'fn_discount_products':
            from tests.test_smoke import PRODUCT, PRODUCT_L
            return [dict(p, product_name=p['display_name']) for p in (PRODUCT, PRODUCT_L)]
        return fake_function(name, *args, **kwargs)
    monkeypatch.setattr(db, 'call_function', routine)
    page = client.get('/admin/promos/1/view')
    assert 'Denim Jacket - Black (M)' not in page.text
    assert '1 product' in page.text and '2 variants' in page.text


def test_cashier_cannot_view_admin_promo_summary(client):
    login(client, 'dev_cashier')
    assert client.get('/admin/promos/1/view').status_code == 403


def test_legacy_uppercase_json_audit_has_business_proof():
    row = event(entity='SALE_ITEM', action='INSERT', after_data='{"SALE_ID":51,"QUANTITY":3,"UNIT_PRICE_AT_SALE":699,"PASSWORD_HASH":"hidden"}')
    result = _readable([row], {})[0]
    assert 'Receipt #51' in result['details'] and 'Quantity 3' in result['details']
    assert result['changes'] and 'hidden' not in str(result)


def test_promo_summary_uses_existing_edit_endpoint(client):
    login(client, 'dev_admin')
    assert 'Campaign overview' in client.get('/admin/promos/1?view=1').text


def test_inventory_sorts_and_filters(client, monkeypatch):
    login(client, 'dev_admin')
    def routine(name, *args, **kw):
        if name == 'fn_list_inventory':
            from tests.test_smoke import INV
            return [dict(INV, product_name='Zebra', current_stock=0), dict(INV, product_name='Alpha', current_stock=5)]
        return fake_function(name, *args, **kw)
    monkeypatch.setattr(db, 'call_function', routine)
    html = client.get('/inventory/').text
    assert html.index('Alpha') < html.index('Zebra')
    html = client.get('/inventory/?stock=in').text
    assert 'Alpha' in html and 'Zebra' not in html
    html = client.get('/inventory/?sort=name_desc').text
    assert html.index('Zebra') < html.index('Alpha')


def test_cart_add_keeps_search_and_category(client):
    from tests.test_smoke import post
    login(client, 'dev_cashier')
    response = post(client, '/pos/cart/add', {'product_id':'1','quantity':'1','q':'Denim','category':'1'}, '/pos/')
    assert 'q=Denim' in response.location and 'category=1' in response.location
