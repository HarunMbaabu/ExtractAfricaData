import pandas as pd
import requests
import io
from config import YEARS
from constants import normalize_country
from clean_transform import build_records

CSV_URL = (
    "https://api.data.apps.fao.org/api/v2/bigquery?sql_url=https://data.apps.fao.org/catalog/dataset/"
    "945666e6-7803-4621-b8ef-cfd885a84596/resource/4a000a1b-24f0-4328-aab6-b9b525892090/"
    "download/query_en.sql&area=Africa&type=all&variable=4016&year=2015,2016,2017,2018,2019,2020,2021,2022"
)

def aquastat_extractor():
    response = requests.get(CSV_URL)
    df_raw = pd.read_csv(io.StringIO(response.content.decode("utf-8")))

    required = ["Country", "Variable", "Unit", "VariableGroup", "Subgroup", "Year", "Value"]
    missing = [col for col in required if col not in df_raw.columns]
    if missing:
        raise ValueError(f"AQUASTAT CSV missing columns: {missing}")

    df_raw["Country"] = df_raw["Country"].map(normalize_country)

    df_pivot = df_raw.pivot_table(
        index=["Country", "Variable", "Unit", "VariableGroup", "Subgroup"],
        columns="Year",
        values="Value",
        aggfunc="first"
    ).reset_index()

    df_pivot.columns = [str(c) if isinstance(c, int) else c for c in df_pivot.columns]

    df_pivot["sector"] = "Climate - Sustainable Agric,Landuse, Water & Oceans"
    df_pivot["sub_sector"] = df_pivot["VariableGroup"].fillna("Water Resources")
    df_pivot["sub_sub_sector"] = df_pivot["Subgroup"].fillna("Aquastat Indicators")
    df_pivot["metric"] = df_pivot["Variable"]
    df_pivot["unit"] = df_pivot["Unit"]
    df_pivot["source_link"] = CSV_URL
    df_pivot["sources"] = "FAO AQUASTAT"

    for year in YEARS:
        if year not in df_pivot.columns:
            df_pivot[year] = None

    final_cols = [
        "Country", "sector", "sub_sector", "sub_sub_sector", "metric", "unit"
    ] + [str(y) for y in YEARS] + ["source_link", "sources"]

    df_pivot = df_pivot[final_cols]
    df_pivot.rename(columns={"Country": "country"}, inplace=True)

    df_pivot.to_csv("aquastat.csv", index=False)

    return build_records(
        title="FAO AQUASTAT",
        df=df_pivot,
        default_sector="Climate - Sustainable Agric,Landuse, Water & Oceans",
        source_file_path="aquastat.csv"
    )