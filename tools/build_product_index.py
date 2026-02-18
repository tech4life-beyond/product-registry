#!/usr/bin/env python3
"""Build machine-readable product index exports from the canonical Markdown index.

Source of truth:
- index/TOIL_Product_Index.md

Outputs (committed build artifacts):
- exports/product_index.json            (legacy: list[product])
- exports/product_index_v1.json         (versioned: {schema_version, products})
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
INDEX_MD = ROOT / "index" / "TOIL_Product_Index.md"
RECORDS_DIR = ROOT / "records"
EXPORTS_DIR = ROOT / "exports"

LEGACY_EXPORT = EXPORTS_DIR / "product_index.json"
V1_EXPORT = EXPORTS_DIR / "product_index_v1.json"

TOIL_ID_RE = re.compile(r"^T4L-TOIL-\d{3}(?:-[A-Z0-9]+)+$")


def _split_list(cell: str) -> List[str]:
    cell = (cell or "").strip()
    if not cell or cell == "-":
        return []
    return [c.strip() for c in cell.split(",") if c.strip()]


def _parse_markdown_table(md_text: str) -> List[Dict[str, str]]:
    """Parse the *single* canonical product index table.

    Enforcement:
    - Exactly one index table must exist in index/TOIL_Product_Index.md.
    - The table is identified by a header row containing "TOIL ID".
    """
    lines = md_text.splitlines()

    def is_separator(line: str) -> bool:
        s = line.replace("|", "").strip()
        return bool(s) and set(s) <= set("-: ")

    header_idxs = []
    for i, line in enumerate(lines):
        if re.search(r"\|\s*TOIL ID\s*\|", line):
            # must be followed by a separator row
            if i + 1 < len(lines) and is_separator(lines[i + 1]):
                header_idxs.append(i)

    if not header_idxs:
        raise SystemExit(
            f"ERROR: Could not find product index table header in {INDEX_MD.as_posix()}"
        )
    if len(header_idxs) > 1:
        locs = ", ".join(str(i + 1) for i in header_idxs)
        raise SystemExit(
            "ERROR: Multiple product index tables detected in index/TOIL_Product_Index.md "
            f"(headers at lines: {locs}). Keep exactly one canonical table."
        )

    header_idx = header_idxs[0]
    header = [c.strip() for c in lines[header_idx].strip().strip("|").split("|")]

    required_cols = [
        "TOIL ID",
        "Product Name",
        "Category",
        "Lead Creator",
        "Status",
        "License State",
    ]
    for c in required_cols:
        if c not in header:
            raise SystemExit(
                f"ERROR: Missing required column {c!r} in {INDEX_MD.as_posix()}"
            )

    # Rows start after the separator line.
    rows: List[Dict[str, str]] = []
    i = header_idx + 2
    while i < len(lines) and lines[i].strip().startswith("|"):
        parts = [p.strip() for p in lines[i].strip().strip("|").split("|")]
        if len(parts) != len(header):
            raise SystemExit(
                f"ERROR: Malformed row (wrong column count) at line {i + 1} in {INDEX_MD.as_posix()}"
            )
        rows.append(dict(zip(header, parts)))
        i += 1

    if not rows:
        raise SystemExit(
            "ERROR: Index table has zero rows; registry must contain at least one product record."
        )

    return rows


def _normalize_product(row: Dict[str, str]) -> Dict[str, object]:
    toil_id = row["TOIL ID"].strip()
    if not TOIL_ID_RE.match(toil_id):
        raise SystemExit(f"ERROR: Invalid TOIL ID format: {toil_id}")

    record_path = RECORDS_DIR / f"{toil_id}.md"
    if not record_path.exists():
        raise SystemExit(
            f"ERROR: Missing record file for {toil_id}: {record_path.relative_to(ROOT).as_posix()}"
        )

    item: Dict[str, object] = {
        "toil_id": toil_id,
        "product_name": row["Product Name"].strip(),
        "category": row["Category"].strip(),
        "lead_creator": row["Lead Creator"].strip(),
        "status": row["Status"].strip(),
        "license_state": row["License State"].strip(),
    }

    # Optional columns may be present as legacy names or as "(Optional)" variants.
    aliases = _split_list(row.get("Aliases (Optional)", "") or row.get("Aliases", ""))
    if aliases:
        item["aliases"] = aliases

    legacy_ids = _split_list(
        row.get("Legacy IDs (Optional)", "") or row.get("Legacy IDs", "")
    )
    if legacy_ids:
        item["legacy_ids"] = legacy_ids

    return item


def _write_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_exports() -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    md_text = INDEX_MD.read_text(encoding="utf-8")
    rows = _parse_markdown_table(md_text)

    products: List[Dict[str, object]] = []
    seen_ids = set()
    for row in rows:
        p = _normalize_product(row)
        if p["toil_id"] in seen_ids:
            raise SystemExit(f"ERROR: Duplicate TOIL ID in index table: {p['toil_id']}")
        seen_ids.add(p["toil_id"])
        products.append(p)

    v1 = {
        "schema_version": "1.0.0",
        "products": products,
    }
    return products, v1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check", action="store_true", help="Fail if exports are not up-to-date"
    )
    args = ap.parse_args()

    products, v1 = build_exports()

    expected_legacy = json.dumps(products, indent=2, sort_keys=True) + "\n"
    expected_v1 = json.dumps(v1, indent=2, sort_keys=True) + "\n"

    if args.check:
        legacy_cur = (
            LEGACY_EXPORT.read_text(encoding="utf-8") if LEGACY_EXPORT.exists() else ""
        )
        v1_cur = V1_EXPORT.read_text(encoding="utf-8") if V1_EXPORT.exists() else ""

        mismatches = []
        if legacy_cur != expected_legacy:
            mismatches.append(LEGACY_EXPORT.relative_to(ROOT).as_posix())
        if v1_cur != expected_v1:
            mismatches.append(V1_EXPORT.relative_to(ROOT).as_posix())

        if mismatches:
            print(
                "ERROR: Exports are out of date. Run tools/build_product_index.py and commit the results."
            )
            for m in mismatches:
                print(f" - {m}")
            raise SystemExit(4)

        print("OK: Exports are up to date.")
        return

    _write_json(LEGACY_EXPORT, products)
    _write_json(V1_EXPORT, v1)
    print(
        f"Wrote {LEGACY_EXPORT.relative_to(ROOT).as_posix()} and {V1_EXPORT.relative_to(ROOT).as_posix()}"
    )


if __name__ == "__main__":
    main()
