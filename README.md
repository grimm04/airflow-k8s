# Apache Airflow on Kubernetes — Local Config Setup

Deploy Apache Airflow di atas Kubernetes (Minikube) menggunakan Helm, dengan seluruh konfigurasi tersimpan lokal dan terdokumentasi.

> **Berdasarkan tutorial:** [Deploying Apache Airflow on Kubernetes with Helm and Minikube](https://medium.com/@jdegbun/deploying-apache-airflow-on-kubernetes-with-helm-and-minikube-syncing-dags-from-github-bce4730d7881)  
> **Perbedaan:** Semua konfigurasi disimpan ke file lokal, bukan langsung dilempar ke Helm — sehingga setiap parameter terdokumentasi dan bisa di-track via Git.

---

## Struktur Proyek

```
airflow-k8s/
├── config/
│   └── values.yaml                  # ← Seluruh konfigurasi Helm (utama)
├── secrets/
│   ├── git-credentials.yaml         # ← Secret GitHub (JANGAN dicommit!)
│   └── git-credentials.yaml.example # ← Template secret (aman dicommit)
├── dags/
│   └── example_dag.py               # ← Contoh DAG untuk testing
├── scripts/
│   ├── encode-credentials.sh        # ← Helper encode GitHub credentials
│   └── deploy.sh                    # ← Script deploy / upgrade / status
├── .gitignore
└── README.md
```

---

## Prerequisites

Pastikan tools berikut sudah terinstall di sistem kamu:

| Tool       | Versi yang diuji | Cara install                          |
|------------|-----------------|---------------------------------------|
| Docker     | 27.4.1+         | https://docs.docker.com/get-docker/   |
| Minikube   | v1.34.0+        | https://minikube.sigs.k8s.io/docs/    |
| Helm       | v3.16.2+        | https://helm.sh/docs/intro/install/   |
| kubectl    | sesuai cluster  | https://kubernetes.io/docs/tasks/tools/ |

Verifikasi semua sudah terinstall:
```bash
docker --version
minikube version
helm version
kubectl version --client
```

---

## Langkah-Langkah Deploy

### Step 1 — Clone / Setup Proyek

Jika kamu memulai dari awal, clone atau copy folder ini ke mesin lokal kamu:

```bash
git clone <repo-ini> airflow-k8s
cd airflow-k8s
```

Beri izin eksekusi pada scripts:

```bash
chmod +x scripts/*.sh
```

---

### Step 2 — Siapkan GitHub Repository untuk DAGs

Airflow akan meng-clone repository GitHub-mu secara otomatis untuk mengambil file DAG.

**2a. Buat repository di GitHub** (bisa public atau private).

**2b. Buat struktur folder DAGs di repo tersebut:**

```
your-dag-repo/
└── dags/
    ├── example_dag.py
    └── ... (DAG lainnya)
```

> Folder `dags/` ini yang akan diisi ke `subPath` di `config/values.yaml`.

**2c. Copy contoh DAG ke repo-mu:**

```bash
cp dags/example_dag.py /path/ke/repo-github-kamu/dags/
```

Lalu commit dan push ke GitHub.

---

### Step 3 — Buat GitHub Personal Access Token (PAT)

Token ini dibutuhkan agar git-sync bisa pull dari repository GitHub-mu (terutama jika private).

1. Buka: https://github.com/settings/tokens
2. Klik **"Generate new token"** → **"Generate new token (classic)"**
3. Beri nama token, misalnya: `airflow-gitsync`
4. Centang scope: **`repo`** (Full control of private repositories)
5. Klik **Generate token**
6. **Salin token-nya sekarang** — tidak akan tampil lagi!

---

### Step 4 — Isi Kredensial GitHub

Jalankan script helper yang akan encode kredensial ke base64 dan mengisi `secrets/git-credentials.yaml`:

```bash
./scripts/encode-credentials.sh
```

Script akan meminta:
- GitHub username
- GitHub Personal Access Token

Lalu otomatis mengisi `secrets/git-credentials.yaml`.

**Alternatif manual:** Encode sendiri lalu isi file:

```bash
# Encode username
echo -n "your_github_username" | base64

# Encode PAT
echo -n "your_github_pat" | base64
```

Lalu buka `secrets/git-credentials.yaml` dan ganti semua `<base64_encoded_*>` dengan hasil encode di atas.

---

### Step 5 — Edit Konfigurasi Utama

Buka `config/values.yaml` dan sesuaikan bagian-bagian berikut:

#### 5a. URL Repository GitHub

```yaml
dags:
  gitSync:
    repo: "https://github.com/YOUR_USERNAME/YOUR_REPO.git"  # ← Ganti ini
    branch: "main"   # ← Sesuaikan nama branch
    subPath: "dags"  # ← Folder dalam repo yang berisi DAG. Kosongkan ("") jika di root
```

#### 5b. NodePort untuk Akses Web UI (opsional)

```yaml
webserver:
  service:
    type: NodePort
    ports:
      - nodePort: 31151  # ← Ganti jika port sudah digunakan
```

#### 5c. Default User Login

```yaml
webserver:
  defaultUser:
    username: admin
    password: admin  # ← GANTI di production!
```

#### 5d. Konfigurasi Lain (opsional)

Semua konfigurasi di `config/values.yaml` sudah diberi komentar penjelasan. Baca dan sesuaikan sesuai kebutuhan.

---

### Step 6 — Jalankan Minikube

```bash
minikube start
```

Tunggu hingga cluster siap. Verifikasi:

```bash
kubectl get nodes
# Output: NAME       STATUS   ROLES           AGE   VERSION
#         minikube   Ready    control-plane   ...   v1.x.x
```

---

### Step 7 — Deploy Airflow

Jalankan script deploy:

```bash
./scripts/deploy.sh
```

Script ini akan otomatis:
1. Memeriksa prerequisites (kubectl, helm, minikube)
2. Membuat namespace `airflow`
3. Menambahkan Helm repo apache-airflow
4. Meng-apply secret `git-credentials`
5. Menjalankan `helm upgrade --install` dengan `config/values.yaml`

**Alternatif manual (tanpa script):**

```bash
# Buat namespace
kubectl create namespace airflow

# Tambah Helm repo
helm repo add apache-airflow https://airflow.apache.org
helm repo update

# Apply secret GitHub
kubectl apply -f secrets/git-credentials.yaml -n airflow

# Deploy Airflow
helm upgrade --install airflow apache-airflow/airflow \
  --namespace airflow \
  --values config/values.yaml \
  --timeout 15m \
  --debug
```

> Proses ini memakan waktu **5–15 menit** tergantung kecepatan internet dan spesifikasi mesin.

---

### Step 8 — Verifikasi Deploy

Cek semua pods berjalan:

```bash
kubectl get pods -n airflow
```

Tunggu hingga semua pod statusnya `Running`. Contoh output yang benar:

```
NAME                                 READY   STATUS    RESTARTS   AGE
airflow-scheduler-xxx                2/2     Running   0          5m
airflow-webserver-xxx                1/1     Running   0          5m
airflow-worker-xxx                   2/2     Running   0          5m
airflow-triggerer-xxx                2/2     Running   0          5m
airflow-postgresql-0                 1/1     Running   0          5m
airflow-redis-0                      1/1     Running   0          5m
```

Cek Helm release:

```bash
helm ls -n airflow
```

---

### Step 9 — Akses Airflow Web UI

Dapatkan IP Minikube:

```bash
minikube ip
# Contoh output: 192.168.49.2
```

Buka browser dan akses:

```
http://192.168.49.2:31151
```

Login dengan:
- **Username:** `admin`
- **Password:** `admin`

Untuk Flower (monitoring Celery workers):

```
http://192.168.49.2:31555
```

---

### Step 10 — Verifikasi git-sync Berjalan

Setelah login, DAG dari GitHub seharusnya sudah muncul di Airflow UI dalam beberapa menit.

Cek log git-sync secara langsung:

```bash
# Temukan nama pod scheduler
kubectl get pods -n airflow | grep scheduler

# Lihat log container git-sync di dalam pod scheduler
kubectl logs <nama-pod-scheduler> -n airflow -c git-sync
```

Jika berhasil, kamu akan melihat log seperti:
```
level=info msg="cloning repo" repo="https://github.com/..."
level=info msg="successfully synced" ...
```

---

## Cara Update Konfigurasi

Jika kamu mengubah sesuatu di `config/values.yaml`, apply perubahan dengan:

```bash
./scripts/deploy.sh upgrade

# Atau manual:
helm upgrade airflow apache-airflow/airflow \
  --namespace airflow \
  --values config/values.yaml \
  --timeout 15m
```

---

## Troubleshooting

### Pod stuck di `Pending`
```bash
kubectl describe pod <nama-pod> -n airflow
```
Biasanya karena resource (CPU/RAM) tidak cukup. Coba tambah resource Minikube:
```bash
minikube stop
minikube start --cpus 4 --memory 8192
```

### DAG tidak muncul di UI
1. Cek log git-sync: `kubectl logs <scheduler-pod> -n airflow -c git-sync`
2. Pastikan URL repo, branch, dan subPath di `config/values.yaml` sudah benar
3. Pastikan secret sudah di-apply: `kubectl get secret git-credentials -n airflow`
4. Jika repo private, pastikan token punya akses `repo`

### Webserver tidak bisa diakses
```bash
# Cek service
kubectl get svc -n airflow

# Cek minikube ip
minikube ip

# Coba tunnel alternatif
minikube service airflow-webserver -n airflow
```

### Melihat semua log Airflow
```bash
# Webserver
kubectl logs -l component=webserver -n airflow --tail=50

# Scheduler
kubectl logs -l component=scheduler -n airflow -c scheduler --tail=50

# Worker
kubectl logs -l component=worker -n airflow --tail=50
```

### Reset total
```bash
./scripts/deploy.sh uninstall
kubectl delete namespace airflow
# Lalu deploy ulang dari Step 6
```

---

## Hapus / Uninstall

```bash
./scripts/deploy.sh uninstall

# Hapus namespace (opsional, akan hapus semua resource di dalamnya)
kubectl delete namespace airflow

# Stop Minikube
minikube stop
```

---

## Referensi

- [Apache Airflow Helm Chart Docs](https://airflow.apache.org/docs/helm-chart/stable/index.html)
- [Apache Airflow Helm Chart Parameters](https://airflow.apache.org/docs/helm-chart/stable/parameters-ref.html)
- [git-sync Documentation](https://github.com/kubernetes/git-sync)
- [Minikube Docs](https://minikube.sigs.k8s.io/docs/)
- [Helm Docs](https://helm.sh/docs/)
