
from flask import Flask, Response, render_template, request, jsonify
import traceback
import logging
import unified
import db
from utils import STATUS_KEYWORDS, classify_status
from werkzeug.datastructures.structures import ImmutableMultiDict

# Ensure DB created on startup
import asyncio
app = Flask(__name__)
logger: logging.Logger = logging.getLogger("couriertracker")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
try:
    db.init_db()
except Exception:
    logger.exception("Failed to initialize DB")



@app.route("/")
def index() -> str:
    return render_template("index.html")



@app.route("/api/track", methods=["POST"])
def api_track() -> Response:
    try:
        payload = request.get_json() or request.form
        inv = payload.get("tracking_number")
        debug = bool(payload.get("debug", False))
        if debug:
            logger.setLevel(logging.DEBUG)
        logger.debug("API track request: %s (debug=%s)", inv, debug)
        if not inv:
            return jsonify({"error": "Missing tracking_number"}), 400
        result = unified.track(inv, debug=debug)
        try:
            if isinstance(result, dict):
                summary = {
                    'courier': result.get('courier'),
                    'tracking_number': result.get('tracking_number'),
                    'status': result.get('status'),
                    'history_len': len(result.get('history', [])),
                }
                dbg = result.get('_debug')
                if isinstance(dbg, dict):
                    summary['debug_keys'] = list(dbg.keys())
                    summary['snippet_len'] = len(dbg.get('snippet', ''))
                    summary['raw_len'] = dbg.get('length')
                logger.debug("Track summary: %s", summary)
        except Exception:
            logger.debug("Track result received (unable to summarize)")
        return jsonify(result)
    except Exception as e:
        tb = traceback.format_exc()
        logger.exception("Unhandled error in /api/track")
        return jsonify({"error": str(e), "trace": tb}), 500


# Note: some Flask versions may not have before_first_request available in test context,
# so we initialize DB eagerly on import above instead.



@app.route('/api/tracked', methods=['GET'])
def api_list_tracked() -> Response:
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401
    items = db.list_tracked(user_id)
    sort = request.args.get('sort')
    order = request.args.get('order', 'desc')
    status_filter = request.args.get('status')
    q = request.args.get('q')
    if status_filter:
        items = [it for it in items if classify_status((it.get('last_result') or {}).get('status') or '') == status_filter]
    if q:
        ql = q.lower()
        def matches(it):
            if ql in str(it.get('tracking','')).lower(): return True
            if ql in str(it.get('label','') or '').lower(): return True
            lr = it.get('last_result') or {}
            if lr and ql in str(lr.get('status','')).lower(): return True
            if lr and ql in str(lr.get('courier','')).lower(): return True
            return False
        items = [it for it in items if matches(it)]
    if sort in ('created_at', 'last_checked'):
        reverse = (order != 'asc')
        items = sorted(items, key=lambda it: (it.get(sort) or ''), reverse=reverse)
    elif sort == 'first_event':
        from utils import parse_time_to_dt
        def first_event_dt(it):
            lr = it.get('last_result') or {}
            hist = lr.get('history') if isinstance(lr.get('history'), list) else []
            if hist and isinstance(hist[0], dict):
                t = hist[0].get('time') or ''
                return parse_time_to_dt(t)
            return None
        reverse = (order != 'asc')
        items = sorted(items, key=lambda it: (first_event_dt(it) is None, first_event_dt(it)), reverse=reverse)
    return jsonify({'items': items})



@app.route('/api/tracked', methods=['POST'])
def api_add_tracked() -> Response:
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401
    payload = request.get_json() or request.form
    tracking = payload.get('tracking')
    label = payload.get('label')
    courier = payload.get('courier')
    if not tracking:
        return jsonify({'error': 'Missing tracking field'}), 400
    rowid = db.add_tracked(user_id, tracking, courier=courier, label=label)
    if rowid is None:
        return jsonify({'error': 'Already exists'}), 409
    return jsonify({'id': rowid, 'tracking': tracking, 'courier': courier, 'label': label})



@app.route('/api/tracked/<int:item_id>/label', methods=['POST'])
def api_update_label(item_id) -> Response:
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401
    payload = request.get_json() or request.form
    label = payload.get('label')
    if label is None:
        return jsonify({'error': 'Missing label'}), 400
    ok = db.update_tracked_label(user_id, item_id, label)
    if not ok:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'id': item_id, 'label': label})



@app.route('/api/tracked/<int:item_id>', methods=['DELETE'])
def api_delete_tracked(item_id) -> Response:
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401
    ok = db.remove_tracked(user_id, item_id)
    if ok:
        return jsonify({'ok': True})
    return jsonify({'error': 'Not found'}), 404



@app.route('/api/tracked/<int:item_id>/check', methods=['POST'])
def api_check_tracked(item_id) -> Response:
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401
    items = db.list_tracked(user_id)
    item = next((i for i in items if i['id'] == item_id), None)
    if not item:
        return jsonify({'error': 'Not found'}), 404
    res = unified.track(item['tracking'])
    db.update_tracked_result(item_id, res)
    return jsonify({'id': item_id, 'result': res})



@app.route('/api/tracked/check_all', methods=['POST'])
def api_check_all() -> Response:
    user_id = request.headers.get('X-User-Id')
    if not user_id:
        return jsonify({'error': 'Missing X-User-Id header'}), 401
    from datetime import datetime
    items = db.list_tracked(user_id)
    tracking_items = [{"tracking": i["tracking"], "courier": i.get("courier")} for i in items]
    try:
        results = asyncio.run(unified.track_many_async(tracking_items))
    except Exception as e:
        tb = traceback.format_exc()
        logger.exception('Batch tracking failed')
        return jsonify({'error': str(e), 'trace': tb}), 500
    out = []
    for i, res in zip(items, results):
        db.update_tracked_result(i['id'], res)
        last_checked = datetime.utcnow().isoformat()
        out.append({'id': i['id'], 'tracking': i['tracking'], 'result': res, 'last_checked': last_checked})
    return jsonify({'results': out})



@app.route('/api/status_keywords', methods=['GET'])
def api_status_keywords() -> Response:
    return jsonify(STATUS_KEYWORDS)



if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
