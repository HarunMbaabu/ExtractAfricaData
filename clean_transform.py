from typing import Dict, Any, List, Optional
import re
import pandas as pd

from constants import normalize_country, serial_for_country, COUNTRIES
from utils import (
    make_unique_headers, normalize_meta_name, to_number, safe_int, now_utc_iso,
    YEAR_RE, is_mostly_numeric, uniqueness_ratio, avg_len,
    looks_like_range, looks_like_ratio, parse_date_iso, cell_to_string
)
from config import YEARS

YES_TOKENS = {"yes","y","true","t","1"}
NO_TOKENS  = {"no","n","false","f","0"}

def _to_bool01(x):
    if x is None: return None
    s = str(x).strip().lower()
    if s in YES_TOKENS: return 1
    if s in NO_TOKENS:  return 0
    try:
        v = float(s)
        if v == 1.0: return 1
        if v == 0.0: return 0
    except:
        pass
    return None

def _boolean_hint(metric: str, unit: str | None) -> bool:
    u = (unit or '').strip().lower()
    if u in {"yes/no","y/n","boolean","bool","binary"}:
        return True
    m = (metric or '').strip().lower()
    if not m: return False
    if m.endswith('?'): return True
    starts = ('is ', 'has ', 'have ', 'does ', 'do ', 'are ', 'was ', 'were ', 'can ')
    if m.startswith(starts): return True
    if ' yes/no' in m or 'yes/no' in m: return True
    return False

def _slug(x: Any) -> str:
    if x is None: return "na"
    s = str(x).strip().lower()
    out=[]
    for ch in s:
        if ch.isalnum(): out.append(ch)
        elif ch.isspace() or ch in "-/&,()%.°": out.append("_")
    slug="".join(out).strip("_")
    while "__" in slug: slug=slug.replace("__","_")
    return slug or "na"

_PLACEHOLDER_META = {
    "country","sector","sub_sector","sub-sub_sector","metric",
    "unit","description","sources","source_link"
}
_NULL_TOKENS = {"na","n/a","null","missing","none","-"}

def _is_invalid_meta(value: Any) -> bool:
    if value is None: return True
    s = str(value).strip()
    if s == "": return True
    n = normalize_meta_name(s)
    if n in _PLACEHOLDER_META: return True
    if n in _NULL_TOKENS: return True
    return False

def drop_repeated_header_rows(df: pd.DataFrame) -> pd.DataFrame:
    cols_lower = [c.lower() for c in df.columns]
    keep=[]
    for _,row in df.iterrows():
        vals=[str(v).strip().lower() for v in row.values]
        non_empty=[(v,c) for v,c in zip(vals,cols_lower) if v]
        same=sum(1 for v,c in non_empty if v==c)
        keep.append(not(len(non_empty)>0 and same>=max(1,len(non_empty)//2)))
    return df[pd.Series(keep, dtype=bool).values]

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = make_unique_headers(df.columns)
    df = drop_repeated_header_rows(df).reset_index(drop=True)
    na_like = {'', ' ', 'n/a', 'na', 'null', 'missing', '—', '-'}
    def _norm(x):
        if x is None: return None
        if isinstance(x,str):
            s = re.sub(r'[\x00-\x1F\x7F]', '', x).strip()
            return None if s.lower() in na_like or s=='' else s
        return x
    return df.map(_norm)

def _token_set(h: str):
    return set([t for t in re.sub(r'[\s\-/&.]+',' ', (h or '').lower()).split(' ') if t])

def infer_sector_columns(columns):
    items=[]
    for c in columns:
        n = normalize_meta_name(c)
        if "sector" in n:
            depth = n.count("sub")
            items.append((depth, c))
    items.sort(key=lambda x: x[0])
    sector_col      = next((c for d,c in items if d == 0), None)
    sub_sector_col  = next((c for d,c in items if d == 1), None)
    sub_sub_col     = next((c for d,c in items if d >= 2), None)
    return sector_col, sub_sector_col, sub_sub_col

def detect_roles(df: pd.DataFrame):
    cols=list(df.columns); tokens={c:_token_set(c) for c in cols}
    year_like=set()
    for c in cols:
        if YEAR_RE.search(c):
            if is_mostly_numeric(df[c]) or any(to_number(x) is not None for x in df[c].dropna().head(50)):
                year_like.add(c)
    roles = {k:None for k in ["country","sector","sub_sector","sub_sub_sector","metric","unit","description","sources","source_link"]}
    assigned=set()

    cand_country=[c for c in cols if 'country' in tokens[c]]
    if not cand_country:
        best=None; best_non_empty=-1
        for c in cols:
            if c in year_like: continue
            vals=[str(v).strip() for v in df[c].dropna().head(400)]
            non_empty=len([v for v in vals if v])
            if non_empty>best_non_empty:
                best_non_empty=non_empty; best=c
        cand_country=[best] if best else []
    if cand_country:
        roles["country"]=cand_country[0]; assigned.add(roles["country"])

    cand_serial=[c for c in cols if {'serial','sr','s','no','sno','s_no'} & tokens[c]]
    if cand_serial: roles["serial"]=cand_serial[0]; assigned.add(roles["serial"])

    cand_unit=[c for c in cols if 'unit' in tokens[c]]
    if cand_unit: roles["unit"]=cand_unit[0]; assigned.add(roles["unit"])

    cand_desc=[c for c in cols if {'description','desc'} & tokens[c]]
    if cand_desc: roles["description"]=cand_desc[0]; assigned.add(roles["description"])

    for c in cols:
        t=tokens[c]
        if roles["sources"] is None and 'source' in t and 'link' not in t: roles["sources"]=c
        if roles["source_link"] is None and 'link' in t: roles["source_link"]=c

    cand_metric=[c for c in cols if {'metric','indicator','measure'} & tokens[c]]
    if not cand_metric:
        best=None; best_ratio=-1
        for c in cols:
            if c in assigned or c in year_like: continue
            if is_mostly_numeric(df[c]): continue
            r=uniqueness_ratio(df[c])
            if r>best_ratio: best_ratio=r; best=c
        if best: cand_metric=[best]
    if cand_metric: roles["metric"]=cand_metric[0]

    sec, sub, subsub = infer_sector_columns(cols)
    roles["sector"]=roles["sector"] or sec
    roles["sub_sector"]=roles["sub_sector"] or sub
    roles["sub_sub_sector"]=roles["sub_sub_sector"] or subsub

    return roles, year_like

def build_year_column_index(columns):
    idx={}
    cols=list(columns)
    for y in YEARS:
        exact=[c for c in cols if c.strip()==y]
        fuzzy=[c for c in cols if (y in c and c not in exact)]
        idx[y]=(exact,fuzzy)
    return idx

def normalize_source_columns(df: pd.DataFrame) -> pd.DataFrame:
    ren = {}
    for src in list(df.columns):
        low = str(src).lower()
        if src == "Source Link( active link)":
            ren[src] = "source_link"
        elif src == "Source_Link(_active_link)":
            ren[src] = "source_link"
        elif src == "Sources(Mention briefly the report from where data is pulled , if any)":
            ren[src] = "sources"
        else:
            has_source = "source" in low
            has_link   = ("link" in low) or ("url" in low)
            if has_source and has_link and "source_link" not in df.columns:
                ren[src] = "source_link"
            elif has_source and not has_link and "sources" not in df.columns:
                ren[src] = "sources"
    if ren:
        df.rename(columns=ren, inplace=True)
    return df

def _unit_is_ratio(unit: Optional[str]) -> bool:
    if not unit:
        return False
    u = unit.strip().lower()
    if "ratio" in u:
        return True
    if "/" in u:
        return True
    return False

def build_records(
    title: str,
    df: pd.DataFrame,
    default_sector: str | None = None,
    *,
    source_file_path: Optional[str] = None,
    skip_initial_clean: bool = False
) -> List[Dict[str,Any]]:
    if not skip_initial_clean:
        df = clean_dataframe(df)
        df = normalize_source_columns(df)

    roles, _ = detect_roles(df)

    if roles.get("country") and roles["country"] in df.columns:
        c = roles["country"]
        df[c] = df[c].map(normalize_country)

    year_index = build_year_column_index(df.columns)
    records=[]
    for _, row in df.iterrows():
        country     = row.get(roles.get("country"))
        metric      = row.get(roles.get("metric"))
        sector      = row.get(roles.get("sector"))
        sub_sector  = row.get(roles.get("sub_sector"))
        sub_sub     = row.get(roles.get("sub_sub_sector"))
        unit        = row.get(roles.get("unit"))
        description = row.get(roles.get("description"))
        sources     = row.get("sources") if "sources" in df.columns else row.get(roles.get("sources"))
        source_link = row.get("source_link") if "source_link" in df.columns else row.get(roles.get("source_link"))

        if (sector is None or str(sector).strip() == "") and default_sector:
            sector = default_sector

        serial = serial_for_country(country)
        is_boolean = _boolean_hint(str(metric), unit)

        raw_by_year = {}
        has_range = False
        has_ratio = False
        has_date  = False
        for y in YEARS:
            exact, fuzzy = year_index.get(y, ([],[]))
            picked = None
            for c in exact:
                v = row.get(c)
                if cell_to_string(v) is not None:
                    picked = v; break
            if picked is None:
                for c in fuzzy:
                    v = row.get(c)
                    if cell_to_string(v) is not None:
                        picked = v; break
            raw_by_year[y] = picked
            if picked is not None:
                s = str(picked).strip()
                if looks_like_range(s): has_range = True
                if looks_like_ratio(s): has_ratio = True
                if parse_date_iso(s):   has_date  = True

        unit_is_ratio = _unit_is_ratio(unit)

        if has_range or has_ratio or unit_is_ratio:
            dtype = "string"
        elif has_date:
            dtype = "date"
        elif is_boolean:
            dtype = "boolean"
        else:
            dtype = "float"

        data_points: Dict[str, Any] = {}
        if dtype == "string":
            for y in YEARS:
                v = raw_by_year.get(y)
                data_points[y] = cell_to_string(v)
        elif dtype == "date":
            for y in YEARS:
                v = raw_by_year.get(y)
                data_points[y] = parse_date_iso(str(v)) if v is not None else None
        elif dtype == "boolean":
            for y in YEARS:
                v = raw_by_year.get(y)
                b = _to_bool01(v)
                data_points[y] = None if b is None else int(b)
        else:
            for y in YEARS:
                v = raw_by_year.get(y)
                n = to_number(v)
                data_points[y] = None if n is None else float(n)

        data_years = list(YEARS)
        _id = "_".join([
            _slug(country),
            str(serial or 0),
            _slug(sector),
            _slug(sub_sector),
            _slug(sub_sub),
            _slug(metric),
            _slug(unit)
        ])

        doc = {
            "id": _id,
            "country": country,
            "serial": serial,
            "sector": str(sector).strip(),
            "sub_sector": str(sub_sector).strip(),
            "sub_sub_sector": str(sub_sub).strip(),
            "metric": str(metric).strip(),
            "unit": None if unit is None else str(unit).strip(),
            "description": None if description is None else str(description).strip(),
            "data_points": data_points,
            "data_years": data_years,
            "data_year_count": len(data_years),
            "tags": list({str(metric).strip().lower(), str(sub_sector).strip().lower(), str(sector).strip().lower()}),
            "sources": None if sources is None else str(sources).strip(),
            "source_link": None if source_link is None else str(source_link).strip(),
            "data_type": dtype,
            "validated": False,
            "metadata": {
                "created_at": now_utc_iso(),
                "last_updated": now_utc_iso(),
                "source_file": source_file_path if source_file_path else f"{title}.csv",
                "notes": None if description is None else str(description).strip(),
                "data_version": "1.0",
                "has_recent_data": any(y in {"2023","2024"} and (data_points.get(y) not in (None, "")) for y in YEARS),
                "is_estimated": looks_like_range(str(next((v for v in raw_by_year.values() if v is not None), ""))),
                "source_collection": f"{title}"
            }
        }
        records.append(doc)

    return records
