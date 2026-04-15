import subprocess
from airflow.exceptions import AirflowException
from airflow.sdk import BaseOperator
from dbt.cli.main import dbtRunner, dbtRunnerResult

class DbtCoreOperator(BaseOperator):
    def __init__(
        self,
        dbt_project_dir: str,
        dbt_profiles_dir: str,
        dbt_command: str,
        target: str = None,
        select: str = None,
        dbt_vars: dict = None,
        full_refresh: bool = False,
        dbt_log_path: str = "/tmp/dbt-logs",  
        dbt_target_path: str = "/tmp/dbt-target",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.dbt_command = dbt_command
        self.dbt_project_dir = dbt_project_dir
        self.dbt_profiles_dir = dbt_profiles_dir
        self.target = target
        self.select = select
        self.runner = dbtRunner()
        self.dbt_vars = dbt_vars or {}
        self.full_refresh = full_refresh
        self.dbt_log_path = dbt_log_path
        self.dbt_target_path = dbt_target_path

    def execute(self, context):
        command_args = [
            self.dbt_command,
            "--profiles-dir", self.dbt_profiles_dir,
            "--project-dir", self.dbt_project_dir,
        ]
        if self.target:
            command_args.extend(["--target", self.target])

        if self.select:
            command_args.extend(["--select", self.select])

        if self.full_refresh:
            command_args.append("--full-refresh")
            
        command_args.extend(["--log-path", f"{self.dbt_log_path}/{self.task_id}"])
        command_args.extend(["--target-path", f"{self.dbt_target_path}/{self.task_id}"])

        if self.dbt_vars:
            vars_string = " ".join([f"{k}: {v}" for k, v in self.dbt_vars.items()])
            command_args.extend(["--vars", f"'{vars_string}'"])

        self.log.info("Executing dbt command: %s", " ".join(command_args))

        res: dbtRunnerResult = self.runner.invoke(command_args)

        if not res.success:
            exc = getattr(res, 'exception', None)
            if exc is not None:
                raise AirflowException(f"dbt command failed with exception: {exc}") from exc
            raise AirflowException(
                f"dbt command failed: {' '.join(command_args)}\nResult: {res.result}"
            )

        self.log.info("dbt command executed successfully.")

        if res.result is not None:
            for r in res.result:
                node_name = getattr(r, 'node', None)
                node_name = node_name.name if node_name else getattr(r, 'unique_id', str(r))
                status = getattr(r, 'status', 'unknown')
                self.log.info("%s: %s", node_name, status)