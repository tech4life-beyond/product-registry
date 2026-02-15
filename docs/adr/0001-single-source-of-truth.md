# ADR-0001: Single Source of Truth for the Product Registry

Date: 2026-02-15

## Status

Accepted

## Context

The product-registry repository needs a deterministic, auditable source of truth for:

- Product identity (TOIL IDs)
- Product metadata (name, status, license state, owner)
- Registry records that support licensing and governance

Previously, the repo had drift risk because a sync script could write an additional auto-generated index table into `index/TOIL_Product_Index.md`, creating two competing sources.

## Decision

**Canonical sources (inside this repo):**

1. `index/TOIL_Product_Index.md` (one and only one index table)
2. `records/*.md` (one record per TOIL ID)

**External sources:**

- The `products` repository is treated as an **external synchronization input**.
- Sync automation may generate **candidate artifacts** for review, but must not rewrite canonical documents.

## Consequences

- `tools/build_product_index.py` parses exactly one index table. Multiple tables are a hard error.
- Sync automation (`tools/build_registry_from_products.py`) generates:
  - `exports/product_index.json`
  - `exports/product_index_v1.json`
  - `exports/products_candidate_index_table.md` (review-only)
  and does **not** modify `index/TOIL_Product_Index.md`.
- CI enforces:
  - exports are up to date (`--check`)
  - registry integrity validation passes
  - schema validation passes
  - no uncommitted diffs
