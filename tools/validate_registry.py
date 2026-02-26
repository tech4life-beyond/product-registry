#!/usr/bin/env python3
"""Validate registry integrity.

Checks:
- Canonical index table parses and is non-empty.
- Each index row has a corresponding records/<TOIL_ID>.md file.
- No duplicate TOIL IDs.
- Exports exist and are internally consistent.
- product_index_v1.json schema_version is correct.
- exports/product_index.json == exports/product_index_v1.json.products (backward compatibility).
- Exports match the canonical index for *all core fields* (and optional fields when present).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
INDEX_MD = ROOT / "index" / "TOIL_Product_Index.md"
RECORDS_DIR = ROOT / "records"
LEGACY_EXPORT = ROOT / "exports" / "product_index.json"
V1_EXPORT = ROOT / "exports" / "product_index_v1.json"

TOIL_ID_RE = re.compile(r"^T4L-TOIL-\d{3}(?:-[A-Z0-9]+)+$")


def _split_list(cell: str) -> List[str]:
    cell = (cell or "").strip()
    if not cell or cell == "-":
        return []
    return [p.strip() for p in cell.split(",") if p.strip()]


def _parse_markdown_table(md_text: str) -> List[Dict[str, str]]:
    lines = md_text.splitlines()

    def is_separator(line: str) -> bool:
        s = line.replace("|", "").strip()
        return bool(s) and set(s) <= set("-: ")

    header_idxs = []
    for i, line in enumerate(lines):
        if re.search(r"\|\s*TOIL ID\s*\|", line):
            if i + 1 < len(lines) and is_separator(lines[i + 1]):
                header_idxs.append(i)

    if not header_idxs:
        raise ValueError("Missing index table header")
    if len(header_idxs) > 1:
        locs = ", ".join(str(i + 1) for i in header_idxs)
        raise ValueError(
            "Multiple product index tables detected (headers at lines: "
            + locs
            + "). Keep exactly one canonical table in index/TOIL_Product_Index.md."
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
            raise ValueError(f"Missing required column {c!r} in index table header")

    rows: List[Dict[str, str]] = []
    i = header_idx + 2
    while i < len(lines) and lines[i].strip().startswith("|"):
        parts = [p.strip() for p in lines[i].strip().strip("|").split("|")]
        if len(parts) != len(header):
            raise ValueError(f"Malformed row at line {i + 1}")
        rows.append(dict(zip(header, parts)))
        i += 1
    return rows


def _canonical_from_index_row(r: Dict[str, str]) -> Tuple[str, Dict[str, object]]:
    tid = (r.get("TOIL ID") or "").strip()
    item: Dict[str, object] = {
        "toil_id": tid,
        "product_name": (r.get("Product Name") or "").strip(),
        "category": (r.get("Category") or "").strip(),
        "lead_creator": (r.get("Lead Creator") or "").strip(),
        "status": (r.get("Status") or "").strip(),
        "license_state": (r.get("License State") or "").strip(),
    }

    aliases = _split_list(
        (r.get("Aliases (Optional)") or r.get("Aliases") or "").strip()
    )
    if aliases:
        item["aliases"] = aliases

    legacy_ids = _split_list(
        (r.get("Legacy IDs (Optional)") or r.get("Legacy IDs") or "").strip()
    )
    if legacy_ids:
        item["legacy_ids"] = legacy_ids

    return tid, item


def main() -> None:
    errors: List[str] = []

    try:
        rows = _parse_markdown_table(INDEX_MD.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: {INDEX_MD.as_posix()}: {e}")
        sys.exit(1)

    if not rows:
        errors.append("Index table has zero rows")

    toil_ids: List[str] = []
    canonical_by_id: Dict[str, Dict[str, object]] = {}

    for r in rows:
        tid, canon = _canonical_from_index_row(r)

        if not TOIL_ID_RE.match(tid):
            errors.append(f"Invalid TOIL ID format in index: {tid!r}")

        toil_ids.append(tid)

        if tid in canonical_by_id:
            errors.append(f"Duplicate TOIL ID in index: {tid}")

        canonical_by_id[tid] = canon

        rec = RECORDS_DIR / f"{tid}.md"
        if not rec.exists():
            errors.append(f"Missing record file: {rec.relative_to(ROOT).as_posix()}")

    # Duplicate detection
    seen = set()
    for tid in toil_ids:
        if tid in seen:
            errors.append(f"Duplicate TOIL ID in index: {tid}")
        seen.add(tid)

    # Exports must exist
    if not LEGACY_EXPORT.exists():
        errors.append(f"Missing export: {LEGACY_EXPORT.relative_to(ROOT).as_posix()}")
    if not V1_EXPORT.exists():
        errors.append(f"Missing export: {V1_EXPORT.relative_to(ROOT).as_posix()}")

    legacy = None
    v1 = None
    try:
        if LEGACY_EXPORT.exists():
            legacy = json.loads(LEGACY_EXPORT.read_text(encoding="utf-8"))
            if not isinstance(legacy, list):
                errors.append("exports/product_index.json must be a JSON list")
    except Exception as e:
        errors.append(f"exports/product_index.json is invalid JSON: {e}")

    try:
        if V1_EXPORT.exists():
            v1 = json.loads(V1_EXPORT.read_text(encoding="utf-8"))
            if not isinstance(v1, dict):
                errors.append("exports/product_index_v1.json must be a JSON object")
    except Exception as e:
        errors.append(f"exports/product_index_v1.json is invalid JSON: {e}")

    if isinstance(v1, dict):
        if v1.get("schema_version") != "1.0.0":
            errors.append(
                f"product_index_v1.json schema_version must be 1.0.0 (got {v1.get('schema_version')!r})"
            )
        prods = v1.get("products")
        if not isinstance(prods, list) or not prods:
            errors.append("product_index_v1.json products must be a non-empty list")

    # Legacy export should match v1.products exactly (for backward compatibility)
    if (
        isinstance(legacy, list)
        and isinstance(v1, dict)
        and isinstance(v1.get("products"), list)
    ):
        if legacy != v1["products"]:
            errors.append(
                "Legacy export does not match v1 products list (exports drift)"
            )

    # Full parity check between canonical index and v1 exports (core + optional)
    if isinstance(v1, dict) and isinstance(v1.get("products"), list):
        products_list = v1["products"]
        exp_by_id: Dict[str, Dict[str, object]] = {}
        for p in products_list:
            if isinstance(p, dict) and isinstance(p.get("toil_id"), str):
                exp_by_id[p["toil_id"]] = p

        # Ensure every index entry exists in exports
        for tid in canonical_by_id.keys():
            if tid not in exp_by_id:
                errors.append(f"Missing product in export for TOIL ID: {tid}")

        # Ensure exports do not contain unknown TOIL IDs
        for tid in exp_by_id.keys():
            if tid not in canonical_by_id:
                errors.append(
                    f"Export contains unknown TOIL ID not present in index: {tid}"
                )

        core_fields = [
            "product_name",
            "category",
            "lead_creator",
            "status",
            "license_state",
        ]
        optional_fields = ["aliases", "legacy_ids"]

        for tid, canon in canonical_by_id.items():
            exp = exp_by_id.get(tid)
            if not exp:
                continue

            for f in core_fields:
                cval = canon.get(f)
                eval_ = exp.get(f)
                if (cval or "") != (eval_ or ""):
                    errors.append(
                        f"{f} differ for {tid}: index has {cval!r} but export has {eval_!r}"
                    )

            # Optional parity: if present in either side, they must match exactly
            for f in optional_fields:
                cval = canon.get(f)
                eval_ = exp.get(f)
                if cval is None and eval_ is None:
                    continue
                if cval is None and eval_ is not None:
                    errors.append(
                        f"{f} differ for {tid}: index has None but export has {eval_!r}"
                    )
                    continue
                if cval is not None and eval_ is None:
                    errors.append(
                        f"{f} differ for {tid}: index has {cval!r} but export has None"
                    )
                    continue
                if cval != eval_:
                    errors.append(
                        f"{f} differ for {tid}: index has {cval!r} but export has {eval_!r}"
                    )

        # Deterministic ordering: export must be sorted by toil_id
        sorted_ids = sorted(exp_by_id.keys())
        exported_ids = [
            p.get("toil_id")
            for p in products_list
            if isinstance(p, dict) and isinstance(p.get("toil_id"), str)
        ]
        if exported_ids != sorted_ids:
            errors.append(
                "Export products list is not sorted by toil_id (deterministic ordering required)"
            )

    if errors:
        print("Registry validation failed:")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)

    print("Registry validation passed.")


if __name__ == "__main__":
    main()
