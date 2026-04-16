from __future__ import annotations

import time
import re
import csv
import os
import sys
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

import cloudscraper 
import requests
import pandas as pd
from dotenv import load_dotenv

from constants import COUNTRIES, ENERGY_INDICATORS, normalize_country, serial_for_country
from clean_transform import build_records

load_dotenv()

# Ensure project root on path (for constants, etc.)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --------------------------------------------------------------------------------------
# Africa Energy Portal scraper (source 1)
# --------------------------------------------------------------------------------------

ENDPOINT = "https://africa-energy-portal.org/get-database-data"
START_YEAR = 2015
CURRENT_YEAR = datetime.now().year 
YEARS = [str(y) for y in range(START_YEAR, CURRENT_YEAR + 1)]


def build_payload(indicator: str) -> dict:
    return {
        "mainGroup": "Electricity",
        "mainIndicator[]": ["Access", "Supply", "Technical"],
        "mainIndicatorValue[]": indicator,
        "year[]": YEARS,
        "name[]": COUNTRIES,
    }


def extract_source(url: str) -> str:
    match = re.search(r"https?://([^/]+)", url)
    return match.group(1) if match else ""


def strip_extension(url: str) -> str:
    return re.sub(r"\.[a-zA-Z0-9]+$", "", url)


def enrich_subsector(metric: str) -> tuple[str, str]:
    m = metric.lower()
    if any(k in m for k in ["with access", "without access", "access to electricity"]):
        return "Power Transmission & Distribution", "General"
    if any(k in m for k in ["transmission", "distribution", "supply", "renewable"]):
        return "Renewable Power Transmission & Distribution", "General"
    if "clean cooking" in m or "clean fuels" in m:
        return "Clean Cooking", "General"
    if any(k in m for k in ["investment", "funding", "finance", "private participation"]):
        return "Energy Funding", "General"
    if any(k in m for k in ["efficiency", "intensity", "per $", "per kg of oil"]):
        return "Energy Efficiency", "General"
    if any(
        k in m
        for k in [
            "generation",
            "installed capacity",
            "production",
            "output",
            "consumption",
            "demand",
            "generated",
        ]
    ):
        if "solar" in m:
            return "Power Generation", "Solar"
        if "wind" in m:
            return "Power Generation", "Wind"
        if "geothermal" in m:
            return "Power Generation", "Geothermal"
        return "Power Generation", "Power Generation"
    return "Energy Policy", "General"


def clean_transform(entry: dict, metric: str) -> dict | None:
    raw_country = entry.get("name")
    country = normalize_country(raw_country)
    if not country:
        return None

    year = str(entry.get("year"))
    score = entry.get("score")
    unit = entry.get("unit")
    ig = entry.get("indicator_group", "Electricity")
    it = entry.get("indicator_topic", "Access")
    url = "https://africa-energy-portal.org" + (entry.get("url") or "")
    source = extract_source(url)
    source_link = strip_extension(url)
    serial = serial_for_country(country)
    sub_sector, sub_sub_sector = enrich_subsector(metric)

    return {
        "country": country,
        "country_serial": serial,
        "metric": metric,
        "unit": unit,
        "sector": "Energy",
        "sub_sector": sub_sector,
        "sub_sub_sector": sub_sub_sector,
        "source_link": source_link,
        "source": source,
        "tags": f"{ig.lower()}|{it.lower()}|{metric.lower()}",
        "created_at": datetime.now().isoformat() + "Z",
        "year": year,
        "score": score,
    }


def extract_africa_energy_panel() -> List[Dict[str, Any]]:
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://africa-energy-portal.org",
        "Referer": "https://africa-energy-portal.org/database",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "X-Requested-With": "XMLHttpRequest",
        "x-kl-kis-ajax-request": "Ajax_Request",
    }

    try:
        scraper.get("https://africa-energy-portal.org/database", timeout=60)
    except Exception as e:
        logging.warning("AEP warm-up request failed: %s", e)

    rows: dict[tuple[str, str], Dict[str, Any]] = {}
    total_indicators = len(ENERGY_INDICATORS)
    consecutive_403 = 0

    for i, indicator in enumerate(ENERGY_INDICATORS, 1):
        payload = build_payload(indicator)
        try:
            resp = scraper.post(ENDPOINT, headers=headers, data=payload, timeout=60)
            if resp.status_code == 403:
                consecutive_403 += 1
                logging.error(
                    "[%d/%d] %s: 403 Forbidden from Africa Energy Portal",
                    i,
                    total_indicators,
                    indicator,
                )
                if consecutive_403 >= 3 and not rows:
                    logging.warning(
                        "Multiple 403s from AEP with no data collected; "
                        "aborting Africa Energy Portal scraping for this run."
                    )
                    return []
                time.sleep(1)
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logging.error(
                "[%d/%d] %s: request failed: %s", i, total_indicators, indicator, e
            )
            time.sleep(1)
            continue

        consecutive_403 = 0
        if not isinstance(data, list):
            data = [data]

        for block in data:
            for entry in block.get("data", []):
                row = clean_transform(entry, indicator)
                if not row:
                    continue
                key = (row["country"], row["metric"])
                if key not in rows:
                    rows[key] = {
                        "country": row["country"],
                        "country_serial": row["country_serial"],
                        "metric": row["metric"],
                        "unit": row["unit"],
                        "sector": row["sector"],
                        "sub_sector": row["sub_sector"],
                        "sub_sub_sector": row["sub_sub_sector"],
                        "source_link": row["source_link"],
                        "source": row["source"],
                        "tags": row["tags"],
                        "created_at": row["created_at"],
                        **{y: None for y in YEARS},
                    }
                rows[key][row["year"]] = row["score"]

        logging.info(
            "[%d/%d] %s: collected %d rows",
            i,
            total_indicators,
            indicator,
            len(rows),
        )

    return list(rows.values())



def export_africa_energy_to_csv(path: str = "africa_energy_data.csv") -> None:
    """
    Preserve the original CSV-writing behaviour from the standalone scraper.
    """
    rows = extract_africa_energy_panel()
    header = [
        "country",
        "country_serial",
        "metric",
        "unit",
        "sector",
        "sub_sector",
        "sub_sub_sector",
        "source_link",
        "source",
    ] + YEARS
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow([row.get(col) for col in header])


# --------------------------------------------------------------------------------------
# World Bank WDI energy indicators (source 2)
# --------------------------------------------------------------------------------------

START_YEAR, END_YEAR = 2015, 2024
YEAR_COLS = [str(y) for y in range(START_YEAR, END_YEAR + 1)]
WDI_BASE = (
    "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"
    "?date={start}:{end}&format=json&per_page=20000"
)
WDI_COUNTRIES_URL = (
    "https://api.worldbank.org/v2/region/AFR/country?per_page=300&format=json"
)

INDICATORS = {
    "EG.FEC.RNEW.ZS": "Renewable energy consumption (% of total final energy consumption)",
    "EG.ELC.RNEW.ZS": "Renewable electricity output (% of total electricity output)",
    "IE.PPN.ENGY.CD": "Public private partnerships investment in energy (current US$)",
    "EN.GHG.N2O.TR.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Transport (Energy) (Mt CO2e)",
    "EN.GHG.N2O.PI.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Power Industry (Energy) (Mt CO2e)",
    "EN.GHG.N2O.IC.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Industrial Combustion (Energy) (Mt CO2e)",
    "EN.GHG.N2O.FE.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Fugitive Emissions (Energy) (Mt CO2e)",
    "EN.GHG.N2O.BU.MT.CE.AR5": "Nitrous oxide (N2O) emissions from Building (Energy) (Mt CO2e)",
    "EN.GHG.CH4.TR.MT.CE.AR5": "Methane (CH4) emissions from Transport (Energy) (Mt CO2e)",
    "EN.GHG.CH4.PI.MT.CE.AR5": "Methane (CH4) emissions from Power Industry (Energy) (Mt CO2e)",
    "EN.GHG.CH4.IC.MT.CE.AR5": "Methane (CH4) emissions from Industrial Combustion (Energy) (Mt CO2e)",
    "EN.GHG.CH4.FE.MT.CE.AR5": "Methane (CH4) emissions from Fugitive Emissions (Energy) (Mt CO2e)",
    "EN.GHG.CH4.BU.MT.CE.AR5": "Methane (CH4) emissions from Building (Energy) (Mt CO2e)",
    "IE.PPI.ENGY.CD": "Investment in energy with private participation (current US$)",
    "EG.GDP.PUSE.KO.PP": "GDP per unit of energy use (PPP $ per kg of oil equivalent)",
    "EG.GDP.PUSE.KO.PP.KD": "GDP per unit of energy use (constant 2021 PPP $ per kg of oil equivalent)",
    "EG.USE.COMM.FO.ZS": "Fossil fuel energy consumption (% of total)",
    "IC.FRM.ENGM.ZS": "Firms adopting energy management measures to reduce emissions (% of firms)",
    "EG.USE.COMM.GD.PP.KD": "Energy use (kg of oil equivalent) per $1,000 GDP (constant 2021 PPP)",
    "EG.USE.PCAP.KG.OE": "Energy use (kg of oil equivalent per capita)",
    "EG.EGY.PRIM.PP.KD": "Energy intensity level of primary energy (MJ/$2017 PPP GDP)",
    "EG.IMP.CONS.ZS": "Energy imports, net (% of energy use)",
    "EG.ELC.RNWX.KH": "Electricity production from renewable sources, excluding hydroelectric (kWh)",
    "EG.ELC.RNWX.ZS": "Electricity production from renewable sources, excluding hydroelectric (% of total)",
    "EG.ELC.FOSL.ZS": "Electricity production from oil, gas and coal sources (% of total)",
    "EG.ELC.PETR.ZS": "Electricity production from oil sources (% of total)",
    "EG.ELC.NUCL.ZS": "Electricity production from nuclear sources (% of total)",
    "EG.ELC.NGAS.ZS": "Electricity production from natural gas sources (% of total)",
    "EG.ELC.HYRO.ZS": "Electricity production from hydroelectric sources (% of total)",
    "EG.ELC.COAL.ZS": "Electricity production from coal sources (% of total)",
    "EG.USE.CRNW.ZS": "Combustible renewables and waste (% of total energy)",
    "EN.GHG.CO2.TR.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Transport (Energy) (Mt CO2e)",
    "EN.GHG.CO2.PI.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Power Industry (Energy) (Mt CO2e)",
    "EN.GHG.CO2.IC.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Industrial Combustion (Energy) (Mt CO2e)",
    "EN.GHG.CO2.FE.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Fugitive Emissions (Energy) (Mt CO2e)",
    "EN.GHG.CO2.BU.MT.CE.AR5": "Carbon dioxide (CO2) emissions from Building (Energy) (Mt CO2e)",
    "EG.USE.COMM.CL.ZS": "Alternative and nuclear energy (% of total energy use)",
    "NY.ADJ.DNGY.CD": "Adjusted savings: energy depletion (current US$)",
    "NY.ADJ.DNGY.GN.ZS": "Adjusted savings: energy depletion (% of GNI)",
    "EG.ELC.ACCS.UR.ZS": "Access to electricity, urban (% of urban population)",
    "EG.ELC.ACCS.RU.ZS": "Access to electricity, rural (% of rural population)",
    "EG.ELC.ACCS.ZS": "Access to electricity (% of population)",
    "EG.CFT.ACCS.UR.ZS": "Access to clean fuels and technologies for cooking, urban (% of urban population)",
    "EG.CFT.ACCS.RU.ZS": "Access to clean fuels and technologies for cooking, rural (% of rural population)",
    "EG.CFT.ACCS.ZS": "Access to clean fuels and technologies for cooking (% of population)",
}

SUBSECTOR_BY_CODE = {
    "EG.CFT.ACCS.UR.ZS": "Clean Cooking",
    "EG.CFT.ACCS.RU.ZS": "Clean Cooking",
    "EG.CFT.ACCS.ZS": "Clean Cooking",
    "IE.PPN.ENGY.CD": "Energy Funding",
    "IE.PPI.ENGY.CD": "Energy Funding",
    "IC.FRM.ENGM.ZS": "Energy Policy",
    "EG.GDP.PUSE.KO.PP": "Energy Efficiency",
    "EG.GDP.PUSE.KO.PP.KD": "Energy Efficiency",
    "EG.USE.COMM.GD.PP.KD": "Energy Efficiency",
    "EG.USE.PCAP.KG.OE": "Energy Efficiency",
    "EG.EGY.PRIM.PP.KD": "Energy Efficiency",
    "EG.FEC.RNEW.ZS": "Energy Policy",
    "EG.IMP.CONS.ZS": "Energy Policy",
    "NY.ADJ.DNGY.CD": "Energy Policy",
    "NY.ADJ.DNGY.GN.ZS": "Energy Policy",
    "EG.ELC.RNEW.ZS": "Power Generation",
    "EG.ELC.RNWX.KH": "Power Generation",
    "EG.ELC.RNWX.ZS": "Power Generation",
    "EG.ELC.FOSL.ZS": "Power Generation",
    "EG.ELC.PETR.ZS": "Power Generation",
    "EG.ELC.NUCL.ZS": "Power Generation",
    "EG.ELC.NGAS.ZS": "Power Generation",
    "EG.ELC.HYRO.ZS": "Power Generation",
    "EG.ELC.COAL.ZS": "Power Generation",
    "EG.USE.CRNW.ZS": "Power Generation",
    "EN.GHG.N2O.TR.MT.CE.AR5": "Energy Policy",
    "EN.GHG.N2O.PI.MT.CE.AR5": "Energy Policy",
    "EN.GHG.N2O.IC.MT.CE.AR5": "Energy Policy",
    "EN.GHG.N2O.FE.MT.CE.AR5": "Energy Policy",
    "EN.GHG.N2O.BU.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CH4.TR.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CH4.PI.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CH4.IC.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CH4.FE.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CH4.BU.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CO2.TR.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CO2.PI.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CO2.IC.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CO2.FE.MT.CE.AR5": "Energy Policy",
    "EN.GHG.CO2.BU.MT.CE.AR5": "Energy Policy",
    "EG.ELC.ACCS.UR.ZS": "Energy Policy",
    "EG.ELC.ACCS.RU.ZS": "Energy Policy",
    "EG.ELC.ACCS.ZS": "Energy Policy",
}


def _unit_from_name(name: str) -> str:
    m = re.search(r"\(([^()]*)\)\s*$", name or "")
    return m.group(1).strip() if m else ""


def _fetch_african_country_codes() -> list[str]:
    for _ in range(4):
        try:
            r = requests.get(WDI_COUNTRIES_URL, timeout=30)
            r.raise_for_status()
            j = r.json()
            items = j[1] if isinstance(j, list) and len(j) > 1 else []
            codes = [
                c["id"]
                for c in items
                if c.get("region", {}).get("value") != "Aggregates"
            ]
            return codes
        except Exception:  # pragma: no cover - network error path
            time.sleep(1.5)
    return []


def _subsector_for_code(code: str) -> str:
    return SUBSECTOR_BY_CODE.get(code, "Energy Policy")


def _subsubsector(sub_sector: str) -> str:
    return "Power Generation" if sub_sector == "Power Generation" else "General"


def _get_indicator(
    session: requests.Session, countries: str, code: str, name: str
) -> list[dict]:
    url = WDI_BASE.format(
        countries=countries, indicator=code, start=START_YEAR, end=END_YEAR
    )
    for _ in range(4):
        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            arr = data[1] if isinstance(data, list) and len(data) > 1 else None
            if not arr:
                return []
            out: list[dict] = []
            for row in arr:
                y = row.get("date")
                v = row.get("value")
                if not y or str(y) not in YEAR_COLS:
                    continue
                out.append(
                    {
                        "country": row["country"]["value"],
                        "metric": name,
                        "indicator_code": code,
                        "unit": _unit_from_name(name),
                        "year": str(y),
                        "value": v,
                    }
                )
            return out
        except Exception:  # pragma: no cover - network error path
            time.sleep(1.5)
    return []


def extract_wdi_energy() -> List[Dict[str, Any]]:
    """
    Fetch World Bank WDI energy indicators for African countries
    and return one wide row per (country, indicator).
    """
    codes = _fetch_african_country_codes()
    if not codes:
        return []
    countries = ";".join(codes)
    session = requests.Session()
    session.headers.update({"User-Agent": "africa-energy-pipeline/1.0"})
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = [
            ex.submit(_get_indicator, session, countries, c, n)
            for c, n in INDICATORS.items()
        ]
        for f in as_completed(futs):
            rows.extend(f.result())
    if not rows:
        return []
    df = pd.DataFrame(rows)
    df["sector"] = "Energy"
    df["sub_sector"] = df["indicator_code"].map(_subsector_for_code)
    df["sub_sub_sector"] = df["sub_sector"].map(_subsubsector)
    for y in YEAR_COLS:
        df[y] = pd.NA
    for idx, r in df.iterrows():
        df.at[idx, r["year"]] = r["value"]
    df["source_link"] = (
        "https://databank.worldbank.org/source/world-development-indicators"
    )
    df["sources"] = "World Bank World Development Indicator"
    keep = (
        ["country", "sector", "sub_sector", "sub_sub_sector", "metric", "unit"]
        + YEAR_COLS
        + ["source_link", "sources"]
    )
    df = df[keep].drop(columns=[], errors="ignore").drop_duplicates()
    df = df.groupby(
        ["country", "sector", "sub_sector", "sub_sub_sector", "metric", "unit"],
        as_index=False,
    ).first()
    return df.to_dict(orient="records")


# --------------------------------------------------------------------------------------
# Combined entrypoint
# --------------------------------------------------------------------------------------

import logging


def main() -> List[Dict[str, Any]]:
    """
    Combined entrypoint used by main.py:
    returns all energy records from Africa Energy Portal and WDI,
    already transformed via build_records (so each record has an 'id').
    """
    all_records: List[Dict[str, Any]] = []

    # Africa Energy Portal
    logging.info("Fetching Africa Energy Portal data...")
    aep_panel_rows = extract_africa_energy_panel()
    if aep_panel_rows:
        aep_df = pd.DataFrame(aep_panel_rows)
        logging.info("Africa Energy Portal panel rows: %d", len(aep_df))
        aep_records = build_records(
            title="Africa Energy Portal",
            df=aep_df,
            default_sector="Energy",
            source_file_path="africa_energy_panel.csv",
            skip_initial_clean=True,
        )
        if aep_records:
            all_records.extend(aep_records)
    else:
        logging.warning("Africa Energy Portal panel is empty; skipping upsert.")

    # World Bank WDI Energy
    logging.info("Fetching World Bank WDI energy data...")
    wdi_panel_rows = extract_wdi_energy()
    if wdi_panel_rows:
        wdi_df = pd.DataFrame(wdi_panel_rows)
        logging.info("World Bank WDI energy panel rows: %d", len(wdi_df))
        wdi_records = build_records(
            title="World Bank Energy WDI",
            df=wdi_df,
            default_sector="Energy",
            source_file_path="worldbank_energy_panel.csv",
            skip_initial_clean=True,
        )
        if wdi_records:
            all_records.extend(wdi_records)
    else:
        logging.warning("World Bank WDI energy panel is empty; skipping upsert.")

    logging.info("Total energy records returned: %d", len(all_records))
    return all_records


if __name__ == "__main__":
    main()
