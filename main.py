# main.py
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import COLLECTIONS
from validate import validate_and_load
from extractors.aquastat import aquastat_extractor
from extractors.energy_data import main as extract_aep
from extractors.nature_faostat import extract_nature_faostat
from extractors.wdi_adaptation import extract_wdi_africa
from extractors.cfcm_oecd import extract_oecd_riomarkers
from extractors.mining import main as mining_extractor
from extractors.infra_data import main as infra_data_extractor

SECTOR_RUNNERS = {
    # "energy": (energy_extractor, COLLECTIONS["energy"]),
    "energy": (extract_aep, COLLECTIONS["energy"]),
    "aquastat": (aquastat_extractor, COLLECTIONS["agriculture"]),
    "nature": (extract_nature_faostat, COLLECTIONS["nature"]),
    "adaptation": (extract_wdi_africa, COLLECTIONS["adaptation"]),
    "cfcm": (extract_oecd_riomarkers, COLLECTIONS["cfcm"]),
    "mining": (mining_extractor, COLLECTIONS["mining"]),
    "infrastructure": (infra_data_extractor, COLLECTIONS["infrastructure"]),
}


def run_sector(sector_key: str):
    extractor, collection = SECTOR_RUNNERS[sector_key]
    docs_by_tab = extractor()
    validate_and_load(collection, docs_by_tab)
    return sector_key

def run_all(workers: int | None = None):
    keys = list(SECTOR_RUNNERS.keys())
    max_workers = min(len(keys), workers if workers and workers > 0 else 4)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(run_sector, k): k for k in keys}
        for f in as_completed(futs):
            f.result()

def main():
    parser = argparse.ArgumentParser(description="Multi-sector ingestion pipeline")
    sub = parser.add_subparsers(dest="cmd")
    p1 = sub.add_parser("run-sector")
    p1.add_argument("--sector", required=True, choices=list(SECTOR_RUNNERS.keys()))
    p2 = sub.add_parser("run-all")
    p2.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    if args.cmd == "run-sector":
        run_sector(args.sector)
    elif args.cmd == "run-all":
        run_all(args.workers)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()