import re
import hashlib
import unicodedata
from datetime import datetime
from typing import Any, Iterable, List, Optional

YEAR_RE = re.compile(r"(19|20)\d{2}")

def make_unique_headers(headers: Iterable[str]) -> List[str]:
    out = []
    seen = {}
    for h in headers:
        s = normalize_meta_name(h)
        if s in seen:
            seen[s] += 1
            s = f"{s}_{seen[s]}"
        else:
            seen[s] = 0
        out.append(s)
    return out

def normalize_meta_name(h: Any) -> str:
    if h is None:
        return ""
    s = unicodedata.normalize("NFKC", str(h)).strip().lower()
    s = re.sub(r"[\s/–—\-]+", " ", s)
    s = s.replace("sub sub", "sub_sub").replace("sub-sub", "sub_sub").replace("sub_sub-", "sub_sub ")
    s = s.replace("sub-sector", "sub sector").replace("sub_sub-sector", "sub_sub sector")
    s = s.replace(":", " ").replace(".", " ")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace(" ", "_")
    if s == "sub_sub_sector" or s == "sub__sector":
        s = "sub_sub_sector"
    return s

def to_number(x: Any) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.upper() in {"NA","N/A","NULL","NONE","MISSING","-","—"}:
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except Exception:
        return None

def safe_int(x: Any) -> Optional[int]:
    try:
        return int(float(str(x).strip()))
    except Exception:
        return None

def now_utc_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def is_mostly_numeric(series) -> bool:
    total = min(len(series), 400)
    if total == 0:
        return False
    hits = 0
    for v in series.dropna().head(400):
        if to_number(v) is not None:
            hits += 1
    return hits >= max(3, int(0.8 * total))

def uniqueness_ratio(series) -> float:
    vals = [str(v).strip() for v in series.dropna().head(400)]
    if not vals:
        return 0.0
    return len(set(vals)) / float(len(vals))

def avg_len(series) -> float:
    vals = [len(str(v)) for v in series.dropna().head(400)]
    if not vals:
        return 0.0
    return sum(vals) / float(len(vals))

_RANGE_SEP = re.compile(r"\s*(?:-|–|—|to|–|—)\s*")
def looks_like_range(s: str) -> bool:
    if not s:
        return False
    s = str(s).strip()
    return bool(re.search(r"\d\s*(?:-|–|—|to)\s*\d", s))

def looks_like_ratio(s: str) -> bool:
    if not s:
        return False
    s = str(s).strip().lower()
    return ("/" in s and re.search(r"\d\s*/\s*\d", s) is not None) or (" per " in s)

def parse_date_iso(s: str) -> Optional[str]:
    s = str(s).strip()
    if not s:
        return None
    m = re.match(r"^\d{4}-\d{2}-\d{2}$", s)
    if m:
        return s
    m2 = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m2:
        y, mo, d = m2.groups()
        mo = mo.zfill(2); d = d.zfill(2)
        return f"{y}-{mo}-{d}"
    m3 = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
    if m3:
        d, mo, y = m3.groups()
        mo = mo.zfill(2); d = d.zfill(2)
        return f"{y}-{mo}-{d}"
    return None

def cell_to_string(x: Any) -> Optional[str]:
    if x is None:
        return None
    s = str(x)
    s = re.sub(r"\s+", " ", s).strip()
    return None if s == "" else s

def stable_id(parts: List[str]) -> str:
    canon = "||".join([p.strip().lower() for p in parts])
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()
