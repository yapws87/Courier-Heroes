import json
from pathlib import Path
import re
from typing import Match, Any


def safe_print_json(obj, *, fallback_file: str = "debug-output.json") -> None:
    """Print JSON to stdout in a way that avoids UnicodeEncodeError on narrow consoles.

    Attempts to print with ensure_ascii=False first. If that raises a UnicodeEncodeError
    (common on Windows consoles using legacy encodings), falls back to ensure_ascii=True.
    If that still fails for any reason, writes UTF-8 JSON to ``fallback_file`` and
    prints a short message pointing to the file.
    """
    s: str = json.dumps(obj, ensure_ascii=False, indent=2)
    try:
        print(s)
    except UnicodeEncodeError:
        try:
            print(json.dumps(obj, ensure_ascii=True, indent=2))
        except Exception:
            # Last resort: write UTF-8 file and notify
            p = Path(fallback_file)
            p.write_text(s, encoding="utf-8")
            print(f"Output saved to {p} (utf-8)")


def save_debug_to_file(obj, path: str) -> str:
    """Save debug object as UTF-8 JSON to given path. Returns the path as string."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def extract_json(text) -> Any | None:
    """Try to extract the first JSON object or array from messy HTML/JS text.

    This is the same robust extractor used across couriers: quick regex for
    embedded variables followed by a balanced-brace scanner that respects
    quoted strings and escaped characters.
    """
    import re

    def try_load(s) -> Any | None:
        try:
            return json.loads(s)
        except Exception:
            s2: str = re.sub(r",\s*}\s*$", "}", s)
            s2: str = re.sub(r",\s*]", "]", s2)
            try:
                return json.loads(s2)
            except Exception:
                try:
                    return json.loads(s2.replace("'", '"'))
                except Exception:
                    return None

    var_names: list[str] = ["trackingInfo", "tracking_info", "trackingData", "tracking", "trackingResult", "jsonData", "data"]

    def scan_from(start_idx):
        if start_idx >= len(text):
            return None
        ch = text[start_idx]
        if ch not in "[{":
            return None
        stack = [ch]
        i = start_idx + 1
        quote_char = None
        esc = False
        while i < len(text):
            c = text[i]
            if esc:
                esc = False
                i += 1
                continue
            if c == "\\":
                esc = True
                i += 1
                continue
            if quote_char:
                if c == quote_char:
                    quote_char = None
                i += 1
                continue
            if c == '"' or c == "'":
                quote_char: str = c
                i += 1
                continue
            if c in "{[":
                stack.append(c)
            elif c in "}]":
                opening = stack.pop() if stack else None
                if (opening == "{" and c != "}") or (opening == "[" and c != "]"):
                    return None
                if not stack:
                    return text[start_idx : i + 1]
            i += 1
        return None

    for name in var_names:
        patt = re.compile(r"\b" + re.escape(name) + r"\b\s*=\s*([\{\[])")
        mvar = patt.search(text)
        if mvar:
            candidate = scan_from(mvar.start(1))
            if candidate:
                v = try_load(candidate)
                if v is not None:
                    return v

    m = re.search(r"(\{[\s\S]*?\}|\[[\s\S]*?\])", text)
    if m:
        candidate = m.group(1)
        v = try_load(candidate)
        if v is not None:
            return v

    for start_idx, ch in enumerate(text):
        if ch not in "[{":
            continue
        stack = [ch]
        i = start_idx + 1
        quote_char = None
        esc = False
        while i < len(text):
            c = text[i]
            if esc:
                esc = False
                i += 1
                continue
            if c == "\\":
                esc = True
                i += 1
                continue
            if quote_char:
                if c == quote_char:
                    quote_char = None
                i += 1
                continue
            if c == '"' or c == "'":
                quote_char = c
                i += 1
                continue
            if c in "{[":
                stack.append(c)
            elif c in "}]":
                if not stack:
                    break
                opening = stack.pop()
                if (opening == "{" and c != "}") or (opening == "[" and c != "]"):
                    break
                if not stack:
                    candidate = text[start_idx : i + 1]
                    v = try_load(candidate)
                    if v is not None:
                        return v
                    break
            i += 1

    return None


# Shared status keyword lists for classification and UI sync
STATUS_KEYWORDS: dict[str, list[str]] = {
    "delivered": [
        "delivered",
        "배송완료",
        "배송 완료",
        "배달완료",
        "배달 완료",
        "고객에게 전달",
        "수령완료",
    ],
    "error": [
        "error",
        "not found",
        "notfound",
        "fail",
        "failed",
        "조회불가",
        "unavailable",
        "오류",
        "실패",
        "등록되지",
        "검색 불가",
        "존재하지 않음",
        "없음",
    ],
}


def classify_status(status_text: str) -> str:
    """Classify a free-form status string into 'delivered'|'error'|'other'."""
    if not status_text:
        return "other"
    s: str = str(status_text).lower()
    for k in STATUS_KEYWORDS["delivered"]:
        if k in s:
            return "delivered"
    for k in STATUS_KEYWORDS["error"]:
        if k in s:
            return "error"
    return "other"


def parse_time_to_dt(s):
    """Parse a free-form timestamp string into a datetime.

    Tries dateutil.parser.parse when available (fuzzy parsing). Falls back
    to simple regex-based extraction of YYYY/MM/DD[-] HH:MM[:SS] patterns.
    Returns a timezone-naive datetime on success or None on failure.
    """
    if not s:
        return None
    s: str = str(s).strip()
    try:
        # Prefer dateutil if available for robust parsing
        from dateutil import parser as _parser
        dt = _parser.parse(s, fuzzy=True)
        # Normalize to naive datetime (drop tzinfo)
        if getattr(dt, 'tzinfo', None):
            dt = dt.astimezone(tz=None).replace(tzinfo=None)
        return dt
    except Exception:
        pass

    # Fallback: extract numeric date/time components using regex
    import re
    from datetime import datetime

    # Examples it should handle: '2025-12-16 11:13:47', '2025.12.16 11:13', '2025/12/16 11:13', '16 Dec 2025 11:13'
    # Try to find a YYYY, MM, DD pattern first
    m = re.search(r"(\d{4})[^0-9]{0,3}(\d{1,2})[^0-9]{0,3}(\d{1,2})(?:[^0-9]+(\d{1,2}:\d{2}(?::\d{2})?))?", s)
    if m:
        year, month, day, timepart = m.group(1), m.group(2), m.group(3), m.group(4)
        try:
            if timepart:
                # Normalize timepart to HH:MM:SS
                parts: list[str] | json.Any = timepart.split(':')
                if len(parts) == 2:
                    timepart: str | json.Any = timepart + ':00'
                dtstr: str = f"{int(year):04d}-{int(month):02d}-{int(day):02d} {timepart}"
                try:
                    return datetime.strptime(dtstr, '%Y-%m-%d %H:%M:%S')
                except Exception:
                    try:
                        return datetime.strptime(dtstr, '%Y-%m-%d %H:%M')
                    except Exception:
                        return None
            else:
                return datetime(int(year), int(month), int(day))
        except Exception:
            return None

    # If nothing matched, return None
    return None


def normalize_history(history):
    """Normalize a list of history events so they are ordered oldest-first.

    Each event is expected to be a dict with a 'time' key (string). We use
    parse_time_to_dt to parse time strings; events with parsable datetimes are
    ordered ascending by datetime. Events without parsable times are placed
    after those with datetimes, preserving their original relative order.
    Returns a new list of events (shallow-copied dicts).
    """
    if not isinstance(history, list):
        return history or []

    parsed = []
    others = []
    for idx, ev in enumerate(history):
        if not isinstance(ev, dict):
            others.append((idx, ev))
            continue
        t = ev.get('time') or ev.get('timestamp') or ''
        dt = parse_time_to_dt(t)
        if dt is not None:
            parsed.append((dt, idx, ev))
        else:
            others.append((idx, ev))

    # sort parsed by datetime ascending (oldest first), tie-break with original index
    parsed.sort(key=lambda x: (x[0], x[1]))

    out = [ev for (_dt, _idx, ev) in parsed]
    # append the others preserving their original order
    others.sort(key=lambda x: x[0])
    out.extend([ev for (_idx, ev) in others])
    return out
