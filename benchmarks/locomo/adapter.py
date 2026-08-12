"""LoCoMo dataset-to-session adapter."""

import re
from datetime import datetime


def parse_session_dt(s: str):
    m = re.match(
        r"(\d{1,2}):(\d{2})\s*(am|pm)\s+on\s+(\d{1,2})\s+(\w+),?\s+(\d{4})", s.strip(), re.I
    )
    if not m:
        return None
    hh, mm, ap, day, mon, yr = m.groups()
    hh = int(hh) % 12 + (12 if ap.lower() == "pm" else 0)
    return datetime.strptime(f"{yr}-{mon}-{int(day):02d} {hh:02d}:{mm}", "%Y-%B-%d %H:%M")


def iter_units(sample: dict):
    """Yield session dictionaries from one LoCoMo sample, chronologically."""
    conv = sample["conversation"]
    speakers = [conv.get("speaker_a", ""), conv.get("speaker_b", "")]
    keys = sorted(
        (k for k in conv if re.fullmatch(r"session_\d+", k) and isinstance(conv[k], list)),
        key=lambda k: int(k.split("_")[1]),
    )
    for k in keys:
        n = int(k.split("_")[1])
        dt = parse_session_dt(conv.get(f"{k}_date_time", "") or "")
        utterances = []
        for d in conv[k]:
            txt = (d.get("text") or "").strip()
            if d.get("blip_caption"):
                txt += f" [photo: {d['blip_caption']}]"
            utterances.append((d["dia_id"], d["speaker"], "", txt))
        yield {
            "id": f"{sample['sample_id']}-S{n}",
            "date": dt.strftime("%Y-%m-%d") if dt else "",
            "weekday": dt.strftime("%A") if dt else "?",
            "time": dt.strftime("%H:%M") if dt else "?",
            "t": dt.isoformat(timespec="minutes") if dt else "",
            "bucket": dt.strftime("%Y-%m") if dt else "",
            "title": "",
            "dur": "",
            "speakers": speakers,
            "utterances": utterances,
        }


__all__ = ["iter_units", "parse_session_dt"]
