"""
PostgreSQL → MinIO (Raw) → dbt (Silver/Gold)

Full ELT pipeline with dbt transformations.
Configuration: ingestion/ecommerce_postgres.yml

Pipeline:
1. Extract from PostgreSQL (192.168.201.136) → MinIO raw/ecommerce
2. Transform with dbt:
   - Silver layer (staging models)
   - Gold layer (analytics models)
"""

from datetime import datetime, timedelta
import io
import yaml
import psycopg2
import pandas as pd
import boto3

from airflow import DAG
from airflow.utils.task_group import TaskGroup

try:
    from airflow.operators.python import PythonOperator
    from airflow.operators.bash import BashOperator
except ModuleNotFoundError:
    from airflow.operators.python_operator import PythonOperator
    from airflow.operators.bash_operator import BashOperator

# Load ingestion config
CONFIG_FILE = "/opt/airflow/dags/ingestion/ecommerce_postgres.yml"
with open(CONFIG_FILE, "r") as f:
    CONFIG = yaml.safe_load(f)


def extract_table_to_minio(table_name: str, schema: str = "public"):
    """Extract PostgreSQL table to Parquet and upload to MinIO"""
    source = CONFIG["source"]
    bronze = CONFIG["bronze"]
    
    try:
        conn = psycopg2.connect(
            host=source["host"],
            port=source["port"],
            user=source["user"],
            password=source["password"],
            database=source["database"],
        )
        
        query = f"SELECT * FROM {schema}.{table_name};"
        df = pd.read_sql(query, conn)
        conn.close()
        
        row_count = len(df)
        col_count = len(df.columns)
        
        parquet_buffer = io.BytesIO()
        df.to_parquet(
            parquet_buffer,
            index=False,
            compression=bronze.get("compression", "snappy")
        )
        parquet_buffer.seek(0)
        
        s3_client = boto3.client(
            "s3",
            endpoint_url=bronze["endpoint"],
            aws_access_key_id=bronze["access_key"],
            aws_secret_access_key=bronze["secret_key"],
        )
        
        s3_key = f"{bronze['namespace']}/{table_name}.parquet"
        s3_client.put_object(
            Bucket=bronze["bucket"],
            Key=s3_key,
            Body=parquet_buffer.getvalue(),
            ContentType="application/octet-stream",
        )
        
        s3_path = f"s3://{bronze['bucket']}/{s3_key}"
        print(f"✅ Extracted {table_name}: {row_count} rows × {col_count} columns → {s3_path}")
        print(f"   Size: {len(parquet_buffer.getvalue()) / 1024 / 1024:.2f} MB")
        
        return {
            "table": table_name,
            "rows": row_count,
            "columns": col_count,
            "minio_path": s3_path,
        }
        
    except Exception as e:
        print(f"❌ Error extracting {table_name}: {e}")
        raise


def extract_all_tables():
    """Extract all configured PostgreSQL tables to MinIO"""
    source = CONFIG["source"]
    bronze = CONFIG["bronze"]
    
    print("\n" + "="*70)
    print("🚀 PostgreSQL → MinIO Extraction Pipeline")
    print("="*70)
    print(f"Source DB: {source['database']} @ {source['host']}:{source['port']}")
    print(f"Target: MinIO {bronze['bucket']}/{bronze['namespace']}")
    print(f"Endpoint: {bronze['endpoint']}")
    print(f"Tables: {len(source['tables'])}")
    print("="*70 + "\n")
    
    results = []
    for table_config in source["tables"]:
        table_name = table_config["name"]
        schema = table_config.get("schema", "public")
        result = extract_table_to_minio(table_name, schema)
        results.append(result)
    
    print("\n" + "="*70)
    print(f"✅ Extraction Complete! {len(results)} tables → MinIO")
    print("="*70)
    
    return results


# ================================================================
# DAG Definition
# ================================================================
default_args = {
    "owner": CONFIG["pipeline"].get("owner", "airflow"),
    "retries": CONFIG["pipeline"].get("retries", 1),
    "retry_delay": timedelta(minutes=CONFIG["pipeline"].get("retry_delay_minutes", 5)),
}

with DAG(
    dag_id="postgres_to_minio_dbt",
    description="PostgreSQL → MinIO (raw) → dbt (silver/gold)",
    schedule=CONFIG["pipeline"]["schedule"],
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["postgres", "minio", "dbt"],
    max_active_runs=CONFIG["pipeline"]["max_active_runs"],
) as dag:

    # Task 1: Extract PostgreSQL to MinIO (Raw)
    extract_task = PythonOperator(
        task_id="extract_postgresql_to_minio",
        python_callable=extract_all_tables,
        doc="Extract all PostgreSQL tables to MinIO raw/ecommerce namespace",
    )

    # Task 2: dbt Silver transformations
    with TaskGroup("dbt_silver_transforms") as silver_group:
        dbt_silver_run = BashOperator(
            task_id="dbt_run_silver",
            bash_command=(
                "cd /opt/airflow/dbt && "
                "dbt run --select tag:silver --profiles-dir /opt/airflow/dbt"
            ),
            doc="Run dbt silver layer models (cleaned/typed data)",
        )
        
        dbt_silver_test = BashOperator(
            task_id="dbt_test_silver",
            bash_command=(
                "cd /opt/airflow/dbt && "
                "dbt test --select tag:silver --profiles-dir /opt/airflow/dbt"
            ),
            doc="Test dbt silver layer models",
        )
        
        dbt_silver_run >> dbt_silver_test

    # Task 3: dbt Gold transformations
    with TaskGroup("dbt_gold_transforms") as gold_group:
        dbt_gold_run = BashOperator(
            task_id="dbt_run_gold",
            bash_command=(
                "cd /opt/airflow/dbt && "
                "dbt run --select tag:gold --profiles-dir /opt/airflow/dbt"
            ),
            doc="Run dbt gold layer models (analytics-ready data)",
        )
        
        dbt_gold_test = BashOperator(
            task_id="dbt_test_gold",
            bash_command=(
                "cd /opt/airflow/dbt && "
                "dbt test --select tag:gold --profiles-dir /opt/airflow/dbt"
            ),
            doc="Test dbt gold layer models",
        )
        
        dbt_gold_run >> dbt_gold_test

    # Pipeline orchestration
    extract_task >> silver_group >> gold_group