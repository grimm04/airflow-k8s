"""
plugins/operators/base_ingestion_operator.py
--------------------------------------------
Abstract base class for all ingestion operators.
Extend this for each source type (Postgres, MySQL, API, etc.)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import pandas as pd
from airflow.models import BaseOperator
from airflow.utils.context import Context

from hooks.minio_hook import MinIOHook

logger = logging.getLogger(__name__)


class BaseIngestionOperator(BaseOperator, ABC):
    """
    Abstract base ingestion operator.

    Subclasses must implement:
        extract(context) → pd.DataFrame

    Optional overrides:
        validate(df) → pd.DataFrame   (add your DQ rules)
        transform_bronze(df) → pd.DataFrame
    """

    template_fields = ("bucket", "source_name", "entity_name")

    def __init__(
        self,
        *,
        source_name: str,
        entity_name: str,
        bucket: str = "bronze",
        minio_conn_id: str = "minio_default",
        output_format: str = "parquet",   # "parquet" | "json"
        chunk_size: int | None = None,    # for large datasets
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.source_name = source_name
        self.entity_name = entity_name
        self.bucket = bucket
        self.minio_conn_id = minio_conn_id
        self.output_format = output_format
        self.chunk_size = chunk_size

    # ----------------------------------------------------------
    # Abstract — subclass must implement
    # ----------------------------------------------------------

    @abstractmethod
    def extract(self, context: Context) -> pd.DataFrame:
        """Pull data from source. Return a DataFrame."""
        ...

    # ----------------------------------------------------------
    # Optional hooks
    # ----------------------------------------------------------

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Override to add data quality checks before upload."""
        if df.empty:
            raise ValueError(f"[{self.entity_name}] Extracted DataFrame is empty!")
        logger.info("[%s] Validated %d rows", self.entity_name, len(df))
        return df

    def transform_bronze(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Light Bronze-layer transforms:
        - add _ingested_at timestamp
        - add _source metadata
        Override to add source-specific casting.
        """
        df["_ingested_at"] = datetime.utcnow().isoformat()
        df["_source"] = self.source_name
        df["_entity"] = self.entity_name
        return df

    # ----------------------------------------------------------
    # Execute
    # ----------------------------------------------------------

    def execute(self, context: Context) -> str:
        logical_date: datetime = context["logical_date"]
        hook = MinIOHook(minio_conn_id=self.minio_conn_id)

        logger.info("Starting ingestion: source=%s entity=%s date=%s",
                    self.source_name, self.entity_name, logical_date.date())

        # 1. Extract
        df = self.extract(context)

        # 2. Validate
        df = self.validate(df)

        # 3. Bronze transforms
        df = self.transform_bronze(df)

        # 4. Build key & upload
        key = MinIOHook.bronze_key(
            source=self.source_name,
            entity=self.entity_name,
            logical_date=logical_date,
            fmt=self.output_format,
        )

        if self.output_format == "parquet":
            path = hook.upload_dataframe_as_parquet(df, bucket=self.bucket, key=key)
        else:
            path = hook.upload_dataframe_as_json(df, bucket=self.bucket, key=key)

        logger.info("Ingestion complete → %s (%d rows)", path, len(df))

        # Push to XCom for downstream tasks
        context["ti"].xcom_push(key="output_path", value=path)
        context["ti"].xcom_push(key="row_count", value=len(df))

        return path
