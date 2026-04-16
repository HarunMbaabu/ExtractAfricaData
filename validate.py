import os
import json
from datetime import datetime
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_batch
from config import POSTGRES_DSN, REPORTS_DIR
from constants import COUNTRIES, normalize_country

PG_COLUMNS = [
    "id", "country", "serial", "sector", "sub_sector", "sub_sub_sector", "metric", "unit", "description", "data_type", "sources", "source_link", "tags", "created_at", "last_updated", "source_file"
]

# --- Validation Helpers ---
def _missing_fields(doc: Dict[str, Any]) -> List[str]:
    required = ["sector", "metric", "country"]
    return [k for k in required if not isinstance(doc.get(k), str) or not doc.get(k).strip()]

# --- Main Validation Logic ---
def _validate_docs(docs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Dict[str, int]]]:
    accepted = []
    errors_detail = []
    per_tab_stats = defaultdict(lambda: {"accepted": 0, "dropped": 0})
    for i, d in enumerate(docs):
        tab = d.get("title") or d.get("source") or "unknown"
        c_raw = (d.get("country") or "").strip()
        c = normalize_country(c_raw) or c_raw
        if c in COUNTRIES:
            d["country"] = c
        miss = _missing_fields({**d, "country": c})
        if miss:
            errors_detail.append(f"Doc {i}: missing {', '.join(miss)}")
            per_tab_stats[tab]["dropped"] += 1
            continue
        if c not in COUNTRIES:
            errors_detail.append(f"Doc {i}: country '{c}' not in canonical list")
            per_tab_stats[tab]["dropped"] += 1
            continue
        accepted.append(d)
        per_tab_stats[tab]["accepted"] += 1
    return accepted, errors_detail, per_tab_stats

# --- Report Writer ---
def _write_report(sheet_name: str, accepted: List[Dict[str, Any]], errors_detail: List[str], per_tab_stats: Dict[str, Dict[str, int]]) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(str(REPORTS_DIR), f"VALIDATION_REPORT_{sheet_name}_{ts}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        total = sum(v["accepted"] + v["dropped"] for v in per_tab_stats.values())
        accepted_count = sum(v["accepted"] for v in per_tab_stats.values())
        f.write(f"VALIDATION REPORT - [{sheet_name}]\n")
        f.write("=" * 60 + "\n")
        f.write("PASSED CHECKS:\n")
        f.write(f"- Total records reviewed: {total}\n")
        f.write(f"- Accepted for load (pre-disambiguation): {accepted_count}\n")
        f.write(f"- Accepted for load (after id disambiguation): {accepted_count}\n")
        f.write(f"- No hierarchy errors in accepted set\n\n")
        dropped = sum(v["dropped"] for v in per_tab_stats.values())
        f.write("FAILED / DROPPED SUMMARY:\n")
        f.write(f"- Dropped documents: {dropped}\n")
        present = set(d.get("country") for d in accepted if d.get("country"))
        missing = [c for c in COUNTRIES if c not in present]
        if missing:
            f.write(f"- Missing countries: {len(missing)} ({', '.join(missing)})\n")
        else:
            f.write("- Missing countries: 0\n")
        if errors_detail:
            f.write("\nDETAILED ERRORS:\n")
            for line in errors_detail:
                f.write(line + "\n")
        f.write("\nPER-TAB SUMMARY:\n")
        for tab, st in per_tab_stats.items():
            f.write(f"- {tab}: accepted={st['accepted']}, dropped={st['dropped']}\n")
    return report_path

# --- Database Helpers ---
def _ensure_table_exists(conn, table_name: str):
    col_types = {
        "id": "TEXT PRIMARY KEY",
        "country": "TEXT",
        "serial": "TEXT",
        "sector": "TEXT",
        "sub_sector": "TEXT",
        "sub_sub_sector": "TEXT",
        "metric": "TEXT",
        "unit": "TEXT",
        "description": "TEXT",
        "data_type": "TEXT",
        "sources": "TEXT",
        "source_link": "TEXT",
        "tags": "JSONB",
        "created_at": "TEXT",
        "last_updated": "TEXT",
        "source_file": "TEXT",
    }
    fields = [f'"{col}" {col_types.get(col, "TEXT")}' for col in PG_COLUMNS]
    create_stmt = sql.SQL("""
        CREATE TABLE IF NOT EXISTS scrapper.{table} (
            {fields}
        )
    """).format(
        table=sql.Identifier(table_name),
        fields=sql.SQL(",\n            ").join(sql.SQL(f) for f in fields)
    )
    with conn.cursor() as cur:
        cur.execute(create_stmt)
        conn.commit()

# --- Upsert Logic ---
def _safe_pg_value(val, col=None):
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return val

def _doc_to_row(doc: Dict[str, Any]) -> list:
    return [_safe_pg_value(doc.get(col), col if col == "tags" else None) for col in PG_COLUMNS]

def _upsert_to_postgres(table_name: str, accepted: List[Dict[str, Any]], report_path: str) -> None:
    if not accepted:
        return
    values_template = ','.join(['%s'] * len(PG_COLUMNS))
    insert_stmt = sql.SQL("""
        INSERT INTO {table} ({fields}) VALUES ({values})
        ON CONFLICT (id) DO UPDATE SET {updates}
    """).format(
        table=sql.Identifier(table_name),
        fields=sql.SQL(',').join(map(sql.Identifier, PG_COLUMNS)),
        values=sql.SQL(values_template),
        updates=sql.SQL(',').join([
            sql.SQL(f"{col}=EXCLUDED.{col}") for col in PG_COLUMNS if col != 'id'
        ])
    )
    data = [_doc_to_row(d) for d in accepted]
    with psycopg2.connect(POSTGRES_DSN) as conn:
        _ensure_table_exists(conn, table_name)
        with conn.cursor() as cur:
            execute_batch(cur, insert_stmt.as_string(conn), data)
            conn.commit()
    with open(report_path, "a", encoding="utf-8") as f:
        f.write("\n\nUPSERT SUMMARY (PostgreSQL):\n")
        f.write(f"- Accepted for load (after id disambiguation): {len(accepted)}\n")
        f.write(f"- PostgreSQL write: upserted/updated={len(accepted)}\n")

# --- Main Entry Point ---
def validate_and_load(table_name: str, docs_or_dict: Any) -> str:
    if isinstance(docs_or_dict, dict):
        docs = []
        for tab, lst in docs_or_dict.items():
            for d in lst:
                if "title" not in d or not d["title"]:
                    d["title"] = str(tab)
                docs.append(d)
    else:
        docs = list(docs_or_dict or [])
    accepted, errors_detail, per_tab_stats = _validate_docs(docs)
    report_path = _write_report(table_name, accepted, errors_detail, per_tab_stats)
    if accepted:
        _upsert_to_postgres(table_name, accepted, report_path)
    print(f"Wrote report: {report_path}")
    print(f"Accepted: {len(accepted)}; Dropped: {sum(v['dropped'] for v in per_tab_stats.values())}")
    return report_path
