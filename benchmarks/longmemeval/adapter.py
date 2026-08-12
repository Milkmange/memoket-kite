"""LongMemEval dataset-to-session adapter."""

import datetime as _datetime
import re


def parse_dt(s: str):
    # "2023/05/20 (Sat) 02:21"
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})\D+(\d{2}):(\d{2})", s.strip())
    if not m:
        return None
    y, mo, d, hh, mm = m.groups()
    try:
        return _datetime.datetime(int(y), int(mo), int(d), int(hh), int(mm))
    except ValueError:
        return None


def iter_units(instance: dict, max_turn_chars: int = 1200):
    """Yield session dictionaries from one LongMemEval instance's haystack."""
    sess_ids = instance["haystack_session_ids"]
    dates = instance["haystack_dates"]
    sessions = instance["haystack_sessions"]
    order = sorted(
        range(len(sessions)),
        key=lambda i: parse_dt(dates[i]) or _datetime.datetime(2000, 1, 1),
    )
    seen_ids: dict[str, int] = {}
    for i in order:
        dt = parse_dt(dates[i])
        # A few haystacks repeat a session id with different content; suffix
        # repeats so Unit/Line ids stay globally unique within the codebook.
        base_id = sess_ids[i]
        occurrence = seen_ids.get(base_id, 0)
        seen_ids[base_id] = occurrence + 1
        session_id = base_id if occurrence == 0 else f"{base_id}_d{occurrence + 1}"
        utterances = []
        for j, turn in enumerate(sessions[i]):
            txt = (turn.get("content") or "").strip()
            if not txt:
                continue
            if len(txt) > max_turn_chars:
                txt = txt[:max_turn_chars] + " …[truncated]"
            utterances.append((f"{session_id}:{j}", turn.get("role", "user"), "", txt))
        if not utterances:
            continue
        yield {
            "id": session_id,
            "date": dt.strftime("%Y-%m-%d") if dt else "",
            "weekday": dt.strftime("%A") if dt else "?",
            "time": dt.strftime("%H:%M") if dt else "?",
            "t": dt.isoformat(timespec="minutes") if dt else "",
            "bucket": dt.strftime("%Y-%m") if dt else "",
            "title": "",
            "dur": "",
            "speakers": ["user", "assistant"],
            "utterances": utterances,
        }


__all__ = ["iter_units", "parse_dt"]
