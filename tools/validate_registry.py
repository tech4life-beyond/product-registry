#!/usr/bin/env python3
"""Validate registry integrity.

Checks:
- Canonical index table parses and is non-empty.
- Each index row has a corresponding records/<TOIL_ID>.md file.
- No duplicate TOIL IDs.
- Exports exist and are internally consistent.
- product_index_v1.json schema_version is correct.
- exports/product_index.json == exports/product_index_v1.json.products (backward compatibility).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
INDEX_MD = ROOT / "index" / "TOIL_Product_Index.md"
RECORDS_DIR = ROOT / "records"
LEGACY_EXPORT = ROOT / "exports" / "product_index.json"
V1_EXPORT = ROOT / "exports" / "product_index_v1.json"

TOIL_ID_RE = re.compile(r"^T4L-TOIL-\d{3}(?:-[A-Z0-9]+)+$")


def _parse_markdown_table(md_text: str) -> List[Dict[str, str]]:
    lines = md_text.splitlines()
    header_idxs = [i for i, line in enumerate(lines) if re.search(r"\|\s*TOIL ID\s*\|", line)]
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
    rows: List[Dict[str, str]] = []
    i = header_idx + 2
    while i < len(lines) and lines[i].strip().startswith("|"):
        parts = [p.strip() for p in lines[i].strip().strip("|").split("|")]
        if len(parts) != len(header):
            raise ValueError(f"Malformed row at line {i + 1}")
        rows.append(dict(zip(header, parts)))
        i += 1
    return rows


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
    for r in rows:
        tid = (r.get("TOIL ID") or "").strip()
        if not TOIL_ID_RE.match(tid):
            errors.append(f"Invalid TOIL ID format in index: {tid!r}")
        toil_ids.append(tid)

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

    # Optional fields in the index must not be silently dropped in exports.
    def _split_list(cell: str) -> List[str]:
        return [p.strip() for p in cell.split(",") if p.strip()]

    if isinstance(v1, dict) and isinstance(v1.get("products"), list):
        exp_by_id = {
            p.get("toil_id"): p
            for p in v1["products"]
            if isinstance(p, dict) and isinstance(p.get("toil_id"), str)
        }
        for r in rows:
            tid = (r.get("TOIL ID") or "").strip()
            exp = exp_by_id.get(tid)
            if not exp:
                continue
            aliases_cell = (r.get("Aliases (Optional)") or r.get("Aliases") or "").strip()
            legacy_cell = (r.get("Legacy IDs (Optional)") or r.get("Legacy IDs") or "").strip()
            aliases = _split_list(aliases_cell)
            legacy_ids = _split_list(legacy_cell)

            if aliases and exp.get("aliases") != aliases:
                errors.append(
                    f"aliases differ for {tid}: index has {aliases!r} but export has {exp.get('aliases')!r}"
                )
            if legacy_ids and exp.get("legacy_ids") != legacy_ids:
                errors.append(
                    f"legacy_ids differ for {tid}: index has {legacy_ids!r} but export has {exp.get('legacy_ids')!r}"
                )

    if errors:
        print("Registry validation failed:")
        for e in errors:
            print(f"- {e}")
        sys.exit(1)

    print("Registry validation passed.")


if __name__ == "__main__":
    main()
