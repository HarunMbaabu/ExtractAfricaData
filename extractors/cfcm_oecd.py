# extractors/cfcm_oecd.py
import io
import os
import re
from typing import Dict, List, Optional
from datetime import datetime

import pandas as pd
import requests

from clean_transform import build_records

OECD_URL = (
    "https://sdmx.oecd.org/dcd-public/rest/data/"
    "OECD.DCD.FSD,DSD_RIOMRKR@DF_RIOMARKERS,1.4/"
    "DAC_EC.EGY+LBY+MAR+TUN+BDI+COM+DJI+ERI+ETH+KEN+MDG+MWI+MUS+MOZ+RWA+SOM+SSD+SDN+TZA+UGA+ZMB+ZWE+AGO+CMR+CAF+TCD+COG+COD+GNQ+GAB+STP+BWA+SWZ+LSO+NAM+ZAF+BEN+BFA+CPV+CIV+GMB+GHA+GIN+GNB+LBR+MLI+NER+MRT+NGA+SEN+SLE+TGO+DZA.1000..2.10...Q._T.."
    "?startPeriod=2015&endPeriod=2024&dimensionAtObservation=AllDimensions&format=csvfilewithlabels"
)

START_YEAR = 2015
CURRENT_YEAR = datetime.now().year 
YEARS = [str(y) for y in range(START_YEAR, CURRENT_YEAR + 1)]


def _pick(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _extract_year(x) -> Optional[str]:
    if pd.isna(x):
        return None
    m = re.search(r"\b(19|20)\d{2}\b", str(x))
    return m.group(0) if m else None


def _load_labelled_csv(src: Optional[str] = None) -> pd.DataFrame:
    if src and os.path.exists(src):
        return pd.read_csv(src)
    if src and src.startswith("http"):
        r = requests.get(src, headers={"Accept": "text/csv"}, timeout=300)
        r.raise_for_status()
        return pd.read_csv(io.BytesIO(r.content))
    r = requests.get(OECD_URL, headers={"Accept": "text/csv"}, timeout=300)
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content))


def _categorize(structure_name: str) -> tuple[str, str, str]:
    s = (structure_name or "").lower()
    sector = "Climate Finance & Carbon Markets"
    sub_sector = "Climate Finance"
    sub_sub_sector = "International Financial Flows Received"
    if any(k in s for k in ("carbon", "ets", "trading", "pricing")):
        sub_sector = "Carbon Markets"
        sub_sub_sector = "Compliance & Pricing Instruments"
    elif "bond" in s:
        sub_sector = "Climate Finance"
        sub_sub_sector = "Green/Climate Bonds"
    return sector, sub_sector, sub_sub_sector


def _metric(marker, score, measure) -> str:
    m = ("" if pd.isna(marker) else str(marker).strip())
    sc = ("" if pd.isna(score) else str(score).strip().lower())
    meas = ("" if pd.isna(measure) else str(measure).strip()) or "Value"
    if m and sc in ("principal", "significant"):
        m = f"{m} ({sc})"
    return f"{m} – {meas}" if m else meas


CF_CM_WDI_INDICATORS = {
    "NY.ADJ.DCO2.CD": {
        "metric": "Adjusted net savings: carbon dioxide damage (current US$)",
        "unit": "current US dollars",
        "sub_sector": "Climate Finance",
        "sub_sub_sector": "Carbon externality cost",
    },
    "NY.ADJ.DCO2.GN.ZS": {
        "metric": "Adjusted net savings: carbon dioxide damage (% of GNI)",
        "unit": "percent of GNI",
        "sub_sector": "Climate Finance",
        "sub_sub_sector": "Carbon externality cost",
    },
    "EN.ATM.CO2E.KT": {
        "metric": "CO2 emissions (kt)",
        "unit": "kilotonnes CO2e",
        "sub_sector": "Carbon Markets",
        "sub_sub_sector": "Emissions baseline",
    },
    "EN.ATM.CO2E.PC": {
        "metric": "CO2 emissions (metric tons per capita)",
        "unit": "metric tons CO2e per capita",
        "sub_sector": "Carbon Markets",
        "sub_sub_sector": "Emissions baseline",
    },
    "EN.ATM.GHGT.KT.CE": {
        "metric": "Total greenhouse gas emissions (kt of CO2 equivalent)",
        "unit": "kilotonnes CO2e",
        "sub_sector": "Carbon Markets",
        "sub_sub_sector": "Emissions baseline",
    },
}


def extract_worldbank_cfcm_wdi() -> List[dict]:
    frames = []
    for code, meta in CF_CM_WDI_INDICATORS.items():
        url = f"https://api.worldbank.org/v2/country/all/indicator/{code}"
        params = {
            "date": "2015:2024",
            "format": "json",
            "per_page": 20000,
        }
        page = 1
        rows_all: list[dict] = []
        while True:
            params["page"] = page
            r = requests.get(url, params=params, timeout=60)
            if r.status_code >= 400:
                break
            data = r.json()
            if not isinstance(data, list) or len(data) < 2:
                break
            meta_block, rows = data[0], data[1]
            if not rows:
                break
            rows_all.extend(rows)
            pages = meta_block.get("pages", 1)
            if page >= pages:
                break
            page += 1
        if not rows_all:
            continue
        df = pd.json_normalize(rows_all)
        df["indicator_code"] = code
        frames.append(df)

    if not frames:
        return []

    df_all = pd.concat(frames, ignore_index=True)

    df_all["year"] = pd.to_numeric(df_all.get("date"), errors="coerce")
    df_all = df_all[df_all["year"].between(2015, 2024)]
    df_all["year"] = df_all["year"].astype("Int64")

    if "country.value" in df_all.columns:
        df_all["country"] = df_all["country.value"]
    elif "country" in df_all.columns and df_all["country"].dtype == object:
        df_all["country"] = df_all["country"]
    else:
        df_all["country"] = df_all.get("countryiso3code", pd.NA)

    df_all["value"] = pd.to_numeric(df_all.get("value"), errors="coerce")
    df_all = df_all.dropna(subset=["country", "value", "year"])

    meta_rows = []
    for code, meta in CF_CM_WDI_INDICATORS.items():
        meta_rows.append(
            {
                "indicator_code": code,
                "metric": meta["metric"],
                "unit": meta["unit"],
                "sub_sector": meta["sub_sector"],
                "sub_sub_sector": meta["sub_sub_sector"],
            }
        )
    meta_df = pd.DataFrame(meta_rows)

    if "indicator_code" in df_all.columns:
        df_all = df_all.merge(meta_df, on="indicator_code", how="left")
    else:
        df_all["metric"] = pd.NA
        df_all["unit"] = pd.NA
        df_all["sub_sector"] = pd.NA
        df_all["sub_sub_sector"] = pd.NA

    df_all["sector"] = "Climate Finance & Carbon Markets"
    df_all["year"] = df_all["year"].astype(str)

    for col in ["metric", "unit", "sub_sector", "sub_sub_sector"]:
        if col not in df_all.columns:
            df_all[col] = pd.NA

    df_all = df_all[
        [
            "sector",
            "sub_sector",
            "sub_sub_sector",
            "country",
            "metric",
            "unit",
            "year",
            "value",
        ]
    ]

    panel = (
        df_all.groupby(
            [
                "sector",
                "sub_sector",
                "sub_sub_sector",
                "country",
                "metric",
                "unit",
                "year",
            ],
            as_index=False,
        )["value"]
        .mean()
        .pivot(
            index=[
                "sector",
                "sub_sector",
                "sub_sub_sector",
                "country",
                "metric",
                "unit",
            ],
            columns="year",
            values="value",
        )
        .reset_index()
    )

    for y in YEARS:
        if y not in panel.columns:
            panel[y] = pd.NA

    panel["source_link"] = "https://databank.worldbank.org/source/world-development-indicators"
    panel["sources"] = "World Bank World Development Indicators"

    panel = panel[
        ["sector", "sub_sector", "sub_sub_sector", "country", "metric", "unit"]
        + YEARS
        + ["source_link", "sources"]
    ]

    docs = build_records(
        title="WorldBank_CF_CM_WDI_2015_2024",
        df=panel,
        default_sector="Climate Finance & Carbon Markets",
        source_file_path="worldbank_cfcm_wdi_2015_2024.csv",
        skip_initial_clean=True,
    )
    return docs


def extract_oecd_riomarkers(source: Optional[str] = None) -> Dict[str, List[dict]]:
    df = _load_labelled_csv(source)

    c_struct = _pick(df, "STRUCTURE_NAME", "Structure name", "STRUCTURE", "Structure")
    c_rcpt = _pick(df, "Recipient", "RECIPIENT")
    c_time = _pick(df, "TIME_PERIOD", "Time period")
    c_unit = _pick(df, "Unit of measure", "UNIT_MEASURE")
    c_value = _pick(df, "OBS_VALUE", "Observation value")
    c_marker = _pick(df, "Marker", "MARKER")
    c_score = _pick(df, "Score", "SCORE")
    c_measure = _pick(df, "Measure", "MEASURE")

    required = [c_struct, c_rcpt, c_time, c_unit, c_value]
    if any(c is None for c in required):
        raise RuntimeError(f"Missing required columns in OECD CSV. Found: {list(df.columns)}")

    df["_year"] = df[c_time].apply(_extract_year)
    df = df[df["_year"].isin(YEARS)].copy()

    recs = []
    for _, r in df.iterrows():
        sector, sub_sector, sub_sub_sector = _categorize(
            str(r[c_struct]) if pd.notna(r[c_struct]) else ""
        )
        country = str(r[c_rcpt]) if pd.notna(r[c_rcpt]) else None
        unit = str(r[c_unit]) if pd.notna(r[c_unit]) else None
        year = str(r["_year"])
        value = pd.to_numeric(r[c_value], errors="coerce")
        metric = _metric(
            r[c_marker] if c_marker else None,
            r[c_score] if c_score else None,
            r[c_measure] if c_measure else None,
        )
        recs.append(
            {
                "sector": sector,
                "sub_sector": sub_sector,
                "sub_sub_sector": sub_sub_sector,
                "country": country,
                "metric": metric,
                "unit": unit,
                "year": year,
                "value": value,
            }
        )

    long_df = pd.DataFrame(recs)
    if long_df.empty:
        raise RuntimeError("No rows after mapping OECD Rio Markers data.")

    wide = (
        long_df.groupby(
            [
                "sector",
                "sub_sector",
                "sub_sub_sector",
                "country",
                "metric",
                "unit",
                "year",
            ],
            as_index=False,
        )["value"]
        .sum()
        .pivot(
            index=[
                "sector",
                "sub_sector",
                "sub_sub_sector",
                "country",
                "metric",
                "unit",
            ],
            columns="year",
            values="value",
        )
        .reset_index()
    )

    for y in YEARS:
        if y not in wide.columns:
            wide[y] = pd.NA

    wide["source_link"] = "https://sdmx.oecd.org/"
    wide["sources"] = "OECD Rio Markers"

    ordered = (
        ["sector", "sub_sector", "sub_sub_sector", "country", "metric", "unit"]
        + YEARS
        + ["source_link", "sources"]
    )
    wide = wide[ordered]

    docs_oecd = build_records(
        title="OECD_RioMarkers_2015_2024",
        df=wide,
        default_sector=None,
        source_file_path="oecd_riomarkers_africa_2015_2024.csv",
        skip_initial_clean=True,
    )

    docs_wdi = extract_worldbank_cfcm_wdi()

    return {
        "OECD_RioMarkers_2015_2024": docs_oecd,
        "WorldBank_CF_CM_WDI_2015_2024": docs_wdi,
    }
