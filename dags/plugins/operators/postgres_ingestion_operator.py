"""
plugins/operators/postgres_ingestion_operator.py
-------------------------------------------------
Ingest full table or query result from PostgreSQL → MinIO Bronze.
"""

from __future__ import annotations

import logging

import pandas as pd
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.context import Context

from operators.base_ingestion_operator import BaseIngestionOperator

logger = logging.getLogger(__name__)


class PostgresIngestionOperator(BaseIngestionOperator):
    """
    Extract data from PostgreSQL into MinIO Bronze layer.

    Examples
    --------
    Full table:
        PostgresIngestionOperator(
            task_id="ingest_orders",
            postgres_conn_id="postgres_source",
            source_name="ecommerce",
            entity_name="orders",
            table="public.orders",
        )

    Custom query with incremental filter:
        PostgresIngestionOperator(
            task_id="ingest_orders_incremental",
            postgres_conn_id="postgres_source",
            source_name="ecommerce",
            entity_name="orders",
            query="SELECT * FROM orders WHERE updated_at >= '{{ ds }}'",
            incremental=True,
        )
    """

    template_fields = BaseIngestionOperator.template_fields + ("query",)

    def __init__(
        self,
        *,
        postgres_conn_id: str = "postgres_default",
        table: str | None = None,
        query: str | None = None,
        schema: str = "public",
        incremental: bool = False,
        incremental_column: str = "updated_at",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.postgres_conn_id = postgres_conn_id
        self.table = table
        self.schema = schema
        self.incremental = incremental
        self.incremental_column = incremental_column

        # Build query
        if query:
            self.query = query
        elif table:
            if incremental:
                self.query = (
                    f"SELECT * FROM {schema}.{table} "
                    f"WHERE {incremental_column} >= '{{{{ ds }}}}' "
                    f"AND {incremental_column} < '{{{{ next_ds }}}}'"
                )
            else:
                self.query = f"SELECT * FROM {schema}.{table}"
        else:
            raise ValueError("Must provide either 'table' or 'query'")

    def extract(self, context: Context) -> pd.DataFrame:
        hook = PostgresHook(postgres_conn_id=self.postgres_conn_id)
        logger.info("Running query: %s", self.query)
        df = hook.get_pandas_df(self.query)
        logger.info("Fetched %d rows from PostgreSQL", len(df))
        return df
