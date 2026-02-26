#!/usr/bin/env python3
"""Sync helper: build registry artifacts from a local checkout of the `products` repo.

IMPORTANT GOVERNANCE NOTE
-------------------------
`index/TOIL_Product_Index.md` and `records/*.md` are the canonical sources of truth for this repo.

This script is intentionally *non-destructive*:
  - It generates candidate exports and a candidate markdown table for review.
  - It does NOT write into `index/TOIL_Product_Index.md`.

Typical use:
  python3 tools/build_registry_from_products.py --products ../products

Outputs:
  - exports/product_index.json                 (legacy)
  - exports/product_index_v1.json              (schema v1)
  - exports/products_candidate_index_table.md  (candidate table for reviewers)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"
RECORDS = ROOT / "records"

# Strict, anchored TOIL id pattern used across the registry.
TOIL_ID_RE = re.compile(r"\bT4L-TOIL-\d{3}(?:-[A-Z0-9]+)+\b")


@dataclass(frozen=True)
class ProductCandidate:
    toil_id: str
    product_name: str
    status: str
    license_state: str
    category: str
    lead_creator: str
    aliases: Optional[List[str]] = None
    legacy_ids: Optional[List[str]] = None


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _extract_toil_id_from_readme(readme_text: str, repo_path: Path) -> str:
    matches = TOIL_ID_RE.findall(readme_text)
    matches = list(dict.fromkeys(matches))  # stable de-dupe
    if len(matches) == 0:
        raise SystemExit(f"ERROR: No TOIL ID found in {repo_path}/README.md")
    if len(matches) > 1:
        raise SystemExit(
            f"ERROR: Multiple TOIL IDs found in {repo_path}/README.md: {', '.join(matches)}"
        )
    return matches[0]


def _split_csv(cell: str) -> Optional[List[str]]:
    parts = [p.strip() for p in (cell or "").split(",") if p.strip()]
    return parts or None


def _extract_readme_metadata(readme_text: str) -> Dict[str, str]:
    """Best-effort metadata extraction from README.md.

    Conservative rules:
    - We only extract when we find explicit key/value patterns.
    - We do not invent values.
    - Placeholders like TBD/N/A/Unknown are ignored.

    Supported keys (case-insensitive):
      - product_name, status, license_state, category, lead_creator, aliases, legacy_ids

    Supported line styles:
      - **Product Name:** Clean Drain Device
      - Product Name: Clean Drain Device
      - - Product Name: Clean Drain Device
    """
    key_map = {
        "product name": "product_name",
        "product_name": "product_name",
        "status": "status",
        "license state": "license_state",
        "license_state": "license_state",
        "category": "category",
        "lead creator": "lead_creator",
        "lead_creator": "lead_creator",
        "aliases": "aliases",
        "legacy ids": "legacy_ids",
        "legacy_ids": "legacy_ids",
    }

    meta: Dict[str, str] = {}

    line_re = re.compile(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?(?P<key>[A-Za-z _]+?)(?:\*\*)?\s*:\s*(?P<val>.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    for m in line_re.finditer(readme_text):
        raw_key = (m.group("key") or "").strip().lower()
        raw_val = (m.group("val") or "").strip()
        if not raw_key or not raw_val:
            continue

        norm_key = key_map.get(raw_key)
        if not norm_key:
            continue

        if norm_key in meta:
            continue

        if raw_val.lower() in {"tbd", "n/a", "na", "none", "unknown", "-"}:
            continue

        meta[norm_key] = raw_val

    return meta


def _load_pack_metadata(repo_path: Path) -> Dict[str, str]:
    """Best-effort metadata extraction.

    Priority:
      1) metadata.json (if present and valid)
      2) README.md key/value fields (fills missing keys)

    Conservative: missing fields remain missing.
    """
    meta: Dict[str, str] = {}

    md = repo_path / "metadata.json"
    if md.exists():
        try:
            meta_json = json.loads(_read_text(md))

            for k in (
                "product_name",
                "status",
                "license_state",
                "category",
                "lead_creator",
            ):
                v = meta_json.get(k)
                if isinstance(v, str) and v.strip():
                    meta[k] = v.strip()

            aliases = meta_json.get("aliases")
            if isinstance(aliases, list) and all(
                isinstance(v, str) and v.strip() for v in aliases
            ):
                meta["aliases"] = ",".join(v.strip() for v in aliases)

            legacy_ids = meta_json.get("legacy_ids")
            if isinstance(legacy_ids, list) and all(
                isinstance(v, str) and v.strip() for v in legacy_ids
            ):
                meta["legacy_ids"] = ",".join(v.strip() for v in legacy_ids)

        except Exception:
            # non-fatal; continue with README-based extraction
            pass

    readme = repo_path / "README.md"
    if readme.exists():
        readme_meta = _extract_readme_metadata(_read_text(readme))
        for k, v in readme_meta.items():
            if k not in meta and isinstance(v, str) and v.strip():
                meta[k] = v.strip()

    return meta


def _candidate_from_pack(pack_path: Path) -> ProductCandidate:
    readme = pack_path / "README.md"
    if not readme.exists():
        raise SystemExit(f"ERROR: Missing README.md in product pack: {pack_path}")

    readme_text = _read_text(readme)
    toil_id = _extract_toil_id_from_readme(readme_text, pack_path)
    meta = _load_pack_metadata(pack_path)

    # Conservative defaults (only used if metadata is missing)
    product_name = meta.get("product_name") or pack_path.name
    status = meta.get("status") or "Active"
    license_state = meta.get("license_state") or "Open for Licensing"
    category = meta.get("category") or "Uncategorized"
    lead_creator = meta.get("lead_creator") or "Unknown"

    return ProductCandidate(
        toil_id=toil_id,
        product_name=product_name,
        status=status,
        license_state=license_state,
        category=category,
        lead_creator=lead_creator,
        aliases=_split_csv(meta.get("aliases", "")),
        legacy_ids=_split_csv(meta.get("legacy_ids", "")),
    )


def _discover_product_packs(products_root: Path) -> List[Path]:
    packs: List[Path] = []
    for p in sorted(products_root.iterdir()):
        if p.is_dir() and (p / "README.md").exists():
            packs.append(p)
    return packs


def _ensure_records_exist(candidates: List[ProductCandidate]) -> None:
    missing = []
    for c in candidates:
        rec = RECORDS / f"{c.toil_id}.md"
        if not rec.exists():
            missing.append(c.toil_id)
    if missing:
        raise SystemExit(
            "ERROR: Missing registry records for TOIL IDs: "
            + ", ".join(missing)
            + ". Create records/<TOIL_ID>.md before syncing exports."
        )


def _check_duplicate_toil_ids(candidates: List[ProductCandidate]) -> None:
    seen: Dict[str, int] = {}
    dups: List[str] = []
    for c in candidates:
        seen[c.toil_id] = seen.get(c.toil_id, 0) + 1
    for k, v in seen.items():
        if v > 1:
            dups.append(k)
    if dups:
        raise SystemExit(
            f"ERROR: Duplicate TOIL IDs detected in products packs: {', '.join(dups)}"
        )


def _write_exports(candidates: List[ProductCandidate]) -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)

    legacy_items: List[Dict[str, object]] = []
    for c in sorted(candidates, key=lambda x: x.toil_id):
        item: Dict[str, object] = {
            "toil_id": c.toil_id,
            "product_name": c.product_name,
            "category": c.category,
            "lead_creator": c.lead_creator,
            "status": c.status,
            "license_state": c.license_state,
        }
        if c.aliases:
            item["aliases"] = c.aliases
        if c.legacy_ids:
            item["legacy_ids"] = c.legacy_ids
        legacy_items.append(item)

    (EXPORTS / "product_index.json").write_text(
        json.dumps(legacy_items, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    v1 = {
        "schema_version": "1.0.0",
        "products": legacy_items,
    }
    (EXPORTS / "product_index_v1.json").write_text(
        json.dumps(v1, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_candidate_table(candidates: List[ProductCandidate]) -> None:
    out = EXPORTS / "products_candidate_index_table.md"
    lines: List[str] = []
    lines.append("# Candidate Product Index Table (from products repo)")
    lines.append("")
    lines.append(
        "This file is generated for review. It must be manually reconciled with index/TOIL_Product_Index.md."
    )
    lines.append("")
    lines.append(
        "| TOIL ID | Product Name | Category | Lead Creator | Status | License State | Aliases (Optional) | Legacy IDs (Optional) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in sorted(candidates, key=lambda x: x.toil_id):
        lines.append(
            "| "
            + " | ".join(
                [
                    c.toil_id,
                    c.product_name,
                    c.category,
                    c.lead_creator,
                    c.status,
                    c.license_state,
                    ", ".join(c.aliases or []),
                    ", ".join(c.legacy_ids or []),
                ]
            )
            + " |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--products",
        required=True,
        help="Path to a local checkout of tech4life-beyond/products",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if generated exports would differ from committed exports.",
    )
    args = ap.parse_args(argv)

    products_root = Path(args.products).resolve()
    if not products_root.exists() or not products_root.is_dir():
        raise SystemExit(
            f"ERROR: --products path does not exist or is not a directory: {products_root}"
        )

    packs = _discover_product_packs(products_root)
    if not packs:
        raise SystemExit(f"ERROR: No product packs found under: {products_root}")

    candidates = [_candidate_from_pack(p) for p in packs]
    _check_duplicate_toil_ids(candidates)
    _ensure_records_exist(candidates)

    if args.check:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tmp_root = Path(td)
            global EXPORTS
            EXPORTS = tmp_root / "exports"
            _write_exports(candidates)
            _write_candidate_table(candidates)

            diffs = []
            for rel in [
                "exports/product_index.json",
                "exports/product_index_v1.json",
                "exports/products_candidate_index_table.md",
            ]:
                a = ROOT / rel
                b = tmp_root / rel
                if not a.exists():
                    diffs.append(rel)
                    continue
                if a.read_bytes() != b.read_bytes():
                    diffs.append(rel)
            if diffs:
                print("ERROR: Generated artifacts differ from committed files:")
                for d in diffs:
                    print(f"- {d}")
                return 4
            print("OK: Products sync artifacts are up to date.")
            return 0

    _write_exports(candidates)
    _write_candidate_table(candidates)
    print(
        "Wrote exports/product_index.json, exports/product_index_v1.json, exports/products_candidate_index_table.md"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
