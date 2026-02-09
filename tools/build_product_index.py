#!/usr/bin/env python3
"""Build exports/product_index.json from index/TOIL_Product_Index.md."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List, Dict

HEADER_MAP = {
    "TOIL ID": "toil_id",
    "Product Name": "product_name",
    "Category": "category",
    "Lead Creator": "lead_creator",
    "Status": "status",
    "License State": "license_state",
    "Aliases (Optional)": "aliases",
    "Legacy IDs (Optional)": "legacy_ids",
}

TOIL_ID_PATTERN = re.compile(r"^T4L-TOIL-\d{3}-[A-Z0-9]+$")


def split_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator_row(cells: List[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.strip()) is not None for cell in cells)


def parse_optional_list(value: str) -> List[str]:
    parts = [part.strip() for part in value.split(",")]
    return [part for part in parts if part]


def parse_table(lines: List[str]) -> List[Dict[str, object]]:
    header_indices: Dict[str, int] | None = None
    products: List[Dict[str, object]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and "|" in line:
            cells = split_row(line)
            if set(HEADER_MAP.keys()).issubset(cells):
                header_indices = {name: cells.index(name) for name in HEADER_MAP}
                i += 1
                if i < len(lines):
                    separator_cells = split_row(lines[i]) if "|" in lines[i] else []
                    if separator_cells and is_separator_row(separator_cells):
                        i += 1
                while i < len(lines):
                    row_line = lines[i]
                    if not row_line.strip().startswith("|"):
                        break
                    row_cells = split_row(row_line)
                    if is_separator_row(row_cells):
                        i += 1
                        continue
                    product: Dict[str, object] = {}
                    for header, field in HEADER_MAP.items():
                        idx = header_indices[header]
                        value = row_cells[idx].strip() if idx < len(row_cells) else ""
                        if field in {"aliases", "legacy_ids"}:
                            if value:
                                product[field] = parse_optional_list(value)
                        else:
                            product[field] = value
                    toil_id = str(product.get("toil_id", ""))
                    if not TOIL_ID_PATTERN.match(toil_id):
                        raise ValueError(f"Invalid TOIL ID: {toil_id}")
                    products.append(product)
                    i += 1
                break
        i += 1
    if header_indices is None:
        raise ValueError("No product index table found with expected headers.")
    return products


def build_index(source: Path, output: Path) -> None:
    lines = source.read_text(encoding="utf-8").splitlines()
    products = parse_table(lines)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(products, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TOIL product index JSON export.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("index/TOIL_Product_Index.md"),
        help="Path to the TOIL product index markdown file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("exports/product_index.json"),
        help="Path to write the product index JSON export.",
    )
    args = parser.parse_args()
    build_index(args.source, args.output)


if __name__ == "__main__":
    main()
