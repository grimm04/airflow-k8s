# dbt — Lakehouse Analytics

dbt project for transforming AdventureWorks data through Iceberg tables via Trino.

## Layers

| Layer | Schema | Models |
|-------|--------|--------|
| Landing | `landing` | Raw CSV seeds |
| Staging | `staging` | `stg_sales`, `stg_products`, `stg_territories`, `stg_product_categories`, `stg_product_subcategories` |
| Curated | `curated` | `fact_sale`, `dim_product`, `dim_country` |

## Run

```bash
dbt seed --profiles-dir . --project-dir .
dbt run --profiles-dir . --project-dir .
dbt test --profiles-dir . --project-dir .
```
