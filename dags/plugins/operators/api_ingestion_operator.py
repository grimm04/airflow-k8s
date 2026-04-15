"""
plugins/operators/api_ingestion_operator.py
-------------------------------------------
Generic REST API → MinIO Bronze ingestion.
Supports pagination, auth headers, and response path extraction.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests
from airflow.utils.context import Context

from operators.base_ingestion_operator import BaseIngestionOperator

logger = logging.getLogger(__name__)


class APIIngestionOperator(BaseIngestionOperator):
    """
    Pull data from a REST API endpoint into MinIO Bronze.

    Supports:
    - Bearer token / API key auth
    - Cursor & page-based pagination
    - JSONPath-like response data extraction

    Examples
    --------
    Simple GET:
        APIIngestionOperator(
            task_id="ingest_github_repos",
            source_name="github",
            entity_name="repos",
            endpoint="https://api.github.com/orgs/myorg/repos",
            headers={"Authorization": "Bearer {{ var.value.github_token }}"},
            response_key="",   # root is list
        )

    Paginated:
        APIIngestionOperator(
            task_id="ingest_crm_contacts",
            source_name="crm",
            entity_name="contacts",
            endpoint="https://api.crm.com/v1/contacts",
            headers={"X-API-Key": "{{ var.value.crm_api_key }}"},
            response_key="data.items",
            pagination_type="page",       # "page" | "cursor" | None
            page_param="page",
            page_size_param="limit",
            page_size=100,
        )
    """

    template_fields = BaseIngestionOperator.template_fields + ("endpoint",)

    def __init__(
        self,
        *,
        endpoint: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        response_key: str = "",           # dot-separated path: "data.items"
        pagination_type: str | None = None,  # "page" | "cursor" | None
        page_param: str = "page",
        page_size_param: str = "per_page",
        page_size: int = 100,
        cursor_key: str = "next_cursor",   # key in response for next cursor
        cursor_param: str = "cursor",      # query param name for cursor
        max_pages: int = 1000,
        timeout: int = 30,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.endpoint = endpoint
        self.method = method
        self.headers = headers or {}
        self.params = params or {}
        self.body = body
        self.response_key = response_key
        self.pagination_type = pagination_type
        self.page_param = page_param
        self.page_size_param = page_size_param
        self.page_size = page_size
        self.cursor_key = cursor_key
        self.cursor_param = cursor_param
        self.max_pages = max_pages
        self.timeout = timeout

    def _extract_data(self, response_json: Any) -> list[dict]:
        """Navigate dot-separated key path in response JSON."""
        if not self.response_key:
            data = response_json
        else:
            data = response_json
            for key in self.response_key.split("."):
                if isinstance(data, dict):
                    data = data.get(key, [])
        return data if isinstance(data, list) else [data]

    def _fetch_page(self, params: dict) -> requests.Response:
        resp = requests.request(
            method=self.method,
            url=self.endpoint,
            headers=self.headers,
            params=params,
            json=self.body,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp

    def extract(self, context: Context) -> pd.DataFrame:
        all_records: list[dict] = []
        params = {**self.params}

        if self.pagination_type == "page":
            page = 1
            params[self.page_size_param] = self.page_size
            for _ in range(self.max_pages):
                params[self.page_param] = page
                resp = self._fetch_page(params)
                records = self._extract_data(resp.json())
                if not records:
                    break
                all_records.extend(records)
                logger.info("Page %d: fetched %d records (total %d)", page, len(records), len(all_records))
                if len(records) < self.page_size:
                    break
                page += 1

        elif self.pagination_type == "cursor":
            cursor = None
            for _ in range(self.max_pages):
                if cursor:
                    params[self.cursor_param] = cursor
                resp = self._fetch_page(params)
                payload = resp.json()
                records = self._extract_data(payload)
                if not records:
                    break
                all_records.extend(records)
                cursor = payload.get(self.cursor_key)
                if not cursor:
                    break

        else:
            # Single request
            resp = self._fetch_page(params)
            all_records = self._extract_data(resp.json())

        logger.info("Total API records fetched: %d", len(all_records))
        return pd.json_normalize(all_records) if all_records else pd.DataFrame()
