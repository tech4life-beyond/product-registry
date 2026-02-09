#!/usr/bin/env python3
"""Build registry index artifacts from the Tech4Life products repository."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

TOIL_ID_PATTERN = re.compile(r"T4L-TOIL-\d{3}-[A-Z0-9]+")

METADATA_KEYS = {
    "product name": "product_name",
    "category": "category",
    "lead creator": "lead_creator",
    "status": "status",
    "license state": "license_state",
    "aliases": "aliases",
    "legacy ids": "legacy_ids",
}

DEFAULTS = {
    "lead_creator": "Ariel Martin",
    "status": "Active",
    "license_state": "Open for Licensing",
}


def run_git(args: List[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True)


def ensure_products_repo(explicit_path: Path | None) -> Path:
    if explicit_path is not None:
        return explicit_path

    sibling_repo = Path("..") / "products"
    if sibling_repo.exists():
        return sibling_repo

    temp_dir = Path(tempfile.mkdtemp(prefix="t4l-products-"))
    run_git([
        "clone",
        "--depth",
        "1",
        "https://github.com/tech4life-beyond/products.git",
        str(temp_dir),
    ], cwd=Path("."))
    return temp_dir


def extract_metadata(lines: List[str]) -> Dict[str, str | List[str]]:
    metadata: Dict[str, str | List[str]] = {}
    for line in lines:
        match = re.match(r"^\s*[-*]?\s*([^:]+)\s*:\s*(.+)$", line)
        if not match:
            continue
        key = match.group(1).strip().lower()
        value = match.group(2).strip()
        if key not in METADATA_KEYS:
            continue
        field = METADATA_KEYS[key]
        if field in {"aliases", "legacy_ids"}:
            items = [item.strip() for item in value.split(",")]
            metadata[field] = [item for item in items if item]
        else:
            metadata[field] = value
    return metadata


def title_case_folder(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").title()


def parse_product_pack(pack_dir: Path) -> Dict[str, object]:
    readme_path = pack_dir / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    toil_matches = TOIL_ID_PATTERN.findall(content)
    if not toil_matches:
        raise ValueError(f"No TOIL ID found in {readme_path}")
    toil_id = toil_matches[0]

    lines = content.splitlines()
    metadata = extract_metadata(lines)

    product_name = metadata.get("product_name") or title_case_folder(pack_dir.name)
    category = metadata.get("category") or ""
    lead_creator = metadata.get("lead_creator") or DEFAULTS["lead_creator"]
    status = metadata.get("status") or DEFAULTS["status"]
    license_state = metadata.get("license_state") or DEFAULTS["license_state"]

    product: Dict[str, object] = {
        "toil_id": toil_id,
        "product_name": product_name,
        "category": category,
        "lead_creator": lead_creator,
        "status": status,
        "license_state": license_state,
    }

    aliases = metadata.get("aliases")
    if aliases:
        product["aliases"] = aliases

    legacy_ids = metadata.get("legacy_ids")
    if legacy_ids:
        product["legacy_ids"] = legacy_ids

    return product


def discover_product_packs(products_repo: Path) -> List[Path]:
    packs: List[Path] = []
    for entry in sorted(products_repo.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / "README.md").exists():
            packs.append(entry)
    return packs


def write_json(products: List[Dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(products, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_markdown_table(products: List[Dict[str, object]]) -> str:
    header = (
        "| TOIL ID | Product Name | Category | Lead Creator | Status | License State | "
        "Aliases (Optional) | Legacy IDs (Optional) |"
    )
    separator = (
        "|-------|-------------|----------|--------------|--------|---------------|"
        "-------------------|-----------------------|"
    )
    rows = []
    for product in products:
        aliases = ", ".join(product.get("aliases", [])) if product.get("aliases") else ""
        legacy_ids = ", ".join(product.get("legacy_ids", [])) if product.get("legacy_ids") else ""
        rows.append(
            "| {toil_id} | {product_name} | {category} | {lead_creator} | {status} | "
            "{license_state} | {aliases} | {legacy_ids} |".format(
                toil_id=product.get("toil_id", ""),
                product_name=product.get("product_name", ""),
                category=product.get("category", ""),
                lead_creator=product.get("lead_creator", ""),
                status=product.get("status", ""),
                license_state=product.get("license_state", ""),
                aliases=aliases,
                legacy_ids=legacy_ids,
            )
        )
    return "\n".join([header, separator, *rows]) + "\n"


def write_markdown_index(products: List[Dict[str, object]], output_path: Path) -> None:
    marker = "<!-- AUTO-GENERATED: PRODUCT INDEX TABLE (DO NOT EDIT BELOW) -->"
    table = build_markdown_table(products)
    if output_path.exists():
        content = output_path.read_text(encoding="utf-8")
    else:
        content = ""

    if marker in content:
        prefix, _ = content.split(marker, 1)
        prefix = prefix.rstrip()
    else:
        prefix = content.rstrip()

    updated = prefix + ("\n\n" if prefix else "") + marker + "\n\n" + table
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(updated, encoding="utf-8")


def build_registry(products_repo: Path, json_output: Path, markdown_output: Path) -> None:
    packs = discover_product_packs(products_repo)
    products = [parse_product_pack(pack) for pack in packs]
    products.sort(key=lambda item: str(item.get("toil_id", "")))
    write_json(products, json_output)
    write_markdown_index(products, markdown_output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build registry from products repository.")
    parser.add_argument(
        "--products",
        type=Path,
        help="Path to the products repository. Defaults to ../products if present.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("exports/product_index.json"),
        help="Path to write the product index JSON export.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("index/TOIL_Product_Index.md"),
        help="Path to write the product index markdown file.",
    )
    args = parser.parse_args()

    products_repo = ensure_products_repo(args.products)
    build_registry(products_repo, args.json_output, args.markdown_output)


if __name__ == "__main__":
    main()
