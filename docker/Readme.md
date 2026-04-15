Overview Alurnya
Dockerfile + requirements.txt
        ↓
  docker build
        ↓
  docker push → registry.sicabe.com
        ↓
  update values.yaml → helm upgrade

Step 1 — Buat requirements.txt
Di folder project kamu, buat file requirements.txt:
txtdlt[postgres]
duckdb
dlt[filesystem]
s3fs

Step 2 — Buat Dockerfile
dockerfileFROM apache/airflow:2.10.5

USER airflow

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

Penting: USER airflow sebelum pip install — jangan pakai root.


Step 3 — Build & Push ke Registry Kamu
bash# Login dulu ke registry kamu
docker login registry.sicabe.com

# Build image
docker build -t registry.sicabe.com/airflow-custom:latest .

# Push ke registry
docker push registry.sicabe.com/airflow-custom:latest
Verifikasi image sudah masuk:
bashcurl https://registry.sicabe.com/v2/airflow-custom/tags/list

Step 4 — Update config/values.yaml
Tambahkan/edit bagian berikut di values.yaml kamu:
yamlimages:
  airflow:
    repository: registry.sicabe.com/airflow-custom
    tag: latest
    pullPolicy: Always
Kalau registry kamu private dan butuh auth, kamu perlu tambahkan imagePullSecrets. Buat secret dulu:
bashkubectl create secret docker-registry registry-sicabe-secret \
  --docker-server=registry.sicabe.com \
  --docker-username=YOUR_USERNAME \
  --docker-password=YOUR_PASSWORD \
  --namespace airflow
Lalu di values.yaml:
yamlimages:
  airflow:
    repository: registry.sicabe.com/airflow-custom
    tag: latest
    pullPolicy: Always

# Tambahkan ini
registry:
  secretName: registry-sicabe-secret

Step 5 — Helm Upgrade
bash./scripts/deploy.sh upgrade

# Atau manual:
helm upgrade airflow apache-airflow/airflow \
  --namespace airflow \
  --values config/values.yaml \
  --timeout 15m

Step 6 — Verifikasi
bash# Cek pods pakai image baru
kubectl get pods -n airflow -o wide

# Cek image yang dipakai pod scheduler
kubectl describe pod -l component=scheduler -n airflow | grep Image

# Verifikasi library terinstall
kubectl exec -it $(kubectl get pod -l component=scheduler -n airflow -o jsonpath='{.items[0].metadata.name}') \
  -n airflow -c scheduler -- pip list | grep dlt

Tips Versioning Image
Daripada selalu pakai latest, lebih baik pakai tag versi biar rollback lebih mudah:
bashdocker build -t registry.sicabe.com/airflow-custom:v1.0.0 .
docker push registry.sicabe.com/airflow-custom:v1.0.0
yaml# values.yaml
images:
  airflow:
    repository: registry.sicabe.com/airflow-custom
    tag: v1.0.0      # ganti ini tiap update
    pullPolicy: IfNotPresent   # lebih efisien untuk tag fixed

Kalau registry kamu perlu TLS atau ada auth khusus, share errornya dan saya bantu debug lebih lanjut.