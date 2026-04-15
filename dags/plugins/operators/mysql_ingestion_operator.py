"""
plugins/operators/mysql_ingestion_operator.py
---------------------------------------------
Ingest from MySQL → MinIO Bronze.
"""

from __future__ import annotations

import logging

import pandas as pd
from airflow.providers.mysql.hooks.mysql import MySqlHook
from airflow.utils.context import Context

from operators.base_ingestion_operator import BaseIngestionOperator

logger = logging.getLogger(__name__)


class MySQLIngestionOperator(BaseIngestionOperator):
    """
    Extract data from MySQL into MinIO Bronze layer.

    Examples
    --------
        MySQLIngestionOperator(
            task_id="ingest_products",
            mysql_conn_id="mysql_source",
            source_name="inventory",
            entity_name="products",
            table="products",
        )
    """

    template_fields = BaseIngestionOperator.template_fields + ("query",)

    def __init__(
        self,
        *,
        mysql_conn_id: str = "mysql_default",
        table: str | None = None,
        query: str | None = None,
        database: str | None = None,
        incremental: bool = False,
        incremental_column: str = "updated_at",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.mysql_conn_id = mysql_conn_id
        self.database = database
        self.incremental = incremental
        self.incremental_column = incremental_column

        if query:
            self.query = query
        elif table:
            tbl = f"{database}.{table}" if database else table
            if incremental:
                self.query = (
                    f"SELECT * FROM {tbl} "
                    f"WHERE {incremental_column} >= '{{{{ ds }}}}' "
                    f"AND {incremental_column} < '{{{{ next_ds }}}}'"
                )
            else:
                self.query = f"SELECT * FROM {tbl}"
        else:
            raise ValueError("Must provide either 'table' or 'query'")

    def extract(self, context: Context) -> pd.DataFrame:
        hook = MySqlHook(mysql_conn_id=self.mysql_conn_id)
        logger.info("Running MySQL query: %s", self.query)
        conn = hook.get_conn()
        df = pd.read_sql(self.query, conn)
        logger.info("Fetched %d rows from MySQL", len(df))
        return df
