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

## Sync from the `products` repo (optional)

The `products` repository is an external input that may be used to *propose* updates.

- `index/TOIL_Product_Index.md` and `records/*.md` remain the canonical sources of truth.
- Sync tooling must not write a second table into `index/TOIL_Product_Index.md`.

Automation entrypoint:

- `tools/build_registry_from_products.py` generates **candidate exports** plus a review-only candidate table:
  - `exports/product_index.json`
  - `exports/product_index_v1.json`
  - `exports/products_candidate_index_table.md`

## Definition of Done for registry PRs

A PR is considered complete when all of these are true:

1. `python3 tools/build_product_index.py --check` passes
2. `python3 tools/validate_registry.py` passes
3. `exports/product_index_v1.json` validates against `schema/product_index_v1.schema.json`
4. `git diff --exit-code .` shows no uncommitted changes


