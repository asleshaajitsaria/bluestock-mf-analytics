"""
data_ingestion.py
Day 1: load all provided CSVs, profile them, explore fund_master and
validate AMFI codes against nav_history.

Usage:
    python data_ingestion.py                # reads data/raw/*.csv
    python data_ingestion.py path/to/csvs   # or a different folder
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
RAW_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "raw"
REPORT_PATH = ROOT / "reports" / "data_quality_summary.md"

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)


# ----------------------------------------------------------------------------
# Step 3: load every CSV, print shape / dtypes / head, note anomalies
# ----------------------------------------------------------------------------
def load_all(raw_dir: Path) -> dict:
    files = sorted(p for p in raw_dir.glob("*.csv") if not p.name.startswith("nav_live_"))
    if not files:
        sys.exit(f"No CSV files found in {raw_dir}. Copy the 10 provided datasets there first.")

    datasets = {}
    for path in files:
        try:
            datasets[path.stem] = pd.read_csv(path)
        except UnicodeDecodeError:
            datasets[path.stem] = pd.read_csv(path, encoding="latin-1")
    print(f"Loaded {len(datasets)} dataset(s) from {raw_dir}")
    return datasets


def find_anomalies(name: str, df: pd.DataFrame) -> list:
    notes = []
    nulls = df.isna().sum()
    for col, n in nulls[nulls > 0].items():
        notes.append(f"`{col}`: {n} null(s) ({n / len(df):.1%})")

    dup_rows = int(df.duplicated().sum())
    if dup_rows:
        notes.append(f"{dup_rows} fully duplicated row(s)")

    for col in df.select_dtypes(include=[np.number]).columns:
        neg = int((df[col] < 0).sum())
        if neg:
            notes.append(f"`{col}`: {neg} negative value(s)")
        if df[col].nunique(dropna=True) <= 1 and len(df) > 1:
            notes.append(f"`{col}`: constant column")

    # Numeric-looking columns stored as text, and date-looking columns not parsed
    for col in df.select_dtypes(include="object").columns:
        sample = df[col].dropna().astype(str).head(200)
        if sample.empty:
            continue
        if pd.to_numeric(sample, errors="coerce").notna().mean() > 0.9:
            notes.append(f"`{col}`: numeric values stored as text")
        elif "date" in col.lower():
            notes.append(f"`{col}`: date column stored as text")
        stripped = df[col].dropna().astype(str)
        if (stripped != stripped.str.strip()).any():
            notes.append(f"`{col}`: leading/trailing whitespace")
    return notes


def profile(datasets: dict) -> dict:
    anomalies = {}
    for name, df in datasets.items():
        print("\n" + "=" * 80)
        print(f"DATASET: {name}")
        print("=" * 80)
        print(f"shape: {df.shape}")
        print("\ndtypes:")
        print(df.dtypes)
        print("\nhead:")
        print(df.head())
        anomalies[name] = find_anomalies(name, df)
        print("\nanomalies:")
        for note in anomalies[name] or ["none detected"]:
            print(f"  - {note}")
    return anomalies


# ----------------------------------------------------------------------------
# Helpers to locate datasets/columns without hard-coding exact names
# ----------------------------------------------------------------------------
def pick_dataset(datasets: dict, keyword: str):
    for name, df in datasets.items():
        if keyword in name.lower():
            return name, df
    return None, None


def pick_column(df: pd.DataFrame, *keywords: str):
    """First column whose lowercase name contains every keyword group (any alt)."""
    for col in df.columns:
        low = col.lower().replace(" ", "_")
        if any(k in low for k in keywords):
            return col
    return None


# ----------------------------------------------------------------------------
# Step 6: explore fund master
# ----------------------------------------------------------------------------
def explore_fund_master(fm: pd.DataFrame) -> dict:
    print("\n" + "=" * 80)
    print("FUND MASTER EXPLORATION")
    print("=" * 80)
    cols = {
        "fund_house": pick_column(fm, "fund_house", "amc", "house"),
        "category": pick_column(fm, "category") if pick_column(fm, "category") and "sub" not in pick_column(fm, "category").lower() else None,
        "sub_category": pick_column(fm, "sub_category", "subcategory", "sub_cat"),
        "risk": pick_column(fm, "risk"),
        "code": pick_column(fm, "amfi", "scheme_code", "code"),
    }
    if cols["category"] is None:
        for c in fm.columns:
            if "category" in c.lower() and "sub" not in c.lower():
                cols["category"] = c
                break

    summary = {}
    for label, col in cols.items():
        if col is None:
            print(f"\n[{label}] column not found")
            continue
        if label == "code":
            print(f"\n[{label}] column `{col}`: {fm[col].nunique()} unique, "
                  f"sample = {fm[col].dropna().astype(str).head(5).tolist()}")
            lengths = fm[col].dropna().astype(str).str.len().value_counts().to_dict()
            print(f"  code length distribution: {lengths}")
            summary[label] = col
            continue
        values = sorted(fm[col].dropna().astype(str).unique())
        print(f"\n[{label}] column `{col}`: {len(values)} unique")
        for v in values:
            print(f"  - {v}")
        summary[label] = (col, values)
    print("\nNote: an AMFI scheme code is a numeric identifier assigned to each scheme "
          "(Direct/Regular and Growth/IDCW plans each get their own code).")
    return {"cols": cols, "summary": summary}


# ----------------------------------------------------------------------------
# Step 7: validate AMFI codes and write data quality summary
# ----------------------------------------------------------------------------
def validate_amfi(fm: pd.DataFrame, nav: pd.DataFrame, fm_code: str, nav_code: str) -> dict:
    fm_codes = set(fm[fm_code].dropna().astype(str).str.strip())
    nav_codes = set(nav[nav_code].dropna().astype(str).str.strip())
    missing = sorted(fm_codes - nav_codes)
    orphan = sorted(nav_codes - fm_codes)
    print("\n" + "=" * 80)
    print("AMFI CODE VALIDATION")
    print("=" * 80)
    print(f"fund_master codes : {len(fm_codes)}")
    print(f"nav_history codes : {len(nav_codes)}")
    print(f"in fund_master but NOT in nav_history: {len(missing)} {missing[:20]}")
    print(f"in nav_history but NOT in fund_master: {len(orphan)} {orphan[:20]}")
    return {"fm": len(fm_codes), "nav": len(nav_codes), "missing": missing, "orphan": orphan}


def write_report(datasets, anomalies, validation) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Day 1 Data Quality Summary", ""]
    lines.append("## Datasets loaded")
    lines.append("")
    lines.append("| Dataset | Rows | Columns |")
    lines.append("|---|---|---|")
    for name, df in datasets.items():
        lines.append(f"| {name} | {len(df)} | {df.shape[1]} |")
    lines += ["", "## Anomalies by dataset", ""]
    for name, notes in anomalies.items():
        lines.append(f"**{name}**")
        lines += [f"- {n}" for n in notes] or ["- none detected"]
        lines.append("")
    lines.append("## AMFI code validation")
    lines.append("")
    if validation:
        lines.append(f"- fund_master unique codes: {validation['fm']}")
        lines.append(f"- nav_history unique codes: {validation['nav']}")
        lines.append(f"- fund_master codes missing from nav_history: {len(validation['missing'])} {validation['missing'][:20]}")
        lines.append(f"- nav_history codes missing from fund_master: {len(validation['orphan'])} {validation['orphan'][:20]}")
    else:
        lines.append("- Validation skipped: fund_master or nav_history (or their code columns) not found.")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nData quality summary written to {REPORT_PATH}")


def main() -> None:
    datasets = load_all(RAW_DIR)
    anomalies = profile(datasets)

    fm_name, fm = pick_dataset(datasets, "fund_master")
    nav_name, nav = pick_dataset(datasets, "nav_history")
    validation = None
    if fm is None:
        print("\nfund_master dataset not found (expected a file with 'fund_master' in its name).")
    else:
        info = explore_fund_master(fm)
        if nav is not None:
            fm_code = info["cols"]["code"]
            nav_code = pick_column(nav, "amfi", "scheme_code", "code")
            if fm_code and nav_code:
                validation = validate_amfi(fm, nav, fm_code, nav_code)
        else:
            print("\nnav_history dataset not found (expected a file with 'nav_history' in its name).")

    write_report(datasets, anomalies, validation)


if __name__ == "__main__":
    main()
