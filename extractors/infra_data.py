from pathlib import Path
import pandas as pd
import requests
import logging
from clean_transform import build_records
from datetime import datetime

BASE_DIR = Path("data") / "infra_urban"
BASE_DIR.mkdir(parents=True, exist_ok=True)

START_YEAR = 2015
CURRENT_YEAR = datetime.now().year  
YEARS = [str(y) for y in range(START_YEAR, CURRENT_YEAR + 1)]

AFRICA_ISO3_TO_NAME = {
    "DZA": "Algeria",
    "AGO": "Angola",
    "BEN": "Benin",
    "BWA": "Botswana",
    "BFA": "Burkina Faso",
    "BDI": "Burundi",
    "CPV": "Cabo Verde",
    "CMR": "Cameroon",
    "CAF": "Central African Republic",
    "TCD": "Chad",
    "COM": "Comoros",
    "COG": "Congo",
    "COD": "Congo, Dem. Rep.",
    "CIV": "Côte d'Ivoire",
    "DJI": "Djibouti",
    "EGY": "Egypt",
    "GNQ": "Equatorial Guinea",
    "ERI": "Eritrea",
    "SWZ": "Eswatini",
    "ETH": "Ethiopia",
    "GAB": "Gabon",
    "GMB": "Gambia",
    "GHA": "Ghana",
    "GIN": "Guinea",
    "GNB": "Guinea-Bissau",
    "KEN": "Kenya",
    "LSO": "Lesotho",
    "LBR": "Liberia",
    "LBY": "Libya",
    "MDG": "Madagascar",
    "MWI": "Malawi",
    "MLI": "Mali",
    "MRT": "Mauritania",
    "MUS": "Mauritius",
    "MAR": "Morocco",
    "MOZ": "Mozambique",
    "NAM": "Namibia",
    "NER": "Niger",
    "NGA": "Nigeria",
    "RWA": "Rwanda",
    "STP": "Sao Tome and Principe",
    "SEN": "Senegal",
    "SYC": "Seychelles",
    "SLE": "Sierra Leone",
    "SOM": "Somalia",
    "ZAF": "South Africa",
    "SSD": "South Sudan",
    "SDN": "Sudan",
    "TZA": "Tanzania",
    "TGO": "Togo",
    "TUN": "Tunisia",
    "UGA": "Uganda",
    "ZMB": "Zambia",
    "ZWE": "Zimbabwe",
}

AFRICA_ISO3 = sorted(AFRICA_ISO3_TO_NAME.keys())

WORLD_BANK_INFRA_META = {
    "EG.ELC.ACCS.ZS": {
        "metric": "Access to electricity (% of population)",
        "unit": "percent of population",
        "sector": "Sustainable infrastructure & urbanisation",
        "subsector": "Energy infrastructure",
        "sub_sub_sector": "Access to electricity (total)",
    },
    "EG.ELC.ACCS.UR.ZS": {
        "metric": "Access to electricity, urban (% of urban population)",
        "unit": "percent of urban population",
        "sector": "Sustainable infrastructure & urbanisation",
        "subsector": "Energy infrastructure",
        "sub_sub_sector": "Access to electricity (urban)",
    },
    "EG.ELC.ACCS.RU.ZS": {
        "metric": "Access to electricity, rural (% of rural population)",
        "unit": "percent of rural population",
        "sector": "Sustainable infrastructure & urbanisation",
        "subsector": "Energy infrastructure",
        "sub_sub_sector": "Access to electricity (rural)",
    },
    "EG.ELC.LOSS.ZS": {
        "metric": "Electric power transmission and distribution losses (% of output)",
        "unit": "percent of output",
        "sector": "Sustainable infrastructure & urbanisation",
        "subsector": "Energy infrastructure",
        "sub_sub_sector": "Network losses",
    },
    "IS.ROD.PAVE.ZS": {
        "metric": "Paved roads (% of total roads)",
        "unit": "percent of total roads",
        "sector": "Sustainable infrastructure & urbanisation",
        "subsector": "Transport infrastructure",
        "sub_sub_sector": "Road quality (paved share)",
    },
    "SP.URB.TOTL.IN.ZS": {
        "metric": "Urban population (% of total population)",
        "unit": "percent of total population",
        "sector": "Sustainable infrastructure & urbanisation",
        "subsector": "Urbanisation",
        "sub_sub_sector": "Urban population share",
    },
}

BBOXES = {
    "nairobi": "36.6,-1.5,37.0,-1.1"
}


def json_to_df(obj):
    if isinstance(obj, dict):
        if "data" in obj and isinstance(obj["data"], (list, dict)):
            return pd.json_normalize(obj["data"])
        if "result" in obj and isinstance(obj["result"], (list, dict)):
            return pd.json_normalize(obj["result"])
        return pd.json_normalize(obj)
    if isinstance(obj, list):
        return pd.json_normalize(obj)
    return pd.json_normalize(obj)


def get_africa_countries_df():
    items = sorted(AFRICA_ISO3_TO_NAME.items())
    return pd.DataFrame(items, columns=["country_iso3", "country"])


def panel_wide_all_countries(df_long, africa_df, years):
    if df_long.empty:
        return pd.DataFrame()
    df_long = df_long.copy()
    df_long["year"] = pd.to_numeric(df_long["year"], errors="coerce")
    df_long = df_long[df_long["year"].isin(years)]
    metric_meta = (
        df_long[["sector", "subsector", "sub_sub_sector", "metric", "unit"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    base = africa_df.assign(key=1).merge(
        metric_meta.assign(key=1), on="key"
    ).drop("key", axis=1)
    panel = df_long.pivot_table(
        index=[
            "country_iso3",
            "country",
            "sector",
            "subsector",
            "sub_sub_sector",
            "metric",
            "unit",
        ],
        columns="year",
        values="value",
        aggfunc="first",
    )
    panel = panel.reindex(columns=years)
    panel = panel.reset_index()
    result = base.merge(
        panel,
        on=[
            "country_iso3",
            "country",
            "sector",
            "subsector",
            "sub_sub_sector",
            "metric",
            "unit",
        ],
        how="left",
    )
    result = result.sort_values(["country_iso3", "metric"]).reset_index(drop=True)
    return result


def fetch_worldbank_indicator(iso3_list, indicator_code, start_year, end_year):
    country_str = ";".join(iso3_list)
    url = f"https://api.worldbank.org/v2/country/{country_str}/indicator/{indicator_code}"
    params = {
        "date": f"{start_year}:{end_year}",
        "format": "json",
        "per_page": 20000,
    }
    all_rows = []
    page = 1
    while True:
        params["page"] = page
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        if not data or len(data) < 2:
            break
        meta, rows = data[0], data[1]
        if not rows:
            break
        all_rows.extend(rows)
        pages = meta.get("pages", 1)
        if page >= pages:
            break
        page += 1
    if not all_rows:
        return pd.DataFrame()
    return pd.json_normalize(all_rows)


def fetch_worldbank_infra_urban(iso3_list, start_year, end_year):
    frames = []
    for code in WORLD_BANK_INFRA_META.keys():
        df = fetch_worldbank_indicator(iso3_list, code, start_year, end_year)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def tidy_worldbank_infra_urban(raw_df):
    if raw_df.empty:
        return pd.DataFrame()
    df = raw_df.copy()
    df["year"] = pd.to_numeric(df["date"], errors="coerce")
    df = df[df["year"].between(START_YEAR, CURRENT_YEAR)]
    df["country_iso3"] = df["countryiso3code"]
    df = df[df["country_iso3"].isin(AFRICA_ISO3)]
    df["country"] = df["country_iso3"].map(AFRICA_ISO3_TO_NAME)
    df["indicator_code"] = df["indicator.id"]
    df = df[~df["value"].isna()]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df[~df["value"].isna()]
    frames = []
    for code, meta in WORLD_BANK_INFRA_META.items():
        sub = df[df["indicator_code"] == code].copy()
        if sub.empty:
            continue
        sub["sector"] = meta["sector"]
        sub["subsector"] = meta["subsector"]
        sub["sub_sub_sector"] = meta["sub_sub_sector"]
        sub["metric"] = meta["metric"]
        sub["unit"] = meta["unit"]
        frames.append(
            sub[
                [
                    "country_iso3",
                    "country",
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
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_ohsome_buildings(bboxes, start_year, end_year):
    url = "https://api.ohsome.org/v1/elements/count"
    time_str = f"{start_year}-01-01/{end_year}-12-31/P1Y"
    frames = []
    for name, bbox in bboxes.items():
        data = {
            "bboxes": bbox,
            "time": time_str,
            "filter": "building=* and type:way",
            "format": "json",
        }
        try:
            r = requests.post(url, data=data, timeout=120)
        except requests.RequestException:
            continue
        if r.status_code >= 500:
            continue
        try:
            r.raise_for_status()
        except requests.HTTPError:
            continue
        resp = r.json()
        df = json_to_df(resp.get("result", resp))
        if not df.empty:
            df["bbox_name"] = name
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def main() -> list:
    logging.info("Fetching infrastructure data...")
    infra_raw = fetch_worldbank_infra_urban(AFRICA_ISO3, START_YEAR, CURRENT_YEAR)
    infra_panel = tidy_worldbank_infra_urban(infra_raw)
    infra_records = build_records(
        title="Infrastructure Data",
        df=infra_panel,
        default_sector="Infrastructure",
        source_file_path="infra_panel.csv",
        skip_initial_clean=True
    )
    return infra_records


if __name__ == "__main__":
    main()
