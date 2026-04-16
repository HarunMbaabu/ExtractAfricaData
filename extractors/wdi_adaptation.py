import requests, pandas as pd, re
from tqdm import tqdm
from clean_transform import build_records
from datetime import datetime

# ---- 1) Classification dictionaries ----
SUBSECTOR_BY_CODE = {
    # Governance effectiveness
    "GE.PER.RNK": "Policy Framework & Planning",
    "GE.PER.RNK.LOWER": "Policy Framework & Planning",
    "GE.PER.RNK.UPPER": "Policy Framework & Planning",
    "GE.STD.ERR": "Policy Framework & Planning",
    # Education expenditure
    "SE.XPD.TOTL.GD.ZS": "Capacity Building & Social Cohesion",
    "SE.XPD.TOTL.GB.ZS": "Capacity Building & Social Cohesion",
    "SE.XPD.PRIM.PC.ZS": "Capacity Building & Social Cohesion",
    "SE.XPD.SECO.PC.ZS": "Capacity Building & Social Cohesion",
    "SE.XPD.TERT.PC.ZS": "Capacity Building & Social Cohesion",
    # Debt/borrowing & deflators
    "NE.DAB.TOTL.ZS": "Public Finance & Investment",
    "NE.DAB.TOTL.KD": "Public Finance & Investment",
    "NE.DAB.TOTL.KN": "Public Finance & Investment",
    "NE.DAB.TOTL.CN": "Public Finance & Investment",
    "NE.DAB.TOTL.CD": "Public Finance & Investment",
    "NE.DAB.DEFL.ZS": "Public Finance & Investment",
    # Private consumption & welfare
    "NE.CON.PRVT.ZS": "Public Finance & Investment",
    "NE.CON.PRVT.KD.ZG": "Public Finance & Investment",
    "NE.CON.PRVT.KD": "Public Finance & Investment",
    "NE.CON.PRVT.KN": "Public Finance & Investment",
    "NE.CON.PRVT.CN": "Public Finance & Investment",
    "NE.CON.PRVT.CD": "Public Finance & Investment",
    "NE.CON.PRVT.PC.KD": "Public Finance & Investment",
    "NE.CON.PRVT.PC.KD.ZG": "Public Finance & Investment",
    "NE.CON.PRVT.PP.KD": "Public Finance & Investment",
    "NE.CON.PRVT.PP.CD": "Public Finance & Investment",
    "NE.CON.PRVT.CN.AD": "Public Finance & Investment",
    # Interest / transactions
    "ST.INT.XPND.MP.ZS": "Public Finance & Investment",
    "ST.INT.XPND.CD": "Public Finance & Investment",
    "ST.INT.TRNX.CD": "Public Finance & Investment",
    "ST.INT.TVLX.CD": "Public Finance & Investment",
    # Military spending
    "MS.MIL.XPND.ZS": "Public Finance & Investment",
    "MS.MIL.XPND.GD.ZS": "Public Finance & Investment",
    "MS.MIL.XPND.CN": "Public Finance & Investment",
    "MS.MIL.XPND.CD": "Public Finance & Investment",
    # ODA
    "DT.ODA.ODAT.XP.ZS": "Public Finance & Investment",
    # Health OOP & UHC
    "SH.XPD.OOPC.CH.ZS": "Social Protection & Inclusion",
    "SH.XPD.OOPC.PC.CD": "Social Protection & Inclusion",
    "SH.XPD.OOPC.PP.CD": "Social Protection & Inclusion",
    "GF.XPD.BUDG.ZS": "Public Finance & Investment",
    "SH.UHC.NOP1.ZS": "Social Protection & Inclusion",
    "SH.UHC.NOP2.ZS": "Social Protection & Inclusion",
    "SH.UHC.NOPR.ZS": "Social Protection & Inclusion",
    "SH.UHC.FBP1.ZS": "Social Protection & Inclusion",
    "SH.UHC.FBP2.ZS": "Social Protection & Inclusion",
    "SH.UHC.FBPR.ZS": "Social Protection & Inclusion",
    "SH.UHC.TOT1.ZS": "Social Protection & Inclusion",
    "SH.UHC.TOT2.ZS": "Social Protection & Inclusion",
    "SH.UHC.TOTR.ZS": "Social Protection & Inclusion",
    "SH.UHC.OOPC.10.ZS": "Social Protection & Inclusion",
    "SH.UHC.OOPC.25.ZS": "Social Protection & Inclusion",
}

SUBSUBSECTOR_BY_CODE = {
    # Governance effectiveness granularity
    "GE.PER.RNK": "Governance Effectiveness",
    "GE.PER.RNK.LOWER": "Governance Effectiveness",
    "GE.PER.RNK.UPPER": "Governance Effectiveness",
    "GE.STD.ERR": "Governance Effectiveness",
    # Education
    "SE.XPD.TOTL.GD.ZS": "Education Expenditure",
    "SE.XPD.TOTL.GB.ZS": "Education Expenditure",
    "SE.XPD.PRIM.PC.ZS": "Education Expenditure",
    "SE.XPD.SECO.PC.ZS": "Education Expenditure",
    "SE.XPD.TERT.PC.ZS": "Education Expenditure",
    # Debt/borrowing
    "NE.DAB.TOTL.ZS": "Debt & Borrowing",
    "NE.DAB.TOTL.KD": "Debt & Borrowing",
    "NE.DAB.TOTL.KN": "Debt & Borrowing",
    "NE.DAB.TOTL.CN": "Debt & Borrowing",
    "NE.DAB.TOTL.CD": "Debt & Borrowing",
    "NE.DAB.DEFL.ZS": "Debt & Borrowing",
    # Household consumption
    "NE.CON.PRVT.ZS": "Household Consumption",
    "NE.CON.PRVT.KD.ZG": "Household Consumption",
    "NE.CON.PRVT.KD": "Household Consumption",
    "NE.CON.PRVT.KN": "Household Consumption",
    "NE.CON.PRVT.CN": "Household Consumption",
    "NE.CON.PRVT.CD": "Household Consumption",
    "NE.CON.PRVT.PC.KD": "Household Consumption",
    "NE.CON.PRVT.PC.KD.ZG": "Household Consumption",
    "NE.CON.PRVT.PP.KD": "Household Consumption",
    "NE.CON.PRVT.PP.CD": "Household Consumption",
    "NE.CON.PRVT.CN.AD": "Household Consumption",
    # Interest / transactions
    "ST.INT.XPND.MP.ZS": "Debt Service Burden",
    "ST.INT.XPND.CD": "Debt Service Burden",
    "ST.INT.TRNX.CD": "Public Finance Operations",
    "ST.INT.TVLX.CD": "Public Finance Operations",
    # Military
    "MS.MIL.XPND.ZS": "Budget Composition",
    "MS.MIL.XPND.GD.ZS": "Budget Composition",
    "MS.MIL.XPND.CN": "Budget Composition",
    "MS.MIL.XPND.CD": "Budget Composition",
    # ODA
    "DT.ODA.ODAT.XP.ZS": "Official Development Assistance",
    # Health
    "SH.XPD.OOPC.CH.ZS": "Health Financial Protection",
    "SH.XPD.OOPC.PC.CD": "Health Financial Protection",
    "SH.XPD.OOPC.PP.CD": "Health Financial Protection",
    "GF.XPD.BUDG.ZS": "Public Expenditure Share",
    "SH.UHC.NOP1.ZS": "Service Coverage (UHC)",
    "SH.UHC.NOP2.ZS": "Service Coverage (UHC)",
    "SH.UHC.NOPR.ZS": "Service Coverage (UHC)",
    "SH.UHC.FBP1.ZS": "Financial Protection (UHC)",
    "SH.UHC.FBP2.ZS": "Financial Protection (UHC)",
    "SH.UHC.FBPR.ZS": "Financial Protection (UHC)",
    "SH.UHC.TOT1.ZS": "UHC Composite",
    "SH.UHC.TOT2.ZS": "UHC Composite",
    "SH.UHC.TOTR.ZS": "UHC Composite",
    "SH.UHC.OOPC.10.ZS": "Catastrophic Health Spending",
    "SH.UHC.OOPC.25.ZS": "Catastrophic Health Spending",
}

INDICATORS = list(SUBSECTOR_BY_CODE.keys())
SECTOR = "Adaptation & Resilience"

# ---- 2) Metric + Unit extraction ----
def extract_metric_and_unit(indicator_name: str):
    if not indicator_name:
        return "", ""
    if ":" in indicator_name:
        metric, unit = indicator_name.split(":", 1)
        return metric.strip(), unit.strip()
    match = re.search(r"\((.*?)\)", indicator_name)
    if match:
        unit = match.group(1).strip()
        metric = indicator_name.replace(f"({unit})", "").strip()
        return metric, unit
    return indicator_name.strip(), ""

# ---- Country filtering ----
def fetch_all_countries():
    url = "https://api.worldbank.org/v2/country?format=json&per_page=400"
    data = requests.get(url).json()[1]
    return data

def african_iso3_list():
    countries = fetch_all_countries()
    iso3 = []
    for c in countries:
        if c.get("region", {}).get("id") == "SSF":
            iso3.append(c["id"])
    north_africa = {"DZA", "EGY", "LBY", "MAR", "TUN", "SDN"}
    for c in countries:
        if c["id"] in north_africa:
            iso3.append(c["id"])
    return sorted({c for c in iso3})

# ---- Indicator fetch ----
def fetch_indicator_for_countries(iso3_list, indicator, date=None):
    rows = []
    chunk = 50
    for i in range(0, len(iso3_list), chunk):
        countries = ";".join(iso3_list[i:i+chunk])
        url = f"https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}?format=json&per_page=20000"
        if date:
            url += f"&date={date}"
        try:
            payload = requests.get(url).json()
        except Exception:
            continue
        if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
            continue
        for item in payload[1]:
            if not item or not item.get("countryiso3code"):
                continue
            rows.append({
                "iso3": item.get("countryiso3code"),
                "country": (item.get("country") or {}).get("value"),
                "indicator": (item.get("indicator") or {}).get("id"),
                "indicator_name": (item.get("indicator") or {}).get("value"),
                "year": item.get("date"),
                "value": item.get("value")
            })
    return rows

# ---- Main extractor ----
def extract_wdi_africa():
    all_rows = []
    iso3 = african_iso3_list()
    START_YEAR = 2015
    CURRENT_YEAR = datetime.now().year
    DATE_RANGE = f"{START_YEAR}:{CURRENT_YEAR}"

    for ind in tqdm(INDICATORS, desc="Fetching WDI indicators"):
        all_rows.extend(fetch_indicator_for_countries(iso3, ind, date=DATE_RANGE))

    df = pd.DataFrame(all_rows)
    df["sector"] = "Adaptation & Resilience"
    df["sub_sector"] = df["indicator"].map(SUBSECTOR_BY_CODE)
    df["sub_sub_sector"] = df["indicator"].map(SUBSUBSECTOR_BY_CODE)
    df[["metric", "unit"]] = df["indicator_name"].apply(lambda x: pd.Series(extract_metric_and_unit(x)))
    df["source_link"] = "https://databank.worldbank.org/source/world-development-indicators"
    df["sources"] = "World Bank WDI"
    df["source_file"] = "wdi_africa.csv"

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    df_pivot = df.pivot_table(
        index=["country", "sector", "sub_sector", "sub_sub_sector", "metric", "unit", "source_link", "sources", "source_file"],
        columns="year",
        values="value"
    ).reset_index()

    df_pivot.columns = [str(c) if isinstance(c, int) else c for c in df_pivot.columns]

    return build_records(
        title="World Bank WDI",
        df=df_pivot,
        default_sector="Adaptation & Resilience",
        source_file_path="wdi_africa.csv",
        skip_initial_clean=True
    )
