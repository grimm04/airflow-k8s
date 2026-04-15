"""
plugins/operators/dbt_operator.py
----------------------------------
Reusable dbt operator for Airflow 3.1.
Runs dbt commands (run, test, snapshot, seed) as subprocesses.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Literal

from airflow.models import BaseOperator
from airflow.utils.context import Context

logger = logging.getLogger(__name__)

DbtCommand = Literal["run", "test", "snapshot", "seed", "compile", "docs generate"]


class DbtOperator(BaseOperator):
    """
    Execute dbt commands within an Airflow task.

    Examples
    --------
    Run all silver models:
        DbtOperator(
            task_id="dbt_run_silver",
            command="run",
            select="tag:silver",
        )

    Run + test specific model:
        DbtOperator(task_id="dbt_run_orders", command="run", select="orders")
        DbtOperator(task_id="dbt_test_orders", command="test", select="orders")

    Full refresh:
        DbtOperator(task_id="dbt_full_refresh", command="run", full_refresh=True)
    """

    template_fields = ("select", "exclude", "vars")

    def __init__(
        self,
        *,
        command: DbtCommand = "run",
        select: str | None = None,
        exclude: str | None = None,
        full_refresh: bool = False,
        vars: dict | None = None,             # dbt --vars
        target: str | None = None,            # dbt --target
        profiles_dir: str = "/opt/airflow/dbt",
        project_dir: str = "/opt/airflow/dbt",
        dbt_bin: str = "dbt",
        env_vars: dict[str, str] | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.command = command
        self.select = select
        self.exclude = exclude
        self.full_refresh = full_refresh
        self.vars = vars
        self.target = target
        self.profiles_dir = profiles_dir
        self.project_dir = project_dir
        self.dbt_bin = dbt_bin
        self.env_vars = env_vars or {}

    def execute(self, context: Context) -> str:
        cmd = [self.dbt_bin, self.command]

        if self.select:
            cmd += ["--select", self.select]
        if self.exclude:
            cmd += ["--exclude", self.exclude]
        if self.full_refresh:
            cmd.append("--full-refresh")
        if self.vars:
            import json
            cmd += ["--vars", json.dumps(self.vars)]
        if self.target:
            cmd += ["--target", self.target]

        cmd += ["--profiles-dir", self.profiles_dir]
        cmd += ["--project-dir", self.project_dir]

        env = {**os.environ, **self.env_vars}

        logger.info("Running dbt: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
        )

        if result.stdout:
            logger.info("dbt stdout:\n%s", result.stdout)
        if result.stderr:
            logger.warning("dbt stderr:\n%s", result.stderr)

        if result.returncode != 0:
            raise RuntimeError(
                f"dbt {self.command} failed with return code {result.returncode}\n"
                f"stderr: {result.stderr}"
            )

        logger.info("dbt %s completed successfully", self.command)
        return result.stdout
