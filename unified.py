import requests
import httpx
import asyncio
from bs4 import BeautifulSoup, ResultSet, Tag
import re
import logging
import utils
import tracking
logger = logging.getLogger("unified")

# Async batch tracker for concurrent updates
async def track_many_async(tracking_items, debug=False):
    # Create semaphores for each courier type (per event loop)
    cj_semaphore = asyncio.Semaphore(2)
    lotte_semaphore = asyncio.Semaphore(2)
    cu_semaphore = asyncio.Semaphore(2)
    hanjin_semaphore = asyncio.Semaphore(2)
    tasks = []
    for item in tracking_items:
        if isinstance(item, dict):
            invc = item.get('tracking', '').strip()
            courier = (item.get('courier') or '').lower()
        else:
            invc = str(item).strip()
            courier = ''
        if courier == 'cj logistics' or courier == 'cj대한통운' or courier == 'cj':
            tasks.append(track_cj_async(invc, debug=debug, semaphore=cj_semaphore))
        elif courier == 'cupost' or courier == 'cu post' or courier == 'cu':
            tasks.append(track_cu_async(invc, debug=debug, semaphore=cu_semaphore))
        elif courier == 'hanjin' or courier == '한진택배':
            tasks.append(track_hanjin_async(invc, debug=debug, semaphore=hanjin_semaphore))
        elif courier == 'korea post' or courier == '우체국':
            import asyncio
            loop = asyncio.get_running_loop()
            from functools import partial
            tasks.append(loop.run_in_executor(None, track_koreapost, invc, debug))
        else:
            # fallback to sync for unknowns
            import asyncio
            loop = asyncio.get_running_loop()
            from functools import partial
            tasks.append(loop.run_in_executor(None, track, invc, debug))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results


import requests
import httpx
import asyncio
from bs4 import BeautifulSoup, ResultSet, Tag
import re
import logging
import utils
import tracking
logger = logging.getLogger("unified")

# -------------------------------------------------------------
# -------------------------------------------------------------
# Note: JSON extraction helper has been moved to `utils.extract_json`
# (imported above). The `normalize` helper standardizes output shape.
# -------------------------------------------------------------
def normalize(
    courier,
    tracking_number,
    sender=None,
    receiver=None,
    latest=None,
    history=None,
):
    # Ensure safe empty values
    if latest is None:
        latest = {}
    if history is None:
        history = []

    # Calculate total days since first event to latest event
    from utils import parse_time_to_dt
    days_taken = None
    if history and isinstance(history, list) and len(history) > 1:
        first_dt = parse_time_to_dt(history[0].get('time', ''))
        last_dt = parse_time_to_dt((latest or {}).get('time', ''))
        if first_dt and last_dt:
            days_taken = (last_dt - first_dt).days
    return {
        "courier": courier,
        "tracking_number": tracking_number,
        "status": latest.get("message", "Unknown"),
        "sender": sender or "",
        "receiver": receiver or "",
        "origin": "",
        "destination": "",
        "latest_event": latest,
        "history": history,
        "days_taken": days_taken,
    }

# -------------------------------------------------------------
# CJ Logistics (대한통운)
# -------------------------------------------------------------
async def track_cj_async(invc, debug=False, semaphore=None):
    url_csrf = "https://www.cjlogistics.com/ko/tool/parcel/tracking"
    url_detail = "https://www.cjlogistics.com/ko/tool/parcel/tracking-detail"
    if semaphore is not None:
        async with semaphore:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url_csrf)
                soup = BeautifulSoup(r.text, "html.parser")
                csrf = soup.find("input", {"name": "_csrf"})["value"]
                r2 = await client.post(url_detail, data={"_csrf": csrf, "paramInvcNo": invc})
    else:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url_csrf)
            soup = BeautifulSoup(r.text, "html.parser")
            csrf = soup.find("input", {"name": "_csrf"})["value"]
            r2 = await client.post(url_detail, data={"_csrf": csrf, "paramInvcNo": invc})
    data = utils.extract_json(r2.text)
    if not data or "trackingDetails" not in data:
        if debug:
            return {"_debug": {"raw": r2.text}, "error": "No tracking data found"}
        return None
    details = data["trackingDetails"]
    history = [
        {
            "time": d["transTime"].replace("T", " ")[:16],
            "location": d["transWhere"],
            "message": d["transKind"],
        }
        for d in details
    ]
    history = utils.normalize_history(history)
    latest = history[-1] if history else {}
    out = normalize(
        courier="CJ Logistics",
        tracking_number=invc,
        sender=data["sender"]["name"],
        receiver=data["receiver"]["name"],
        latest=latest,
        history=history,
    )
    if debug:
        out["_debug"] = {"raw": r2.text}
    return out

# Synchronous wrapper for compatibility
def track_cj(invc, debug=False):
    return asyncio.run(track_cj_async(invc, debug=debug))

# -------------------------------------------------------------
# CVSNet (GS25 택배)
# -------------------------------------------------------------
def track_cvs(invc, debug=False):
    url: str = f"https://www.cvsnet.co.kr/invoice/tracking.do?invoice_no={invc}"
    r = requests.get(url)
    attempts = []

    # Try a few decodings/variants to handle different encodings from the site
    candidates = [("requests_text", r.text)]
    try:
        candidates.append(("utf8", r.content.decode("utf-8", errors="replace")))
    except Exception:
        pass
    try:
        candidates.append(("cp949", r.content.decode("cp949", errors="replace")))
    except Exception:
        pass

    data = None
    used_encoding = None
    for name, txt in candidates:
        attempts.append({"method": name, "length": len(txt)})
        tmp = utils.extract_json(txt)
        if tmp:
            data = tmp
            used_encoding: str = name
            break

    if not data or "trackingDetails" not in data:
        if debug:
            return {
                "_debug": {
                    "raw": r.text,
                    "status_code": getattr(r, "status_code", None),
                    "headers": dict(getattr(r, "headers", {})),
                    "snippet": r.text[:2000],
                    "attempts": attempts,
                    "used": used_encoding,
                },
                "error": "No tracking data found",
            }
        return None

    details = data["trackingDetails"]

    history = [
        {
            "time": d["transTime"].replace("T", " ")[:16],
            "location": d["transWhere"],
            "message": d["transKind"],
        }
        for d in details
    ]
    history = utils.normalize_history(history)
    latest = history[-1] if history else {}

    out = normalize(
        courier="CVSNet (GS25)",
        tracking_number=invc,
        sender=data["sender"]["name"],
        receiver=data["receiver"]["name"],
        latest=latest,
        history=history,
    )
    if debug:
        out["_debug"] = {
            "raw": r.text,
            "used": used_encoding,
            "attempts": attempts,
            "snippet": r.text[:2000],
        }
    return out

# -------------------------------------------------------------
# Lotte (롯데택배)
# -------------------------------------------------------------
async def track_lotte_async(invc, debug=False, semaphore=None):
    url = "https://www.lotteglogis.com/mobile/reservation/tracking/linkView"
    if semaphore is not None:
        async with semaphore:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, data={"InvNo": invc})
    else:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, data={"InvNo": invc})
    try:
        parsed = tracking.parse_tracking_html(r.text)
        events = parsed.get('trackingEvents', [])
        history = [
            {
                'time': (ev.get('timestamp') or ev.get('time') or '').replace('\xa0', ' ').replace('&nbsp;', ' '),
                'location': ev.get('location', ''),
                'message': ev.get('description', '')
            }
            for ev in events
        ]
        history = utils.normalize_history(history)
        latest = history[-1] if history else {"message": parsed.get('deliveryStatus', '')}
        out = normalize(
            courier=parsed.get('carrier', {}).get('name', 'Lotte'),
            tracking_number=parsed.get('trackingNumber', invc),
            latest=latest,
            history=history,
        )
        out['origin'] = parsed.get('origin', '')
        out['destination'] = parsed.get('destination', '')
        if debug:
            out['_debug'] = {'raw': r.text, 'parsed': parsed, 'snippet': r.text[:2000], 'length': len(r.text)}
        return out
    except Exception:
        pass
    # Fallback: extract table rows
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table tr")
    history = [
        {"time": tds[0].text.strip(), "location": tds[2].text.strip(), "message": tds[1].text.strip()}
        for tr in rows[1:]
        if (tds := tr.find_all("td")) and len(tds) >= 3
    ]
    history = utils.normalize_history(history)
    latest = history[-1] if history else {}
    out = normalize(
        courier="Lotte",
        tracking_number=invc,
        latest=latest,
        history=history,
    )
    if debug:
        out["_debug"] = {"raw": r.text, "snippet": r.text[:2000], "length": len(r.text)}
    return out

# Synchronous wrapper for compatibility
def track_lotte(invc, debug=False):
    return asyncio.run(track_lotte_async(invc, debug=debug))


# -------------------------------------------------------------
# CU Post (CUpost)
# -------------------------------------------------------------
async def track_cu_async(invc, debug=False, semaphore=None):
    url = "https://www.cupost.co.kr/mobile/delivery/allResult.cupost"
    payload = {"invoice_no": invc}

    headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Mobile Safari/537.36"}
    try:
        if semaphore is not None:
            async with semaphore:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.post(url, data=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, data=payload, headers=headers)
    except Exception as e:
        if debug:
            return {"_debug": {"error": str(e)}, "error": "Request failed"}
        return None

    try:
        parsed = tracking.parse_cupost_main(r.text)
    except Exception:
        parsed = None

    if not parsed:
        if debug:
            return {
                "_debug": {
                    "raw": r.text,
                    "status_code": getattr(r, "status_code", None),
                    "headers": dict(getattr(r, "headers", {})),
                    "snippet": r.text[:2000],
                    "length": len(r.text),
                },
                "error": "No tracking data found",
            }
        return None

    events = parsed.get("trackingEvents", [])
    history = [
        {"time": e.get("timestamp", ""), "location": e.get("location", ""), "message": e.get("description", "")}
        for e in events
    ]
    history = utils.normalize_history(history)
    latest = history[-1] if history else {"message": parsed.get("deliveryStatus", "")}

    out = normalize(
        courier=parsed.get("carrier", {}).get("name", "CUpost"),
        tracking_number=parsed.get("trackingNumber", invc),
        sender=parsed.get("sender_name", ""),
        receiver=parsed.get("recipient_name", ""),
        latest=latest,
        history=history,
    )
    out["origin"] = parsed.get("origin", "")
    out["destination"] = parsed.get("destination", "")
    if debug:
        out["_debug"] = {
            "raw": r.text,
            "parsed": parsed,
            "snippet": r.text[:2000],
            "length": len(r.text),
            "status_code": getattr(r, "status_code", None),
            "headers": dict(getattr(r, "headers", {})),
        }
    return out

# Synchronous wrapper for compatibility
def track_cu(invc, debug=False):
    return asyncio.run(track_cu_async(invc, debug=debug))

# -------------------------------------------------------------
# Hanjin (한진택배)
# -------------------------------------------------------------
async def track_hanjin_async(invc, debug=False, semaphore=None):
    url = f"https://www.hanjin.co.kr/kor/CMS/DeliveryMgr/WaybillResult.do?mCode=MN038&NUM={invc}"
    if semaphore is not None:
        async with semaphore:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url)
    else:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table.tb_deliver tbody tr")
    history = []
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        time, location, message = [td.text.strip() for td in tds]
        history.append({"time": time, "location": location, "message": message})
    history = utils.normalize_history(history)
    latest = history[-1] if history else {}
    out = normalize(
        courier="Hanjin",
        tracking_number=invc,
        latest=latest,
        history=history,
    )
    if debug:
        out["_debug"] = {"raw": r.text}
    return out

# Synchronous wrapper for compatibility
def track_hanjin(invc, debug=False):
    return asyncio.run(track_hanjin_async(invc, debug=debug))

# -------------------------------------------------------------
# Korea Post (우체국)
# -------------------------------------------------------------
def track_koreapost(invc, debug=False):
    url: str = f"https://service.epost.go.kr/trace.RetrieveDomRigiTraceList.comm?sid1={invc}"
    r = requests.get(url)
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("table.table_col tbody tr")
    history = []
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        time, status, location = [x.text.strip() for x in tds]
        history.append({"time": time, "location": location, "message": status})
    history = utils.normalize_history(history)
    latest = history[-1] if history else {}

    out = normalize(
        courier="Korea Post",
        tracking_number=invc,
        latest=latest,
        history=history,
    )
    if debug:
        out["_debug"] = {"raw": r.text}
    return out


# ----------------------------------------------------------------------
# KG Logis
# ----------------------------------------------------------------------
def track_kgl(invc, debug=False):
    url = f"https://www.kglogis.co.kr/delivery/delivery_result.jsp?item_no={invc}"
    r = requests.get(url)
    out = normalize(
        courier="KG Logis",
        tracking_number=invc,
        latest={},
        history=[],
    )
    out["raw_html"] = r.text
    if debug:
        out["_debug"] = {"raw": r.text}
    return out

# ----------------------------------------------------------------------
# Daesin (대신택배)
# ----------------------------------------------------------------------
def track_daesin(invc, debug=False):
    url = f"http://www.ds3211.co.kr/freight/internalFreightSearch.ht?billno={invc}"
    r = requests.get(url)
    out = normalize(
        courier="Daesin",
        tracking_number=invc,
        latest={},
        history=[],
    )
    out["raw_html"] = r.text
    if debug:
        out["_debug"] = {"raw": r.text}
    return out
    
# ----------------------------------------------------------------------
# Logen (로젠택배)
# ----------------------------------------------------------------------
def track_logen(invc, debug=False):
    url = "https://www.ilogen.com/deliveryInfo"
    r = requests.post(url, data={"invoiceNo": invc})
    data = utils.extract_json(r.text)
    history = []
    latest = {}
    if data and isinstance(data, dict):
        # Try to extract history if possible (example structure may vary)
        events = data.get("trackingDetails") or []
        history = [
            {
                "time": ev.get("transTime", "").replace("T", " ")[:16],
                "location": ev.get("transWhere", ""),
                "message": ev.get("transKind", "")
            }
            for ev in events if isinstance(ev, dict)
        ]
        history = utils.normalize_history(history)
        latest = history[-1] if history else {}
    out = normalize(
        courier="Logen",
        tracking_number=invc,
        latest=latest,
        history=history,
    )
    out["raw_json"] = data
    if debug:
        out["_debug"] = {"raw": r.text}
    return out
    
    
# -------------------------------------------------------------
# Universal dispatcher
# -------------------------------------------------------------
def track(invc, debug=False):
    invc = invc.strip()
    debug_attempts = []

    if re.match(r"^\d{12}$", invc):  # CJ / Lotte / GS25 common
        # Try CJ first
        cj = track_cj(invc, debug=debug)
        if cj and "error" not in cj:
            if debug:
                cj.setdefault("_debug", {})
                cj["_debug"]["attempts"] = debug_attempts
            return cj
        else:
            if debug and cj:
                debug_attempts.append({"courier": "CJ Logistics", "result": cj})

        # Try CVSNet
        cvs = track_cvs(invc, debug=debug)
        if cvs and "error" not in cvs:
            if debug:
                cvs.setdefault("_debug", {})
                cvs["_debug"]["attempts"] = debug_attempts
            return cvs
        else:
            if debug and cvs:
                debug_attempts.append({"courier": "CVSNet", "result": cvs})

        # Try Lotte
        l = track_lotte(invc, debug=debug)
        if l and "error" not in l:
            if debug:
                l.setdefault("_debug", {})
                l["_debug"]["attempts"] = debug_attempts
            return l
        else:
            if debug and l:
                debug_attempts.append({"courier": "Lotte", "result": l})
    
    # CUpost uses 11-digit invoice numbers in many cases
    if re.match(r"^\d{11}$", invc):
        cu = track_cu(invc, debug=debug)
        if cu and "error" not in cu:
            if debug:
                cu.setdefault("_debug", {})
                cu["_debug"]["attempts"] = debug_attempts
            return cu
        else:
            if debug and cu:
                debug_attempts.append({"courier": "CUpost", "result": cu})
        
    
        # track_daesin(invc, debug=debug)
        # track_logen(invc, debug=debug)

    if re.match(r"^\d{10}$", invc):
        h = track_hanjin(invc, debug=debug)
        if debug:
            h.setdefault("_debug", {})
            h["_debug"]["attempts"] = debug_attempts
        return h

    if re.match(r"^\d{13}$", invc):
        k = track_koreapost(invc, debug=debug)
        if debug:
            k.setdefault("_debug", {})
            k["_debug"]["attempts"] = debug_attempts
        return k
    
    if re.match(r"^\d{20}$", invc):
        seven_el = {'courier': '7-Eleven 착한택배',
               'tracking_number': invc,
               'status': 'unavailable',
               'history': []
               }
        # kgl = track_kgl(invc, debug=debug)
        # if debug:
        #     kgl.setdefault("_debug", {})
        #     kgl["_debug"]["attempts"] = debug_attempts
        return seven_el
    
    return {"error": "Unknown tracking format", "_debug": {"attempts": debug_attempts} }

# -------------------------------------------------------------
# Example
# -------------------------------------------------------------
if __name__ == "__main__":
    
    seven_el_1 = "11110525121300000019"
    seven_el_2 = "11110525121100000051"
    
    cu = "25129173683"
    lotte = "404931271275"
    cu_post = "363225021454"
    gs_post_1 = "210535605545"
    
    
    print(track(gs_post_1))
    
