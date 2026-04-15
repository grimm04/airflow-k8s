"""
plugins/hooks/minio_hook.py
---------------------------
Reusable MinIO hook extending S3Hook with
datalakehouse-specific helpers.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from typing import Any

import boto3
import pandas as pd
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from botocore.client import Config

logger = logging.getLogger(__name__)


class MinIOHook(S3Hook):
    """
    Extended S3Hook for MinIO with Bronze/Silver/Gold helpers.

    Usage in DAG:
        hook = MinIOHook(minio_conn_id="minio_default")
        hook.upload_dataframe_as_parquet(df, bucket="bronze", key="mydata/2024/01/01/data.parquet")
    """

    def __init__(self, minio_conn_id: str = "minio_default", **kwargs):
        super().__init__(aws_conn_id=minio_conn_id, **kwargs)
        self.minio_conn_id = minio_conn_id

    def get_client(self):
        """Return a raw boto3 S3 client pointed at MinIO."""
        conn = self.get_connection(self.minio_conn_id)
        extras = conn.extra_dejson
        endpoint = extras.get("endpoint_url", "http://minio:9000")
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=conn.login,
            aws_secret_access_key=conn.password,
            config=Config(signature_version="s3v4"),
            region_name=extras.get("region_name", "us-east-1"),
        )

    # ----------------------------------------------------------
    # WRITE helpers
    # ----------------------------------------------------------

    def upload_dataframe_as_parquet(
        self,
        df: pd.DataFrame,
        bucket: str,
        key: str,
        partition_cols: list[str] | None = None,
    ) -> str:
        """Upload a pandas DataFrame as Parquet to MinIO."""
        client = self.get_client()
        buffer = io.BytesIO()
        df.to_parquet(buffer, index=False, engine="pyarrow")
        buffer.seek(0)
        client.put_object(Bucket=bucket, Key=key, Body=buffer.getvalue())
        full_path = f"s3://{bucket}/{key}"
        logger.info("Uploaded parquet → %s", full_path)
        return full_path

    def upload_dataframe_as_json(
        self,
        df: pd.DataFrame,
        bucket: str,
        key: str,
    ) -> str:
        """Upload a pandas DataFrame as newline-delimited JSON."""
        client = self.get_client()
        ndjson = df.to_json(orient="records", lines=True)
        client.put_object(Bucket=bucket, Key=key, Body=ndjson.encode())
        full_path = f"s3://{bucket}/{key}"
        logger.info("Uploaded ndjson → %s", full_path)
        return full_path

    def upload_bytes(self, data: bytes, bucket: str, key: str) -> str:
        """Raw bytes upload."""
        client = self.get_client()
        client.put_object(Bucket=bucket, Key=key, Body=data)
        return f"s3://{bucket}/{key}"

    # ----------------------------------------------------------
    # READ helpers
    # ----------------------------------------------------------

    def read_parquet(self, bucket: str, key: str) -> pd.DataFrame:
        """Read a Parquet file from MinIO into a DataFrame."""
        client = self.get_client()
        obj = client.get_object(Bucket=bucket, Key=key)
        return pd.read_parquet(io.BytesIO(obj["Body"].read()))

    def read_json(self, bucket: str, key: str) -> list[dict]:
        """Read a JSON/NDJSON file from MinIO."""
        client = self.get_client()
        obj = client.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read().decode("utf-8")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return [json.loads(line) for line in content.strip().splitlines()]

    # ----------------------------------------------------------
    # KEY BUILDERS  (Bronze / Silver / Gold convention)
    # ----------------------------------------------------------

    @staticmethod
    def bronze_key(source: str, entity: str, logical_date: datetime, fmt: str = "parquet") -> str:
        """
        Generate a partitioned Bronze key.
        Pattern: {source}/{entity}/year=YYYY/month=MM/day=DD/{entity}.{fmt}
        """
        return (
            f"{source}/{entity}/"
            f"year={logical_date.year}/"
            f"month={logical_date.month:02d}/"
            f"day={logical_date.day:02d}/"
            f"{entity}.{fmt}"
        )

    @staticmethod
    def silver_key(source: str, entity: str, logical_date: datetime, fmt: str = "parquet") -> str:
        return (
            f"silver/{source}/{entity}/"
            f"year={logical_date.year}/month={logical_date.month:02d}/"
            f"day={logical_date.day:02d}/{entity}_clean.{fmt}"
        )

    @staticmethod
    def gold_key(domain: str, mart: str, logical_date: datetime, fmt: str = "parquet") -> str:
        return (
            f"gold/{domain}/{mart}/"
            f"year={logical_date.year}/month={logical_date.month:02d}/"
            f"{mart}.{fmt}"
        )

    # ----------------------------------------------------------
    # UTILITY
    # ----------------------------------------------------------

    def list_keys_by_prefix(self, bucket: str, prefix: str) -> list[str]:
        """List all object keys under a prefix."""
        client = self.get_client()
        paginator = client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def object_exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists."""
        try:
            self.get_client().head_object(Bucket=bucket, Key=key)
            return True
        except Exception:
            return False
