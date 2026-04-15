from datetime import datetime, timedelta
from airflow import DAG
from custom_operator.dbt_operator import DbtCoreOperator
from airflow import settings


DBT_PROJECT_PATH = f"{settings.DAGS_FOLDER}/dbt_trino"


default_args = {
    'owner': 'lakekit',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}

with DAG(
    dag_id='dbt_pipeline',
    default_args=default_args,
    description='Run dbt seed and transformations on the Iceberg lakehouse.',
    schedule=timedelta(days=1),
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['dbt', 'lakehouse', 'iceberg'],
) as dag:
    dbt_seed_task = DbtCoreOperator(
        task_id='dbt_seed',
        dbt_project_dir=DBT_PROJECT_PATH,
        dbt_profiles_dir=DBT_PROJECT_PATH,
        dbt_command='seed',
        full_refresh=True
    )

    dbt_run_task = DbtCoreOperator(
        task_id='dbt_run',
        dbt_project_dir=DBT_PROJECT_PATH,
        dbt_profiles_dir=DBT_PROJECT_PATH,
        dbt_command='run',
    )

    dbt_seed_task >> dbt_run_task
