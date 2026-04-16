import requests
import pandas as pd
import time
from clean_transform import build_records
from config import YEARS
import logging

BASE_URL = (
    "https://faostatservices.fao.org/api/v1/en/data/RL?area=4%2C7%2C53%2C20%2C233%2C29%2C35%2C32%2C37%2C39%2C40%2C45%2C46%2C107%2C250%2C72%2C59%2C61%2C178%2C209%2C238%2C74%2C75%2C81%2C90%2C175%2C114%2C122%2C123%2C124%2C129%2C130%2C133%2C136"
    "%2C137%2C143%2C144%2C147%2C158%2C159%2C184%2C193%2C195%2C196%2C197%2C201%2C202%2C277%2C276%2C206%2C217%2C222%2C226%2C215%2C251%2C181&area_cs=M49"
    "element=7277%2C7208%2C7252%2C7210%2C7209%2C7278%2C5110%2C7215%2C72000%3E&"
    "item=6610%2C6649%2C6717%2C6716%2C6620%2C6655%2C6621%2C6656%2C6659%2C6650%2C6630%2C6640%2C6633%2C66710%3E%2C6602%2C66020%3E%2C6611%2C6672%2C6671%2C67620%3E%2C"
    "68000%3E%2C6773%2C6641%2C6642%2C6600%2C6694%2C6669%2C6665%2C6664%2C6668%2C6774%2C6666%2C6644%2C6645%2C6643%2C6646%2C66630%3E%2C6695%2C6680%2C6767%2C6771%2C66900%3E%2C6601%2C6616%2C6690%2C6762%2C6670%2C6657%2C6682%2C6681%2C6714%2C66800%3E"
    "&year="
    + "%2C".join(str(y) for y in YEARS)
    + "&show_codes=true&show_unit=true&show_flags=true&show_notes=true&null_values=false&page_number={page}&page_size=100&output_type=objects&caching=false"
)

(
    "https://faostatservices.fao.org/api/v1/en/data/FO?area=4%2C7%2C53%2C20%2C233%2C29%2C35%2C32%2C37%2C39%2C40%2C45%2C46%2C107%2C250%2C72%2C59%2C61%2C178%2C209%2C238%2C74%2C75%2C81%2C90%2C175%2C114%2C122%2C123%2C124%2C129%2C130%2C133%2C136"
    "%2C137%2C143%2C144%2C147%2C158%2C159%2C184%2C193%2C195%2C196%2C197%2C201%2C202%2C277%2C276%2C206%2C217%2C222%2C226%2C215%2C251%2C181&area_cs=M49"
    "element=2910%2C2920%2C2610%2C2620%2C2510&item=1653%2C1618%2C1617%2C1656%2C1663%2C1662%2C1686%2C1661%2C1660%2C1665%2C1688%2C"
    "1667%2C1649%2C1643%2C1644%2C1636%2C1647%2C1673%2C1676%2C1684%2C1651%2C1670%2C1657%2C1607%2C1685%2C1654%2C1648%2C1671%2C1606%2C1678%2C1650%2C1625%2C1623%2C1626%2C1692%2C1675%2C1683%2C1622%2C1677%2C1697%2C1646%2C1640%2C1664%2C"
    "1674%2C1616%2C1612%2C1615%2C1668%2C1608%2C1611%2C1614%2C1602%2C1603%2C1609%2C1669%2C1600%2C1605%2C1601%2C1604%2C1632%2C1633%2C1655%2C1666%2C1634%2C1694%2C1630%2C1619%2C1629%2C1627%2C1628%2C1693%2C1691%2C1620%2C1658%2C1652%2C1681%2C1621"
    "&year="
    + "%2C".join(str(y) for y in YEARS)
    + "&show_codes=true&show_unit=true&show_flags=true&show_notes=true&null_values=false&page_number={page}&page_size=100&output_type=objects&caching=false"
)

(
    "https://faostatservices.fao.org/api/v1/en/data/LC?area=4%2C7%2C53%2C20%2C233%2C29%2C35%2C32%2C37%2C39%2C40%2C45%2C46%2C107%2C250%2C72%2C59%2C61%2C178%2C209%2C238%2C74%2C75%2C81%2C90%2C175%2C114%2C122%2C123%2C124%2C129%2C130%2C133%2C136"
    "%2C137%2C143%2C144%2C147%2C158%2C159%2C184%2C193%2C195%2C196%2C197%2C201%2C202%2C277%2C276%2C206%2C217%2C222%2C226%2C215%2C251%2C181&area_cs=M49"
    "element=5008%2C5006%2C5007%2C5013&item=6970%2C6982%2C6983%2C6971%2C6981%2C6975%2C6973%2C6980%2C6976%2C6977%2C6978%2C6979%2C6974%2C6972"
    "&year="
    + "%2C".join(str(y) for y in YEARS)
    + "&show_codes=true&show_unit=true&show_flags=true&show_notes=true&null_values=false&page_number={page}&page_size=100&output_type=objects&caching=false"
)

def classify_sub_sector(element, item):
    text = f"{element} {item}".lower()
    if any(k in text for k in ["forest", "tree"]): return "Forests & Terrestrial Ecosystems"
    if any(k in text for k in ["wetland", "blue", "aquaculture", "eez", "marine", "coast"]): return "Wetlands & Blue Carbon"
    if any(k in text for k in ["protected", "conserved", "park", "reserve"]): return "Protected & Conserved Areas"
    if "degrad" in text or "soil" in text or "fallow" in text: return "Land Degradation & Soil Health"
    if any(k in text for k in ["water", "catchment", "irrigation"]): return "Water & Catchment Health"
    if any(k in text for k in ["wildlife", "livelihood", "pasture", "meadow"]): return "Wildlife Economy & Livelihoods"
    if any(k in text for k in ["governance", "policy"]): return "Environmental Governance & Policy"
    if "climate" in text: return "Nature-Based Climate Solutions"
    if "restor" in text or "land use change" in text: return "Restoration & Land Use Change"
    if any(k in text for k in ["finance", "funding"]): return "Environmental Finance"
    if any(k in text for k in ["pollution", "stress", "contaminant"]): return "Pollution & Ecosystem Stressors"
    return "Biodiversity"

def fetch_page(page, session, retries=3, backoff=5):
    url = BASE_URL.format(page=page)
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception:
            time.sleep(backoff * (2 ** attempt))
    return []

def extract_nature_faostat():
    all_rows = []
    page = 1
    session = requests.Session()
    while True:
        rows = fetch_page(page, session)
        if not rows:
            break
        all_rows.extend(rows)
        page += 1

    df = pd.DataFrame(all_rows)
    df["sector"] = "Nature"
    df["sub_sector"] = df.apply(lambda row: classify_sub_sector(row["Element"], row["Item"]), axis=1)
    df["sub_sub_sector"] = df["Element"]
    df["metric"] = df["Item"]
    df["unit"] = df["Unit"]
    df["country"] = df["Area"]
    df["year"] = pd.to_numeric(df["Year"], errors="coerce")
    df["value"] = pd.to_numeric(df["Value"], errors="coerce")
    df["source_link"] = "https://www.fao.org/faostat/en/#data/RL"
    df["sources"] = "FAO FAOSTAT"
    df["source_file"] = "fao_faostat.csv"

    df_pivot = df.pivot_table(
        index=["country", "sector", "sub_sector", "sub_sub_sector", "metric", "unit", "source_link", "sources", "source_file"],
        columns="year",
        values="value"
    ).reset_index()

    df_pivot.columns = [str(c) if isinstance(c, int) else c for c in df_pivot.columns]

    records = build_records(
        title="FAO FAOSTAT",
        df=df_pivot,
        default_sector="Nature",
        source_file_path="fao_faostat.csv",
        skip_initial_clean=True
    )

    return records
