"""
Google Drive Batch Ingestion DAG

Flow: Google Drive → MinIO (Raw)
Auth: Service Account (JSON key file)

Supported file types:
- CSV  → DataFrame → Parquet
- Excel (.xlsx, .xls) → DataFrame → Parquet
- JSON → DataFrame → Parquet
- Parquet → langsung upload ke MinIO
- DOCX → upload as-is (tanpa konversi)

Files saved to MinIO:
- s3://raw/gdrive/<folder_name>/<filename>.parquet  (untuk tabular)
- s3://raw/gdrive/<folder_name>/<filename>.docx     (untuk dokumen)

Setup steps ada di bagian bawah file ini (lihat SETUP GUIDE).
"""

from datetime import datetime, timedelta
import io
import pandas as pd
import boto3

from airflow import DAG

try:
    from airflow.operators.python import PythonOperator
except ModuleNotFoundError:
    from airflow.operators.python_operator import PythonOperator

# Google Drive SDK
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account

# ──────────────────────────────────────────────────────────────
# CONFIG — Sesuaikan bagian ini
# ──────────────────────────────────────────────────────────────

SERVICE_ACCOUNT_FILE = "/opt/airflow/credentials/gdrive_sa.json"

DRIVE_FOLDERS = {
    "api data": "1V4LpbYxR7R5cRYOW4xuAQlP1t_oAi7gj",
    "customers": "1PY9NJ8Q84TISJyMs8JHQotdUXTvXOLan",
}

SUPPORTED_MIME_TYPES = {
    "text/csv":                                                                      "csv",
    "application/vnd.ms-excel":                                                      "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":             "xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":       "docx",
    "application/json":                                                               "json",
    "application/octet-stream":                                                       "parquet",
}

AS_IS_EXTENSIONS = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MINIO_CONFIG = {
    "endpoint_url":          "http://lakehouse-lakekit-minio.lakehouse.svc.cluster.local:9000",
    "aws_access_key_id":     "minioadmin",
    "aws_secret_access_key": "LuuxHCNcehVJJ2nUZgl4tLYyIB0Mtn0T",
}
MINIO_BUCKET    = "raw"
MINIO_NAMESPACE = "gdrive"

# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _get_drive_service():
    """Build authenticated Google Drive service."""
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds  = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=scopes
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _get_s3_client():
    """Build boto3 S3 client pointing to MinIO."""
    return boto3.client("s3", **MINIO_CONFIG)


def _list_files_in_folder(service, folder_id: str) -> list[dict]:
    """List semua file di dalam folder Drive (tidak rekursif)."""
    results = []
    page_token = None

    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken, files(id, name, mimeType)",
            pageSize=100,
            pageToken=page_token,
        ).execute()

        results.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return results


def _download_file(service, file_id: str) -> bytes:
    """Download file content dari Google Drive sebagai bytes."""
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _to_parquet_bytes(raw_bytes: bytes, ext: str) -> bytes:
    """Konversi file tabular ke Parquet bytes."""
    if ext == "csv":
        df = pd.read_csv(io.BytesIO(raw_bytes))
    elif ext in ("xls", "xlsx"):
        df = pd.read_excel(io.BytesIO(raw_bytes))
    elif ext == "json":
        df = pd.read_json(io.BytesIO(raw_bytes))
    elif ext == "parquet":
        return raw_bytes
    else:
        raise ValueError(f"Unsupported extension for parquet conversion: {ext}")

    buf = io.BytesIO()
    df.to_parquet(buf, index=False, compression="snappy")
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────
# TASKS
# ──────────────────────────────────────────────────────────────

def extract_drive_to_minio():
    """Task: Scan semua folder Drive → upload ke MinIO."""
    print("\n" + "="*60)
    print("🚀 Starting Google Drive → MinIO Extraction")
    print("="*60)

    service = _get_drive_service()
    s3      = _get_s3_client()
    summary = []

    for namespace, folder_id in DRIVE_FOLDERS.items():
        print(f"\n📁 Scanning folder: {namespace} ({folder_id})")
        files = _list_files_in_folder(service, folder_id)
        print(f"   Found {len(files)} file(s)")

        for f in files:
            mime     = f["mimeType"]
            filename = f["name"]
            fid      = f["id"]

            ext = SUPPORTED_MIME_TYPES.get(mime)

            if ext is None:
                for candidate in ("csv", "xlsx", "xls", "json", "parquet", "docx"):
                    if filename.lower().endswith(f".{candidate}"):
                        ext = candidate
                        break

            if ext is None:
                print(f"   ⏭️  Skip (unsupported): {filename} [{mime}]")
                continue

            try:
                print(f"   ⬇️  Downloading: {filename}")
                raw  = _download_file(service, fid)
                stem = filename.rsplit(".", 1)[0] if "." in filename else filename

                if ext in AS_IS_EXTENSIONS:
                    content_type = AS_IS_EXTENSIONS[ext]
                    s3_key       = f"{MINIO_NAMESPACE}/{namespace}/{stem}.{ext}"
                    body         = raw
                else:
                    content_type = "application/octet-stream"
                    s3_key       = f"{MINIO_NAMESPACE}/{namespace}/{stem}.parquet"
                    body         = _to_parquet_bytes(raw, ext)

                s3.put_object(
                    Bucket=MINIO_BUCKET,
                    Key=s3_key,
                    Body=body,
                    ContentType=content_type,
                )

                size_mb = len(body) / 1024 / 1024
                path    = f"s3://{MINIO_BUCKET}/{s3_key}"
                print(f"   ✅ Uploaded → {path} ({size_mb:.2f} MB)")

                summary.append({
                    "namespace":  namespace,
                    "file":       filename,
                    "minio_path": path,
                    "size_mb":    round(size_mb, 2),
                })

            except Exception as e:
                print(f"   ❌ Error [{filename}]: {e}")
                raise

    print("\n" + "="*60)
    print(f"✅ Extraction complete — {len(summary)} file(s) uploaded")
    for s in summary:
        print(f"   {s['namespace']}/{s['file']} → {s['minio_path']}")
    print("="*60)

    return summary


# ──────────────────────────────────────────────────────────────
# DAG DEFINITION
# ──────────────────────────────────────────────────────────────

default_args = {
    "owner":       "airflow",
    "retries":     1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    "google_drive_ingestion",
    default_args=default_args,
    description="Google Drive (all files) → MinIO raw/gdrive",
    schedule="0 3 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ingestion", "batch", "gdrive", "minio"],
    max_active_runs=1,
) as dag:

    extract_task = PythonOperator(
        task_id="extract_drive_to_minio",
        python_callable=extract_drive_to_minio,
        doc="Download semua file dari Google Drive folders dan upload ke MinIO (tabular → Parquet, lainnya → as-is)",
    )


# ══════════════════════════════════════════════════════════════
# SETUP GUIDE — Baca ini sebelum deploy DAG
# ══════════════════════════════════════════════════════════════
#
# STEP 1 — Buat Service Account di Google Cloud Console
# ─────────────────────────────────────────────────────
# 1. Buka: https://console.cloud.google.com/iam-admin/serviceaccounts
# 2. Pilih project → klik "Create Service Account"
# 3. Isi nama, misal: airflow-drive-reader
# 4. Klik "Create and Continue"
# 5. Role: tidak perlu assign role (akses Drive lewat sharing)
# 6. Klik "Done"
# 7. Klik service account yang baru dibuat → tab "Keys"
# 8. Add Key → Create new key → JSON → Download
#
#
# STEP 2 — Aktifkan Google Drive API
# ────────────────────────────────────
# 1. Buka: https://console.cloud.google.com/apis/library/drive.googleapis.com
# 2. Klik "Enable"
#
#
# STEP 3 — Share Google Drive Folder ke Service Account
# ──────────────────────────────────────────────────────
# 1. Buka Google Drive di browser
# 2. Klik kanan folder → "Share"
# 3. Tambahkan email service account (field "client_email" di file JSON)
#    Contoh: airflow-drive-reader@your-project.iam.gserviceaccount.com
# 4. Set permission: "Viewer"
#
#    ⚠️ Jika folder belum di-share, DAG akan error "File not found"
#
#
# STEP 4 — Ambil Folder ID dari Google Drive
# ───────────────────────────────────────────
# 1. Buka folder di Google Drive browser
# 2. Lihat URL: https://drive.google.com/drive/folders/1ABCxxxxx
#                                                      ^^^^^^^^^^
#                                                      ini Folder ID-nya
# 3. Copy ID tersebut ke DRIVE_FOLDERS di bagian CONFIG atas
#
#
# STEP 5 — Letakkan file JSON credentials di container Airflow
# ─────────────────────────────────────────────────────────────
#   openmetadata/
#   ├── docker-compose-postgres.yml
#   ├── airflow-local/
#   │   ├── dags/
#   │   │   └── google_drive_ingestion_dag.py
#   │   └── credentials/
#   │       └── gdrive_sa.json
#
# Path di container = /opt/airflow/credentials/gdrive_sa.json
#
#
# STEP 6 — Install dependencies di container Airflow
# ────────────────────────────────────────────────────
#   google-api-python-client>=2.100.0
#   google-auth>=2.23.0
#   google-auth-httplib2>=0.1.1
#   pandas>=2.0.0
#   pyarrow>=14.0.0
#   openpyxl>=3.1.0
#   boto3>=1.28.0
#
#
# STEP 7 — Deploy dan Test DAG
# ──────────────────────────────
# 1. Copy DAG ke ./airflow-local/dags/
# 2. Buka Airflow UI: http://localhost:8080
# 3. Cari DAG "google_drive_ingestion"
# 4. Toggle ON → Trigger manually untuk test pertama
#
#
# STEP 8 — Verifikasi di MinIO
# ─────────────────────────────
# MinIO Console : http://localhost:9001
#   → Bucket: raw → folder: gdrive/<namespace>/
#   → File tabular muncul sebagai .parquet
#   → File docx muncul dengan ekstensi asli .docx
#
# ══════════════════════════════════════════════════════════════