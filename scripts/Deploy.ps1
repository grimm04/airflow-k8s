# =============================================================================
# Deploy.ps1
# =============================================================================
# Script untuk deploy / upgrade / cek status Apache Airflow di Minikube
# menggunakan Helm — dijalankan langsung di Windows PowerShell.
#
# CARA PAKAI:
#   .\scripts\Deploy.ps1              # deploy / upgrade (default)
#   .\scripts\Deploy.ps1 -Action status
#   .\scripts\Deploy.ps1 -Action uninstall
#
# Jika muncul error "execution policy":
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# =============================================================================

param(
    [ValidateSet("install", "upgrade", "deploy", "status", "uninstall", "delete")]
    [string]$Action = "upgrade"
)

$ErrorActionPreference = "Stop"

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir  = Split-Path -Parent $ScriptDir
$ValuesFile  = Join-Path $ProjectDir "config\values.yaml"
$SecretFile  = Join-Path $ProjectDir "secrets\git-credentials.yaml"

$Namespace   = "airflow"
$ReleaseName = "airflow"
$Chart       = "apache-airflow/airflow"
$Timeout     = "15m"

function Write-Header {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Airflow Kubernetes Deployment         " -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

# -----------------------------------------------------------------------------
# Cek prerequisites
# -----------------------------------------------------------------------------
function Test-Prerequisites {
    Write-Host "🔍 Memeriksa prerequisites..." -ForegroundColor Cyan

    foreach ($cmd in @("kubectl", "helm", "minikube")) {
        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
            Write-Host "  ✗ '$cmd' tidak ditemukan. Install terlebih dahulu." -ForegroundColor Red
            switch ($cmd) {
                "minikube" { Write-Host "    → https://minikube.sigs.k8s.io/docs/start/" }
                "helm"     { Write-Host "    → https://helm.sh/docs/intro/install/" }
                "kubectl"  { Write-Host "    → https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/" }
            }
            exit 1
        }
        Write-Host "  ✓ $cmd ditemukan" -ForegroundColor Green
    }

    if (-not (Test-Path $ValuesFile)) {
        Write-Host "  ✗ File tidak ditemukan: $ValuesFile" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ config\values.yaml ada" -ForegroundColor Green

    # Cek Minikube running
    $mkStatus = minikube status --format='{{.Host}}' 2>$null
    if ($mkStatus -ne "Running") {
        Write-Host ""
        Write-Host "  ✗ Minikube belum running. Jalankan dulu: minikube start" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Minikube running" -ForegroundColor Green
    Write-Host ""
}

# -----------------------------------------------------------------------------
# Cek apakah repo di values.yaml sudah diisi
# -----------------------------------------------------------------------------
function Test-RepoConfigured {
    $content = Get-Content $ValuesFile -Raw
    if ($content -match "YOUR_USERNAME") {
        Write-Host "⚠ PERINGATAN: Kamu belum mengisi 'repo' di config\values.yaml!" -ForegroundColor Yellow
        Write-Host "  Buka config\values.yaml dan ganti:" -ForegroundColor Yellow
        Write-Host "    repo: `"https://github.com/YOUR_USERNAME/YOUR_REPO.git`"" -ForegroundColor Yellow
        Write-Host ""
        $confirm = Read-Host "Lanjut tetap? (y/n)"
        if ($confirm -notmatch '^[Yy]$') { exit 0 }
    }
}

# -----------------------------------------------------------------------------
# Buat namespace jika belum ada
# -----------------------------------------------------------------------------
function Ensure-Namespace {
    $exists = kubectl get namespace $Namespace 2>$null
    if (-not $exists) {
        Write-Host "📁 Membuat namespace '$Namespace'..." -ForegroundColor Cyan
        kubectl create namespace $Namespace
        Write-Host "  ✓ Namespace '$Namespace' dibuat" -ForegroundColor Green
    } else {
        Write-Host "  ✓ Namespace '$Namespace' sudah ada" -ForegroundColor Green
    }
}

# -----------------------------------------------------------------------------
# Tambah / update Helm repo
# -----------------------------------------------------------------------------
function Ensure-HelmRepo {
    $repos = helm repo list 2>$null
    if ($repos -notmatch "apache-airflow") {
        Write-Host "📦 Menambahkan Helm repo apache-airflow..." -ForegroundColor Cyan
        helm repo add apache-airflow https://airflow.apache.org
    }
    Write-Host "🔄 Mengupdate Helm repos..." -ForegroundColor Cyan
    helm repo update
    Write-Host ""
}

# -----------------------------------------------------------------------------
# Apply Kubernetes secret untuk GitHub credentials
# -----------------------------------------------------------------------------
function Apply-Secret {
    if (-not (Test-Path $SecretFile)) {
        Write-Host "⚠ File secrets\git-credentials.yaml tidak ditemukan. Skip." -ForegroundColor Yellow
        return
    }

    $content = Get-Content $SecretFile -Raw
    if ($content -match "<base64_encoded") {
        Write-Host "⚠ File secrets\git-credentials.yaml masih berisi placeholder." -ForegroundColor Yellow
        Write-Host "  Jalankan dulu: .\scripts\Encode-Credentials.ps1" -ForegroundColor Yellow
        Write-Host ""
        return
    }

    Write-Host "🔐 Applying git-credentials secret..." -ForegroundColor Cyan
    kubectl apply -f $SecretFile -n $Namespace
    Write-Host "  ✓ Secret git-credentials applied" -ForegroundColor Green
    Write-Host ""
}

# -----------------------------------------------------------------------------
# Deploy / upgrade Airflow
# -----------------------------------------------------------------------------
function Invoke-Deploy {
    Test-Prerequisites
    Test-RepoConfigured
    Ensure-Namespace
    Ensure-HelmRepo
    Apply-Secret

    Write-Host "🚀 Deploy Airflow dengan Helm..." -ForegroundColor Cyan
    Write-Host "   Release  : $ReleaseName"
    Write-Host "   Namespace: $Namespace"
    Write-Host "   Values   : $ValuesFile"
    Write-Host "   Timeout  : $Timeout"
    Write-Host ""

    helm upgrade --install $ReleaseName $Chart `
        --namespace $Namespace `
        --values $ValuesFile `
        --timeout $Timeout `
        --debug

    Write-Host ""
    Write-Host "✓ Deploy selesai!" -ForegroundColor Green
    Show-Status
}

# -----------------------------------------------------------------------------
# Status
# -----------------------------------------------------------------------------
function Show-Status {
    Write-Host ""
    Write-Host "📊 Status Helm Release:" -ForegroundColor Cyan
    helm ls -n $Namespace

    Write-Host ""
    Write-Host "🔍 Status Pods:" -ForegroundColor Cyan
    kubectl get pods -n $Namespace

    Write-Host ""
    Write-Host "🌐 Akses Airflow:" -ForegroundColor Cyan
    $ip = minikube ip
    Write-Host "   Airflow UI : http://$ip`:31151" -ForegroundColor Green
    Write-Host "   Flower UI  : http://$ip`:31555" -ForegroundColor Green
    Write-Host "   Login      : admin / admin"
    Write-Host ""
}

# -----------------------------------------------------------------------------
# Uninstall
# -----------------------------------------------------------------------------
function Invoke-Uninstall {
    Write-Host "⚠ Ini akan menghapus Airflow dari namespace '$Namespace'." -ForegroundColor Yellow
    $confirm = Read-Host "Lanjut? (y/n)"
    if ($confirm -match '^[Yy]$') {
        helm uninstall $ReleaseName -n $Namespace
        Write-Host "✓ Airflow dihapus." -ForegroundColor Green
    } else {
        Write-Host "Dibatalkan."
    }
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
Write-Header

switch ($Action) {
    { $_ -in "install","upgrade","deploy" } { Invoke-Deploy }
    "status"                                { Show-Status }
    { $_ -in "uninstall","delete" }         { Invoke-Uninstall }
}
