import os
import io
import gzip
import zipfile
import logging
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from datetime import datetime

try:
    import cloudscraper  # type: ignore
except ImportError:
    cloudscraper = None

from clean_transform import build_records

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()]
)

BASE_DIR = Path("data") / "green_mining_manf"
BASE_DIR.mkdir(parents=True, exist_ok=True)

START_YEAR = 2015
CURRENT_YEAR = datetime.now().year 
YEARS = [str(y) for y in range(START_YEAR, CURRENT_YEAR + 1)]

AFRICA_COUNTRIES = [
    ("DZA", "Algeria"),
    ("AGO", "Angola"),
    ("BEN", "Benin"),
    ("BWA", "Botswana"),
    ("BFA", "Burkina Faso"),
    ("BDI", "Burundi"),
    ("CMR", "Cameroon"),
    ("CPV", "Cabo Verde"),
    ("CAF", "Central African Republic"),
    ("TCD", "Chad"),
    ("COM", "Comoros"),
    ("COD", "Democratic Republic of the Congo"),
    ("COG", "Congo"),
    ("CIV", "Côte d'Ivoire"),
    ("DJI", "Djibouti"),
    ("EGY", "Egypt"),
    ("GNQ", "Equatorial Guinea"),
    ("ERI", "Eritrea"),
    ("ETH", "Ethiopia"),
    ("GAB", "Gabon"),
    ("GMB", "Gambia"),
    ("GHA", "Ghana"),
    ("GIN", "Guinea"),
    ("GNB", "Guinea-Bissau"),
    ("KEN", "Kenya"),
    ("LSO", "Lesotho"),
    ("LBR", "Liberia"),
    ("LBY", "Libya"),
    ("MDG", "Madagascar"),
    ("MWI", "Malawi"),
    ("MLI", "Mali"),
    ("MRT", "Mauritania"),
    ("MUS", "Mauritius"),
    ("MAR", "Morocco"),
    ("MOZ", "Mozambique"),
    ("NAM", "Namibia"),
    ("NER", "Niger"),
    ("NGA", "Nigeria"),
    ("RWA", "Rwanda"),
    ("STP", "Sao Tome and Principe"),
    ("SEN", "Senegal"),
    ("SYC", "Seychelles"),
    ("SLE", "Sierra Leone"),
    ("ZAF", "South Africa"),
    ("SSD", "South Sudan"),
    ("SDN", "Sudan"),
    ("SWZ", "Eswatini"),
    ("TZA", "Tanzania"),
    ("TGO", "Togo"),
    ("TUN", "Tunisia"),
    ("UGA", "Uganda"),
    ("ZMB", "Zambia"),
    ("ZWE", "Zimbabwe"),
    ("SOM", "Somalia"),
]

AFRICA_ISO3 = [c[0] for c in AFRICA_COUNTRIES]
COUNTRY_NAME = {c[0]: c[1] for c in AFRICA_COUNTRIES}

OUTPUT_COLUMNS = [
    "country_iso3",
    "country",
    "sector",
    "subsector",
    "sub_sub_sector",
    "metric",
    "unit",
] + [str(y) for y in YEARS]


def make_session() -> requests.Session:
    if cloudscraper is not None:
        try:
            return cloudscraper.create_scraper()
        except Exception:
            pass
    return requests.Session()


SESSION = make_session()


def json_to_df(obj) -> pd.DataFrame:
    if isinstance(obj, dict):
        if "data" in obj and isinstance(obj["data"], (list, dict)):
            return pd.json_normalize(obj["data"])
        if "result" in obj and isinstance(obj["result"], (list, dict)):
            return pd.json_normalize(obj["result"])
        return pd.json_normalize(obj)
    if isinstance(obj, list):
        return pd.json_normalize(obj)
    return pd.json_normalize(obj)


def ensure_all_countries(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return panel
    year_cols = [c for c in panel.columns if isinstance(c, str) and c.isdigit()]
    meta_cols = [
        c
        for c in panel.columns
        if c not in year_cols and c not in ("country_iso3", "country")
    ]
    frames = []
    for _, g in panel.groupby(meta_cols, dropna=False):
        has = set(g["country_iso3"])
        missing = [iso for iso in AFRICA_ISO3 if iso not in has]
        if missing:
            add_rows = []
            template = {c: g.iloc[0][c] for c in meta_cols}
            for iso in missing:
                row = {"country_iso3": iso}
                row.update(template)
                for y in year_cols:
                    row[y] = pd.NA
                add_rows.append(row)
            add_df = pd.DataFrame(add_rows)
            g = pd.concat([g, add_df], ignore_index=True)
        frames.append(g)
    out = pd.concat(frames, ignore_index=True)
    out["country"] = out["country_iso3"].map(COUNTRY_NAME)
    cols = ["country_iso3", "country"] + meta_cols + year_cols
    out = out[cols]
    out = out.sort_values(["metric", "country_iso3"]).reset_index(drop=True)
    return out


def build_stub_panel_from_meta(meta_list):
    rows = []
    for meta in meta_list:
        for iso in AFRICA_ISO3:
            row = {
                "country_iso3": iso,
                "sector": meta["sector"],
                "subsector": meta["subsector"],
                "sub_sub_sector": meta["sub_sub_sector"],
                "metric": meta["metric"],
                "unit": meta["unit"],
            }
            for y in YEARS:
                row[str(y)] = pd.NA
            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    panel = pd.DataFrame(rows)
    panel = ensure_all_countries(panel)

    for col in OUTPUT_COLUMNS:
        if col not in panel.columns:
            panel[col] = pd.NA
    panel = panel[OUTPUT_COLUMNS]
    return panel


WDI_INDICATORS = {
    "NV.IND.MANF.ZS": {
        "metric": "Manufacturing, value added (% of GDP)",
        "unit": "percent of GDP",
        "subsector": "Manufacturing",
        "sub_sub_sector": "Value added (% of GDP)",
    },
    "NV.IND.MANF.KD.ZG": {
        "metric": "Manufacturing, value added (annual % growth)",
        "unit": "percent growth",
        "subsector": "Manufacturing",
        "sub_sub_sector": "Value added growth",
    },
    "NV.IND.TOTL.ZS": {
        "metric": "Industry, value added (% of GDP)",
        "unit": "percent of GDP",
        "subsector": "Industry (incl. mining)",
        "sub_sub_sector": "Value added (% of GDP)",
    },
    "SL.IND.EMPL.ZS": {
        "metric": "Employment in industry (% of total employment)",
        "unit": "percent of total employment",
        "subsector": "Industry (incl. mining)",
        "sub_sub_sector": "Employment share",
    },
    "TM.VAL.MMTL.ZS.UN": {
        "metric": "Ores and metals imports (% of merchandise imports)",
        "unit": "percent of merchandise imports",
        "subsector": "Mining",
        "sub_sub_sector": "Trade (imports share)",
    },
    "TX.VAL.MMTL.ZS.UN": {
        "metric": "Ores and metals exports (% of merchandise exports)",
        "unit": "percent of merchandise exports",
        "subsector": "Mining",
        "sub_sub_sector": "Trade (exports share)",
    },
    "TX.VAL.MANF.ZS.UN": {
        "metric": "Manufactures exports (% of merchandise exports)",
        "unit": "percent of merchandise exports",
        "subsector": "Manufacturing",
        "sub_sub_sector": "Trade (exports share)",
    },
    "TX.MNF.TECH.ZS.UN": {
        "metric": "Medium and high-tech exports (% of manufactured exports)",
        "unit": "percent of manufactured exports",
        "subsector": "Manufacturing",
        "sub_sub_sector": "Technology exports share",
    },
    "NV.IND.MANF.CD": {
        "metric": "Manufacturing, value added (current US$)",
        "unit": "current US dollars",
        "subsector": "Manufacturing",
        "sub_sub_sector": "Value added (current US$)",
    },
    "NV.IND.MANF.KD": {
        "metric": "Manufacturing, value added (constant 2015 US$)",
        "unit": "constant 2015 US dollars",
        "subsector": "Manufacturing",
        "sub_sub_sector": "Value added (constant)",
    },
    "NV.IND.TOTL.CD": {
        "metric": "Industry, value added (current US$)",
        "unit": "current US dollars",
        "subsector": "Industry (incl. mining)",
        "sub_sub_sector": "Value added (current US$)",
    },
    "NV.IND.TOTL.KD": {
        "metric": "Industry, value added (constant 2015 US$)",
        "unit": "constant 2015 US dollars",
        "subsector": "Industry (incl. mining)",
        "sub_sub_sector": "Value added (constant)",
    },
    "EN.CO2.MANF.ZS": {
        "metric": "CO2 emissions from manufacturing industries and construction (% of total fuel combustion)",
        "unit": "percent of total fuel combustion",
        "subsector": "Industry (incl. mining)",
        "sub_sub_sector": "CO2 emissions share",
    },
    "EN.CO2.ETOT.ZS": {
        "metric": "CO2 emissions from electricity and heat production (% of total fuel combustion)",
        "unit": "percent of total fuel combustion",
        "subsector": "Industry (incl. mining)",
        "sub_sub_sector": "CO2 emissions share (power/heat)",
    },
    "EN.ATM.CO2E.KT": {
        "metric": "CO2 emissions (kt)",
        "unit": "kilotonnes of CO2 equivalent",
        "subsector": "Industry (incl. mining)",
        "sub_sub_sector": "CO2 emissions level",
    },
    "EN.ATM.CO2E.PC": {
        "metric": "CO2 emissions (metric tons per capita)",
        "unit": "metric tons per capita",
        "subsector": "Industry (incl. mining)",
        "sub_sub_sector": "CO2 emissions per capita",
    },
}


def fetch_worldbank_wdi() -> pd.DataFrame:
    indicators = list(WDI_INDICATORS.keys())
    country_str = ";".join(AFRICA_ISO3)
    frames = []
    for code in indicators:
        url = f"https://api.worldbank.org/v2/country/{country_str}/indicator/{code}"
        params = {
            "date": f"{START_YEAR}:{CURRENT_YEAR}",
            "format": "json",
            "per_page": 20000,
        }
        page = 1
        rows_all = []
        while True:
            params["page"] = page
            r = SESSION.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            if not data or len(data) < 2:
                break
            meta, rows = data[0], data[1]
            if not rows:
                break
            rows_all.extend(rows)
            pages = meta.get("pages", 1)
            if page >= pages:
                break
            page += 1
        if rows_all:
            df = pd.json_normalize(rows_all)
            df["indicator_code"] = code
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def tidy_worldbank_wdi(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        logging.warning("World Bank WDI: No raw data provided.")
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = df_raw.copy()
    df["date"] = pd.to_numeric(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["year"] = df["date"].astype(int)
    df = df[df["year"].between(START_YEAR, CURRENT_YEAR)]
    if "countryiso3code" in df.columns:
        df["country_iso3"] = df["countryiso3code"].str.upper()
    else:
        df["country_iso3"] = df["country.id"].str[-3:].str.upper()
    df = df[df["country_iso3"].isin(AFRICA_ISO3)]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    meta_rows = []
    for code, meta in WDI_INDICATORS.items():
        meta_rows.append(
            {
                "indicator_code": code,
                "sector": "Green mining & manufacturing",
                "subsector": meta["subsector"],
                "sub_sub_sector": meta["sub_sub_sector"],
                "metric": meta["metric"],
                "unit": meta["unit"],
            }
        )
    meta_df = pd.DataFrame(meta_rows)
    df = df.merge(meta_df, left_on="indicator_code", right_on="indicator_code", how="left")
    for col in ["country_iso3", "sector", "subsector", "sub_sub_sector", "metric", "unit", "year", "value"]:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[[
        "country_iso3",
        "sector",
        "subsector",
        "sub_sub_sector",
        "metric",
        "unit",
        "year",
        "value",
    ]]
    panel = df.pivot_table(
        index=[
            "country_iso3",
            "sector",
            "subsector",
            "sub_sub_sector",
            "metric",
            "unit",
        ],
        columns="year",
        values="value",
        aggfunc="mean",
    ).reset_index()
    for y in YEARS:
        if y not in panel.columns:
            panel[y] = pd.NA
    panel.columns = [str(c) if isinstance(c, int) else c for c in panel.columns]
    panel = panel[
        [
            "country_iso3",
            "sector",
            "subsector",
            "sub_sub_sector",
            "metric",
            "unit",
        ]
        + [str(y) for y in YEARS]
    ]
    panel = ensure_all_countries(panel)
    return panel


def fetch_unido_cip() -> pd.DataFrame:
    url = "https://stat.unido.org/data/download?dataset=cip"
    try:
        r = SESSION.get(
            url,
            timeout=300,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://stat.unido.org/data/download",
            },
        )
        if r.status_code >= 400:
            return pd.DataFrame()
    except requests.RequestException:
        return pd.DataFrame()
    buf = io.BytesIO(r.content)
    try:
        with zipfile.ZipFile(buf) as z:
            csv_names = [n for n in z.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                return pd.DataFrame()
            frames = []
            for name in csv_names:
                with z.open(name) as f:
                    frames.append(pd.read_csv(f))
            if not frames:
                return pd.DataFrame()
            df = pd.concat(frames, ignore_index=True)
    except zipfile.BadZipFile:
        buf.seek(0)
        try:
            df = pd.read_csv(buf)
        except Exception:
            return pd.DataFrame()
    return df


def tidy_unido_cip(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = df_raw.copy()
    year_col = None
    for cand in ["year", "YEAR", "period", "PERIOD", "refYear", "REF_YEAR"]:
        if cand in df.columns:
            year_col = cand
            break
    if year_col is None:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df[year_col] = pd.to_numeric(df[year_col], errors="coerce")
    df = df.dropna(subset=[year_col])
    df[year_col] = df[year_col].astype(int)
    df = df[df[year_col].between(START_YEAR, CURRENT_YEAR)]
    iso_col = None
    for cand in ["iso3", "ISO3", "country_iso3", "cty_iso3", "cty_iso"]:
        if cand in df.columns:
            iso_col = cand
            break
    if iso_col is None:
        for c in df.columns:
            if df[c].dtype == object:
                vals = df[c].dropna().astype(str).str.upper()
                if (vals.str.len() == 3).mean() > 0.8 and (
                    vals.isin(AFRICA_ISO3).mean() > 0.2
                ):
                    iso_col = c
                    break
    if iso_col is None:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df[iso_col] = df[iso_col].astype(str).str.upper()
    df = df[df[iso_col].isin(AFRICA_ISO3)]
    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    id_cols = {iso_col, year_col}
    metric_cols = []
    for c in df.columns:
        if c in id_cols:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            metric_cols.append(c)
    if not metric_cols:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    long_frames = []
    meta_rows = []
    for col in metric_cols:
        col_clean = str(col).strip()
        metric_name = col_clean
        unit = "index or ratio (see UNIDO CIP metadata)"
        subsector = "Industrial competitiveness"
        sub_sub = "CIP component"
        meta_rows.append(
            {
                "metric_id": col_clean,
                "metric": metric_name,
                "unit": unit,
                "subsector": subsector,
                "sub_sub_sector": sub_sub,
            }
        )
        tmp = df[[iso_col, year_col, col]].copy()
        tmp.rename(columns={iso_col: "country_iso3", year_col: "year"}, inplace=True)
        tmp["metric_id"] = col_clean
        tmp["value"] = pd.to_numeric(tmp[col], errors="coerce")
        long_frames.append(tmp[["country_iso3", "metric_id", "year", "value"]])
    long_df = pd.concat(long_frames, ignore_index=True)
    meta_df = pd.DataFrame(meta_rows).drop_duplicates("metric_id")
    panel = (
        long_df.pivot_table(
            index=["country_iso3", "metric_id"], columns="year", values="value", aggfunc="mean"
        )
        .reset_index()
    )
    for y in YEARS:
        if y not in panel.columns:
            panel[y] = pd.NA
    panel.columns = [str(c) if isinstance(c, int) else c for c in panel.columns]
    panel = panel.merge(meta_df, on="metric_id", how="left")
    panel["sector"] = "Green mining & manufacturing"
    panel["subsector"] = panel["subsector"].fillna("Industrial competitiveness")
    panel["sub_sub_sector"] = panel["sub_sub_sector"].fillna("CIP component")
    panel["metric"] = panel["metric"].fillna(panel["metric_id"])
    panel["unit"] = panel["unit"].fillna("index or ratio (see UNIDO CIP metadata)")
    panel = panel[
        ["country_iso3", "sector", "subsector", "sub_sub_sector", "metric", "unit"]
        + [str(y) for y in YEARS]
    ]
    panel = ensure_all_countries(panel)
    return panel


ILOSTAT_DATASET_ID = "EMP_TEMP_SEX_ECO_NB_A"
ILOSTAT_URL = "https://rplumber.ilo.org/data/indicator/"


def fetch_ilostat() -> pd.DataFrame:
    params = {"id": ILOSTAT_DATASET_ID, "format": ".csv.gz"}
    try:
        r = SESSION.get(ILOSTAT_URL, params=params, timeout=300)
        r.raise_for_status()
    except requests.RequestException:
        return pd.DataFrame()
    buf = io.BytesIO(r.content)
    try:
        with gzip.open(buf, "rt", encoding="utf-8") as f:
            df = pd.read_csv(f)
    except Exception:
        return pd.DataFrame()
    return df


def tidy_ilostat(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df = df_raw.copy()
    if "time" not in df.columns or "ref_area" not in df.columns:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])
    df["year"] = df["time"].astype(int)
    df = df[df["year"].between(START_YEAR, CURRENT_YEAR)]
    df["country_iso3"] = df["ref_area"].astype(str).str.upper()
    df = df[df["country_iso3"].isin(AFRICA_ISO3)]
    if "sex" in df.columns:
        df = df[df["sex"] == "T"]
    eco_col = None
    for c in ["classif1", "eco"]:
        if c in df.columns:
            eco_col = c
            break
    if eco_col is None:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    metric_meta = {
        "B": {
            "metric": "Employment in mining and quarrying (thousands)",
            "subsector": "Mining",
            "sub_sub_sector": "Employment",
            "unit": "thousands of persons",
        },
        "C": {
            "metric": "Employment in manufacturing (thousands)",
            "subsector": "Manufacturing",
            "sub_sub_sector": "Employment",
            "unit": "thousands of persons",
        },
        "B-C": {
            "metric": "Employment in mining and manufacturing (thousands)",
            "subsector": "Mining and manufacturing",
            "sub_sub_sector": "Employment",
            "unit": "thousands of persons",
        },
    }
    df = df[df[eco_col].isin(metric_meta.keys())]
    if "obs_value" in df.columns:
        df["value"] = pd.to_numeric(df["obs_value"], errors="coerce")
    elif "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    else:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    df["metric_code"] = df[eco_col]
    meta_rows = []
    for code, meta in metric_meta.items():
        meta_rows.append(
            {
                "metric_code": code,
                "metric": meta["metric"],
                "subsector": meta["subsector"],
                "sub_sub_sector": meta["sub_sub_sector"],
                "unit": meta["unit"],
            }
        )
    meta_df = pd.DataFrame(meta_rows)
    df = df.merge(meta_df, on="metric_code", how="left")
    df["sector"] = "Green mining & manufacturing"
    df = df[
        [
            "country_iso3",
            "sector",
            "subsector",
            "sub_sub_sector",
            "metric",
            "unit",
            "year",
            "value",
        ]
    ]
    panel = (
        df.pivot_table(
            index=[
                "country_iso3",
                "sector",
                "subsector",
                "sub_sub_sector",
                "metric",
                "unit",
            ],
            columns="year",
            values="value",
            aggfunc="mean",
        )
        .reset_index()
    )
    for y in YEARS:
        if y not in panel.columns:
            panel[y] = pd.NA
    panel.columns = [str(c) if isinstance(c, int) else c for c in panel.columns]
    panel = panel[
        [
            "country_iso3",
            "sector",
            "subsector",
            "sub_sub_sector",
            "metric",
            "unit",
        ]
        + [str(y) for y in YEARS]
    ]
    panel = ensure_all_countries(panel)
    return panel


COMTRADE_REPORTER_CODES = {
    "DZA": 12,
    "AGO": 24,
    "BEN": 204,
    "BWA": 72,
    "BFA": 854,
    "BDI": 108,
    "CMR": 120,
    "CPV": 132,
    "CAF": 140,
    "TCD": 148,
    "COM": 174,
    "COD": 180,
    "COG": 178,
    "CIV": 384,
    "DJI": 262,
    "EGY": 818,
    "GNQ": 226,
    "ERI": 232,
    "ETH": 231,
    "GAB": 266,
    "GMB": 270,
    "GHA": 288,
    "GIN": 324,
    "GNB": 624,
    "KEN": 404,
    "LSO": 426,
    "LBR": 430,
    "LBY": 434,
    "MDG": 450,
    "MWI": 454,
    "MLI": 466,
    "MRT": 478,
    "MUS": 480,
    "MAR": 504,
    "MOZ": 508,
    "NAM": 516,
    "NER": 562,
    "NGA": 566,
    "RWA": 646,
    "STP": 678,
    "SEN": 686,
    "SYC": 690,
    "SLE": 694,
    "ZAF": 710,
    "SSD": 728,
    "SDN": 729,
    "SWZ": 748,
    "TZA": 834,
    "TGO": 768,
    "TUN": 788,
    "UGA": 800,
    "ZMB": 894,
    "ZWE": 716,
    "SOM": 706,
}


def fetch_comtrade() -> pd.DataFrame:
    api_key = os.getenv("COMTRADE_API_KEY")
    if not api_key:
        return pd.DataFrame()
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    base_url = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
    period_str = ",".join(str(y) for y in YEARS)
    frames = []
    for iso3 in AFRICA_ISO3:
        reporter_code = COMTRADE_REPORTER_CODES.get(iso3)
        if reporter_code is None:
            continue
        params = {
            "cmdCode": "TOTAL",
            "reporterCode": reporter_code,
            "partnerCode": "0",
            "period": period_str,
            "includeDesc": "true",
            "flowCode": "X,M",
        }
        try:
            r = SESSION.get(base_url, params=params, headers=headers, timeout=300)
            if r.status_code in (401, 403):
                continue
            r.raise_for_status()
        except requests.RequestException:
            continue
        resp = r.json()
        data = resp.get("data", [])
        if not data:
            continue
        df = json_to_df(data)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def tidy_comtrade(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df = df_raw.copy()

    year_col = None
    for c in ["period", "refYear", "ref_year"]:
        if c in df.columns:
            year_col = c
            break
    if year_col is None:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df[year_col] = pd.to_numeric(df[year_col], errors="coerce")
    df = df.dropna(subset=[year_col])
    df["year"] = df[year_col].astype(int)
    df = df[df["year"].between(START_YEAR, CURRENT_YEAR)]

    iso_col = None
    for c in ["reporterISO", "reporter_iso", "iso3", "country_iso3"]:
        if c in df.columns:
            iso_col = c
            break
    if iso_col is None:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df[iso_col] = df[iso_col].astype(str).str.upper()
    df = df[df[iso_col].isin(AFRICA_ISO3)]
    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    value_col = None
    for c in ["primaryValue", "primary_value", "TradeValue", "trade_value"]:
        if c in df.columns:
            value_col = c
            break
    if value_col is None:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df["value"] = pd.to_numeric(df[value_col], errors="coerce")
    if "flowCode" not in df.columns:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    frames = []
    metrics_meta = {
        "X": {
            "metric": "Total merchandise exports, all products (current US$)",
            "subsector": "Trade in goods",
            "sub_sub_sector": "Merchandise exports",
            "unit": "current US dollars",
        },
        "M": {
            "metric": "Total merchandise imports, all products (current US$)",
            "subsector": "Trade in goods",
            "sub_sub_sector": "Merchandise imports",
            "unit": "current US dollars",
        },
    }

    for flow_code, meta in metrics_meta.items():
        sub = df[df["flowCode"] == flow_code]
        if sub.empty:
            continue
        tmp = sub.copy()
        tmp["sector"] = "Green mining & manufacturing"
        tmp["subsector"] = meta["subsector"]
        tmp["sub_sub_sector"] = meta["sub_sub_sector"]
        tmp["metric"] = meta["metric"]
        tmp["unit"] = meta["unit"]
        tmp.rename(columns={iso_col: "country_iso3"}, inplace=True)
        frames.append(
            tmp[
                [
                    "country_iso3",
                    "sector",
                    "subsector",
                    "sub_sub_sector",
                    "metric",
                    "unit",
                    "year",
                    "value",
                ]
            ]
        )

    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df2 = pd.concat(frames, ignore_index=True)

    panel = (
        df2.pivot_table(
            index=[
                "country_iso3",
                "sector",
                "subsector",
                "sub_sub_sector",
                "metric",
                "unit",
            ],
            columns="year",
            values="value",
            aggfunc="sum",
        )
        .reset_index()
    )

    panel.columns = [str(c) if isinstance(c, int) else c for c in panel.columns]

    for y in YEARS:
        if y not in panel.columns:
            panel[y] = pd.NA

    panel = panel[
        [
            "country_iso3",
            "sector",
            "subsector",
            "sub_sub_sector",
            "metric",
            "unit",
        ]
        + YEARS
    ]

    panel = ensure_all_countries(panel)
    return panel



def main() -> None:
    all_records = []

    logging.info("Fetching World Bank WDI data...")
    wb_raw = fetch_worldbank_wdi()
    wb_panel = tidy_worldbank_wdi(wb_raw)

    if wb_panel is None or wb_panel.empty:
        logging.warning("World Bank WDI panel is empty; building stub panel instead.")
        wdi_meta_list = []
        for _code, meta in WDI_INDICATORS.items():
            wdi_meta_list.append(
                {
                    "sector": "Green mining & manufacturing",
                    "subsector": meta["subsector"],
                    "sub_sub_sector": meta["sub_sub_sector"],
                    "metric": meta["metric"],
                    "unit": meta["unit"],
                }
            )
        wb_panel = build_stub_panel_from_meta(wdi_meta_list)
    else:
        logging.info("World Bank WDI panel rows: %d", len(wb_panel))

    wb_panel["source"] = "World Bank World Development Indicators"
    wb_panel["source_url"] = "https://databank.worldbank.org/source/world-development-indicators"

    wb_records = build_records(
        title="World Bank WDI",
        df=wb_panel,
        default_sector="Green mining & manufacturing",
        source_file_path="worldbank_wdi_panel.csv",
        skip_initial_clean=True,
    )
    if wb_records:
        all_records.extend(wb_records)

    logging.info("Fetching UNIDO CIP data...")
    unido_raw = fetch_unido_cip()
    unido_panel = tidy_unido_cip(unido_raw)

    if unido_panel is None or unido_panel.empty:
        logging.warning("UNIDO CIP panel is empty; building stub panel instead.")
        unido_meta_list = [
            {
                "sector": "Green mining & manufacturing",
                "subsector": "Industrial competitiveness",
                "sub_sub_sector": "Competitive Industrial Performance index",
                "metric": "Competitive Industrial Performance (CIP) index",
                "unit": "index (0-1, UNIDO definition)",
            }
        ]
        unido_panel = build_stub_panel_from_meta(unido_meta_list)
    else:
        logging.info("UNIDO CIP panel rows: %d", len(unido_panel))
    
    unido_panel["source"] = "UNIDO Statistics (CIP database)"
    unido_panel["source_url"] = "https://stat.unido.org"

    unido_records = build_records(
        title="UNIDO CIP",
        df=unido_panel,
        default_sector="Green mining & manufacturing",
        source_file_path="unido_cip_panel.csv",
        skip_initial_clean=True,
    )
    if unido_records:
        all_records.extend(unido_records)

    logging.info("Fetching ILOSTAT data...")
    ilo_raw = fetch_ilostat()
    ilo_panel = tidy_ilostat(ilo_raw)

    if ilo_panel is None or ilo_panel.empty:
        logging.warning("ILOSTAT panel is empty; building stub panel instead.")
        ilo_meta_list = [
            {
                "sector": "Green mining & manufacturing",
                "subsector": "Employment in mining and manufacturing",
                "sub_sub_sector": "Employment by sex and economic activity",
                "metric": "Number of employees by sex and economic activity",
                "unit": "Thousands of persons",
            }
        ]
        ilo_panel = build_stub_panel_from_meta(ilo_meta_list)
    else:
        logging.info("ILOSTAT panel rows: %d", len(ilo_panel))
    
    ilo_panel["source"] = "ILO ILOSTAT"
    ilo_panel["source_url"] = "https://ilostat.ilo.org"

    ilo_records = build_records(
        title="ILOSTAT",
        df=ilo_panel,
        default_sector="Green mining & manufacturing",
        source_file_path="ilostat_emp_panel.csv",
        skip_initial_clean=True,
    )
    if ilo_records:
        all_records.extend(ilo_records)

    logging.info("Fetching Comtrade data...")
    comtrade_raw = fetch_comtrade()
    comtrade_panel = tidy_comtrade(comtrade_raw)

    if comtrade_panel is None or comtrade_panel.empty:
        logging.warning("Comtrade panel is empty; building stub panel instead.")
        comtrade_meta_list = [
            {
                "sector": "Green mining & manufacturing",
                "subsector": "Trade in goods",
                "sub_sub_sector": "Merchandise exports",
                "metric": "Total merchandise exports, all products (current US$)",
                "unit": "current US dollars",
            },
            {
                "sector": "Green mining & manufacturing",
                "subsector": "Trade in goods",
                "sub_sub_sector": "Merchandise imports",
                "metric": "Total merchandise imports, all products (current US$)",
                "unit": "current US dollars",
            },
        ]
        comtrade_panel = build_stub_panel_from_meta(comtrade_meta_list)
    else:
        logging.info("Comtrade panel rows: %d", len(comtrade_panel))

    comtrade_panel["source"] = "UN Comtrade"
    comtrade_panel["source_url"] = "https://comtradeplus.un.org"

    comtrade_records = build_records(
        title="Comtrade",
        df=comtrade_panel,
        default_sector="Green mining & manufacturing",
        source_file_path="comtrade_trade_panel.csv",
        skip_initial_clean=True,
    )
    if comtrade_records:
        all_records.extend(comtrade_records)

    logging.info("Total records prepared for upsert (all sources): %d", len(all_records))

    return all_records


if __name__ == "__main__":
    main()
