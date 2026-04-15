# =============================================================================
# example_dag.py
# =============================================================================
# Contoh DAG sederhana untuk memverifikasi bahwa git-sync berjalan dengan benar.
# Simpan file ini di folder yang kamu set sebagai 'subPath' di values.yaml.
# =============================================================================

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# Default arguments untuk semua task dalam DAG ini
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Definisi DAG
with DAG(
    dag_id="example_hello_world",
    description="DAG contoh untuk verifikasi git-sync dari GitHub",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule="@daily",  # Jalan setiap hari
    catchup=False,                # Jangan jalankan run yang terlewat
    tags=["example", "test"],
) as dag:

    # Task 1: Print info dengan BashOperator
    task_bash_hello = BashOperator(
        task_id="bash_hello",
        bash_command='echo "Hello from Airflow on Kubernetes! Time: $(date)"',
    )

    # Task 2: Python function dengan PythonOperator
    def print_python_info(**context):
        print("=== Airflow Task Info ===")
        print(f"DAG ID       : {context['dag'].dag_id}")
        print(f"Run ID       : {context['run_id']}")
        print(f"Execution    : {context['execution_date']}")
        print(f"Task Instance: {context['task_instance_key_str']}")
        print("git-sync bekerja dengan benar!")
        return "success"

    task_python_info = PythonOperator(
        task_id="python_info",
        python_callable=print_python_info,
        # provide_context=True,
    )

    # Task 3: Verifikasi environment
    task_check_env = BashOperator(
        task_id="check_environment",
        bash_command="""
            echo "=== Airflow Environment ===" &&
            echo "AIRFLOW_HOME: $AIRFLOW_HOME" &&
            echo "Python version: $(python --version)" &&
            echo "DAG folder: $(ls $AIRFLOW_HOME/dags/ 2>/dev/null || echo 'tidak ada')"
        """,
    )

    # Urutan eksekusi task
    task_bash_hello >> task_python_info >> task_check_env
