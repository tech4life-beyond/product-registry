from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_products_sync_generates_schema_compatible_exports(tmp_path: Path) -> None:
    products = tmp_path / "products"
    pack = products / "clean-drain-device"
    pack.mkdir(parents=True)
    (pack / "README.md").write_text(
        "# Clean Drain Device\n\nID: T4L-TOIL-001-CDD\n", encoding="utf-8"
    )
    (pack / "metadata.json").write_text(
        json.dumps(
            {
                "product_name": "Clean Drain Device",
                "category": "HVAC Hardware",
                "lead_creator": "Ariel Martin",
                "status": "Active",
                "license_state": "Open for Licensing",
                "aliases": ["DrainClean T Adapter"],
                "legacy_ids": ["T4L-2025-001"],
            }
        ),
        encoding="utf-8",
    )

    before_legacy = (ROOT / "exports/product_index.json").read_text(encoding="utf-8")
    before_v1 = (ROOT / "exports/product_index_v1.json").read_text(encoding="utf-8")

    try:
        p = subprocess.run(
            [
                "python3",
                "tools/build_registry_from_products.py",
                "--products",
                str(products),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        assert p.returncode == 0, p.stderr

        v1 = json.loads(
            (ROOT / "exports/product_index_v1.json").read_text(encoding="utf-8")
        )
        assert v1["schema_version"] == "1.0.0"
        assert "generated_at" not in v1

        product = v1["products"][0]
        assert "category" in product
        assert "lead_creator" in product
        assert "primary_owner" not in product
    finally:
        (ROOT / "exports/product_index.json").write_text(
            before_legacy, encoding="utf-8"
        )
        (ROOT / "exports/product_index_v1.json").write_text(before_v1, encoding="utf-8")
