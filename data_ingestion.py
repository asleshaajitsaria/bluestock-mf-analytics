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
    for col in df.select_dtypes(include=["object", "string"]).columns:
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


# ----------------------------------------------------------------------------
# Deeper checks: cross-file consistency, duplicates, gaps, outliers
# ----------------------------------------------------------------------------
def deep_checks(datasets: dict) -> list:
    """Return a list of human-readable findings beyond per-column profiling."""
    out = []
    fm = datasets.get("fund_master")
    fm_codes = set(fm["amfi_code"].astype(str)) if fm is not None and "amfi_code" in fm else set()

    # 1. Byte-identical / identical-content datasets
    names = list(datasets)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if datasets[a].shape == datasets[b].shape and datasets[a].equals(datasets[b]):
                out.append(f"`{a}` and `{b}` have identical content (duplicate file).")

    # 2. AMFI codes in other datasets that are not in fund_master
    if fm_codes:
        for name, df in datasets.items():
            if name == "fund_master" or "amfi_code" not in df.columns:
                continue
            codes = set(df["amfi_code"].astype(str))
            extra, missing = sorted(codes - fm_codes), sorted(fm_codes - codes)
            if extra:
                out.append(f"`{name}`: {len(extra)} amfi_code(s) not in fund_master {extra[:10]}")
            if missing:
                out.append(f"`{name}`: covers only {len(codes)}/{len(fm_codes)} fund_master codes "
                           f"({len(missing)} missing, e.g. {missing[:8]})")

    # 3. nav_history: duplicates, date gaps, extreme daily moves, non-positive NAV
    nav = datasets.get("nav_history")
    if nav is not None:
        n = nav.copy()
        n["date"] = pd.to_datetime(n["date"], errors="coerce")
        d = int(n.duplicated(["amfi_code", "date"]).sum())
        if d:
            out.append(f"`nav_history`: {d} duplicate (amfi_code, date) rows")
        if n["date"].isna().any():
            out.append(f"`nav_history`: {int(n['date'].isna().sum())} unparseable dates")
        if (n["nav"] <= 0).any():
            out.append(f"`nav_history`: {int((n['nav'] <= 0).sum())} non-positive NAV values")
        n = n.sort_values(["amfi_code", "date"])
        n["ret"] = n.groupby("amfi_code")["nav"].pct_change()
        big = n[n["ret"].abs() > 0.10]
        if len(big):
            out.append(f"`nav_history`: {len(big)} daily NAV move(s) larger than 10% "
                       f"(e.g. code {big.iloc[0]['amfi_code']} on {big.iloc[0]['date'].date()})")
        n["gap"] = n.groupby("amfi_code")["date"].diff().dt.days
        gaps = n[n["gap"] > 5]
        if len(gaps):
            out.append(f"`nav_history`: {len(gaps)} gap(s) longer than 5 days between NAV dates")
        per = n.groupby("amfi_code").size()
        out.append(f"`nav_history`: {n['date'].min().date()} to {n['date'].max().date()}, "
                   f"rows per scheme min={per.min()} max={per.max()}")

    # 4. benchmark_indices coverage
    bi = datasets.get("benchmark_indices")
    if bi is not None:
        out.append(f"`benchmark_indices`: indices = {sorted(bi['index_name'].unique())}")
        out.append(f"`benchmark_indices`: {int(bi.duplicated(['date', 'index_name']).sum())} duplicate (date, index) rows")

    # 5. portfolio_holdings: weights per fund should be close to 100
    ph = datasets.get("portfolio_holdings")
    if ph is not None:
        w = ph.groupby("amfi_code")["weight_pct"].sum()
        off = w[(w < 95) | (w > 105)]
        out.append(f"`portfolio_holdings`: weight_pct per fund sums to {w.min():.1f}%-{w.max():.1f}%; "
                   f"{len(off)} of {len(w)} funds are outside 95-105%")
        px = ph.groupby("stock_symbol")["current_price_inr"].agg(["min", "max"])
        wide = px[px["max"] / px["min"] > 2]
        if len(wide):
            out.append(f"`portfolio_holdings`: current_price_inr for the same stock differs >2x across funds "
                       f"for {len(wide)} of {len(px)} stocks (price not consistent per stock)")
        covered = ph["amfi_code"].nunique()
        out.append(f"`portfolio_holdings`: covers {covered} schemes only")

    # 6. monthly_sip_flows: outliers, repeats, level shifts
    sip = datasets.get("monthly_sip_flows")
    if sip is not None:
        rep = sip[sip["sip_inflow_crore"].diff() == 0]
        if len(rep):
            out.append(f"`monthly_sip_flows`: sip_inflow_crore repeats the previous month in {len(rep)} month(s): "
                       f"{rep['month'].tolist()}")
        col = "new_sip_accounts_lakh"
        q1, q3 = sip[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        o = sip[(sip[col] > q3 + 3 * iqr) | (sip[col] < q1 - 3 * iqr)]
        if len(o):
            out.append(f"`monthly_sip_flows`: outlier in `{col}`: {o[['month', col]].values.tolist()}")
        jump = sip["sip_aum_lakh_crore"].pct_change()
        j = sip[jump > 0.15]
        if len(j):
            out.append(f"`monthly_sip_flows`: sip_aum_lakh_crore jumps >15% in one month at {j['month'].tolist()}")
        drop = sip[sip["active_sip_accounts_crore"].diff() < 0]
        if len(drop):
            out.append(f"`monthly_sip_flows`: active_sip_accounts_crore falls month-on-month at {drop['month'].tolist()}")

    # 7. category_inflows / folio count / AUM coverage
    ci = datasets.get("category_inflows")
    if ci is not None:
        out.append(f"`category_inflows`: months {ci['month'].min()} to {ci['month'].max()} "
                   f"({ci['month'].nunique()} months, {ci['category'].nunique()} categories)")
    fo = datasets.get("industry_folio_count")
    if fo is not None:
        m = pd.PeriodIndex(fo["month"], freq="M")
        full = pd.period_range(m.min(), m.max(), freq="M")
        out.append(f"`industry_folio_count`: {len(fo)} rows but {len(full)} months in range "
                   f"(irregular, non-monthly spacing)")
    au = datasets.get("aum_by_fund_house")
    if au is not None:
        out.append(f"`aum_by_fund_house`: {au['date'].nunique()} snapshot dates, irregular spacing "
                   f"(e.g. gap from 2025-03-31 to 2025-12-31)")
        bad = au[(au["aum_lakh_crore"] * 100000 - au["aum_crore"]).abs() > 1]
        out.append(f"`aum_by_fund_house`: {len(bad)} rows where aum_crore != aum_lakh_crore x 100000")

    # 8. investor_transactions
    tx = datasets.get("investor_transactions")
    if tx is not None:
        out.append(f"`investor_transactions`: types = {tx['transaction_type'].value_counts().to_dict()}")
        out.append(f"`investor_transactions`: kyc_status = {tx['kyc_status'].value_counts().to_dict()}")
        out.append(f"`investor_transactions`: {int(tx.duplicated().sum())} duplicate rows; "
                   f"amount_inr min={tx['amount_inr'].min()} max={tx['amount_inr'].max()}")
        sip_amt = tx[tx["transaction_type"] == "SIP"]["amount_inr"]
        if len(sip_amt):
            out.append(f"`investor_transactions`: SIP amount median={sip_amt.median():.0f}, max={sip_amt.max()}")
        inc = tx["annual_income_lakh"]
        out.append(f"`investor_transactions`: annual_income_lakh range {inc.min()} to {inc.max()}")
        out.append(f"`investor_transactions`: dates {tx['transaction_date'].min()} to {tx['transaction_date'].max()}")

    # 9. fund_master vs scheme_performance consistency
    sp = datasets.get("scheme_performance")
    if fm is not None and sp is not None:
        m = fm.merge(sp, on="amfi_code", suffixes=("_fm", "_sp"))
        er = int((m["expense_ratio_pct_fm"] - m["expense_ratio_pct_sp"]).abs().gt(0.001).sum())
        rk = int((m["risk_category"] != m["risk_grade"]).sum())
        out.append(f"fund_master vs scheme_performance: {len(m)} matched schemes; "
                   f"{er} expense_ratio mismatches; {rk} risk grade mismatches")
        liq = sp[sp["sharpe_ratio"] > 3]
        if len(liq):
            out.append(f"`scheme_performance`: implausible sharpe_ratio > 3 for {liq['scheme_name'].tolist()} "
                       f"(sharpe equals return_3yr in these rows)")
    if fm is not None and "sub_category" in fm:
        subs = set(fm["sub_category"])
        if {"Index", "Index/ETF"} <= subs:
            out.append("`fund_master`: sub_category uses both `Index` and `Index/ETF` (inconsistent labels)")
    return out


def write_report(datasets, anomalies, validation, deep=None) -> None:
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
    if deep:
        lines += ["", "## Additional checks (cross-file consistency, gaps, outliers)", ""]
        lines += [f"- {d}" for d in deep]
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

    deep = deep_checks(datasets)
    print("\n" + "=" * 80)
    print("ADDITIONAL CHECKS")
    print("=" * 80)
    for d in deep:
        print(f"  - {d}")

    write_report(datasets, anomalies, validation, deep)


if __name__ == "__main__":
    main()
