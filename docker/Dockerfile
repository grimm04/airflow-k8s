FROM apache/airflow:3.1.8

USER airflow

COPY requirements.txt /requirements.txt
COPY .env /opt/airflow/.env
RUN pip install --no-cache-dir -r /requirements.txt