# product-registry

Canonical registry of Tech4Life & Beyond product IDs and lifecycle status.

## Source of truth

- **Human-readable canonical index:** `index/TOIL_Product_Index.md`
- **Canonical product records:** `records/<TOIL_ID>.md`

## Machine-readable exports

These files are generated from the canonical index and are treated as build artifacts committed to `main`:

- `exports/product_index.json` (legacy, list format)
- `exports/product_index_v1.json` (versioned export with `schema_version` + metadata)

Schema:
- `schema/product_index_v1.schema.json`

## How to update the registry

1. Add a row to `index/TOIL_Product_Index.md`
2. Create the corresponding record file in `records/<TOIL_ID>.md`
3. Run:
   - `python3 tools/build_product_index.py`
   - `python3 tools/validate_registry.py`
4. Commit the updated exports and open a PR.

CI will fail if exports are out of date or if index/records are inconsistent.
