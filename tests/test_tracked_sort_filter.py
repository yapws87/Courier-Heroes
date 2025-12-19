import sqlite3
from datetime import datetime
from app import app
import db
import unified


def set_created_at(conn, item_id, iso_ts):
    c = conn.cursor()
    c.execute('UPDATE tracked SET created_at=? WHERE id=?', (iso_ts, item_id))
    conn.commit()


def test_sort_and_filter_tracked(tmp_path, monkeypatch):
    db.DB_PATH = tmp_path / 'tracked_sf.db'
    db.init_db()

    # Insert three tracked items
    id1 = db.add_tracked('T1', courier='TestCourier')
    id2 = db.add_tracked('T2', courier='TestCourier')
    id3 = db.add_tracked('T3', courier='TestCourier')

    # Set deterministic created_at timestamps
    conn = db.get_conn()
    set_created_at(conn, id1, '2025-12-16T10:00:00')
    set_created_at(conn, id2, '2025-12-16T11:00:00')
    set_created_at(conn, id3, '2025-12-16T12:00:00')
    conn.close()

    # Mock unified.track to return different statuses and first-event times
    def mock_track(tracking):
        if tracking == 'T1':
            return {'courier': 'Mock', 'tracking_number': tracking, 'status': '배송완료', 'history': [{'time': '2025.12.16 10:00'}], 'latest_event': {'message': '배송완료'}}
        if tracking == 'T2':
            return {'courier': 'Mock', 'tracking_number': tracking, 'status': '조회불가', 'history': [{'time': '2025/12/16 11:00'}], 'latest_event': {'message': '조회불가'}}
        return {'courier': 'Mock', 'tracking_number': tracking, 'status': 'In transit', 'history': [{'time': '16 Dec 2025 12:00'}], 'latest_event': {'message': 'In transit'}}

    monkeypatch.setattr(unified, 'track', mock_track)

    with app.test_client() as c:
        # Check all items to save last_result
        c.post(f'/api/tracked/{id1}/check')
        c.post(f'/api/tracked/{id2}/check')
        c.post(f'/api/tracked/{id3}/check')

        # Sort ascending by first event time
        r = c.get('/api/tracked?sort=first_event&order=asc')
        assert r.status_code == 200
        items = r.get_json()['items']
        # expecting T1, T2, T3 by their first-event times
        assert [it['tracking'] for it in items] == ['T1', 'T2', 'T3']

        # Filter delivered
        r2 = c.get('/api/tracked?status=delivered')
        items2 = r2.get_json()['items']
        assert len(items2) == 1 and items2[0]['tracking'] == 'T1'

        # Filter error
        r3 = c.get('/api/tracked?status=error')
        items3 = r3.get_json()['items']
        assert len(items3) == 1 and items3[0]['tracking'] == 'T2'

        # Filter other
        r4 = c.get('/api/tracked?status=other')
        items4 = r4.get_json()['items']
        assert len(items4) == 1 and items4[0]['tracking'] == 'T3'
