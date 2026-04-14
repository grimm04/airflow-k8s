#!/usr/bin/env bash
# =============================================================================
# deploy.sh
# =============================================================================
# Script untuk deploy atau upgrade Apache Airflow di Kubernetes via Helm.
#
# CARA PAKAI:
#   chmod +x scripts/deploy.sh
#   ./scripts/deploy.sh [install|upgrade|status|uninstall]
#
# Default (tanpa argumen) = upgrade --install (idempotent)
# =============================================================================

set -e

# Warna output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

NAMESPACE="airflow"
RELEASE_NAME="airflow"
VALUES_FILE="$PROJECT_DIR/config/values.yaml"
SECRET_FILE="$PROJECT_DIR/secrets/git-credentials.yaml"
CHART="apache-airflow/airflow"
TIMEOUT="15m"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Airflow Kubernetes Deployment         ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

ACTION="${1:-upgrade}"

# ---- Helper functions -------------------------------------------------------

check_prerequisites() {
  echo -e "${BLUE}🔍 Memeriksa prerequisites...${NC}"

  for cmd in kubectl helm; do
    if ! command -v "$cmd" &>/dev/null; then
      echo -e "${RED}✗ '$cmd' tidak ditemukan di WSL.${NC}"
      echo -e "  Jalankan dulu: ./scripts/setup-wsl.sh"
      exit 1
    fi
    echo -e "  ${GREEN}✓ $cmd ditemukan${NC}"
  done

  # Cek KUBECONFIG sudah di-set (dari setup-wsl.sh)
  if [ -z "$KUBECONFIG" ]; then
    echo -e "${YELLOW}⚠ KUBECONFIG belum di-set.${NC}"
    echo -e "  Jalankan: source ~/airflow-k8s-env.sh"
    echo -e "  Atau jalankan dulu: ./scripts/setup-wsl.sh"
    exit 1
  fi
  echo -e "  ${GREEN}✓ KUBECONFIG = $KUBECONFIG${NC}"

  # Cek bisa konek ke cluster
  if ! kubectl cluster-info &>/dev/null; then
    echo -e "${RED}✗ Tidak bisa konek ke Kubernetes cluster.${NC}"
    echo -e "  Pastikan Minikube sudah running di Windows."
    echo -e "  Lalu jalankan: source ~/airflow-k8s-env.sh"
    exit 1
  fi
  echo -e "  ${GREEN}✓ Cluster dapat diakses${NC}"

  # Cek values.yaml ada
  if [ ! -f "$VALUES_FILE" ]; then
    echo -e "${RED}✗ File tidak ditemukan: $VALUES_FILE${NC}"
    exit 1
  fi
  echo -e "  ${GREEN}✓ config/values.yaml ada${NC}"
  echo ""
}

check_repo_configured() {
  # Cek apakah user sudah mengisi repo URL
  if grep -q "YOUR_USERNAME" "$VALUES_FILE"; then
    echo -e "${RED}⚠ PERINGATAN: Kamu belum mengisi 'repo' di config/values.yaml!${NC}"
    echo -e "  Buka config/values.yaml dan ganti:"
    echo -e "    repo: \"https://github.com/YOUR_USERNAME/YOUR_REPO.git\""
    echo ""
    echo -e "${YELLOW}Lanjut tetap? (y/n):${NC}"
    read -r CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
      exit 0
    fi
  fi
}

ensure_namespace() {
  if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
    echo -e "${BLUE}📁 Membuat namespace '$NAMESPACE'...${NC}"
    kubectl create namespace "$NAMESPACE"
    echo -e "${GREEN}✓ Namespace '$NAMESPACE' dibuat${NC}"
  else
    echo -e "${GREEN}✓ Namespace '$NAMESPACE' sudah ada${NC}"
  fi
}

ensure_helm_repo() {
  if ! helm repo list | grep -q "apache-airflow"; then
    echo -e "${BLUE}📦 Menambahkan Helm repo apache-airflow...${NC}"
    helm repo add apache-airflow https://airflow.apache.org
  fi
  echo -e "${BLUE}🔄 Mengupdate Helm repos...${NC}"
  helm repo update
  echo ""
}

apply_secret() {
  if [ -f "$SECRET_FILE" ]; then
    # Cek apakah masih ada placeholder
    if grep -q "<base64_encoded" "$SECRET_FILE"; then
      echo -e "${YELLOW}⚠ File secrets/git-credentials.yaml masih berisi placeholder.${NC}"
      echo -e "  Jalankan: ./scripts/encode-credentials.sh"
      echo -e "  atau isi manual, lalu deploy ulang."
      echo ""
    else
      echo -e "${BLUE}🔐 Applying git-credentials secret...${NC}"
      kubectl apply -f "$SECRET_FILE" -n "$NAMESPACE"
      echo -e "${GREEN}✓ Secret git-credentials applied${NC}"
    fi
  else
    echo -e "${YELLOW}⚠ File secrets/git-credentials.yaml tidak ditemukan. Skip.${NC}"
  fi
  echo ""
}

# ---- Actions ----------------------------------------------------------------

do_deploy() {
  check_prerequisites
  check_repo_configured
  ensure_namespace
  ensure_helm_repo
  apply_secret

  echo -e "${BLUE}🚀 Deploy Airflow dengan Helm...${NC}"
  echo -e "   Release : $RELEASE_NAME"
  echo -e "   Namespace: $NAMESPACE"
  echo -e "   Values  : $VALUES_FILE"
  echo -e "   Timeout : $TIMEOUT"
  echo ""

  helm upgrade --install "$RELEASE_NAME" "$CHART" \
    --namespace "$NAMESPACE" \
    --values "$VALUES_FILE" \
    --timeout "$TIMEOUT" \
    --debug

  echo ""
  echo -e "${GREEN}✓ Deploy selesai!${NC}"
  do_status
}

do_status() {
  echo ""
  echo -e "${BLUE}📊 Status Helm Release:${NC}"
  helm ls -n "$NAMESPACE"

  echo ""
  echo -e "${BLUE}🔍 Status Pods:${NC}"
  kubectl get pods -n "$NAMESPACE"

  echo ""
  echo -e "${BLUE}🌐 Akses Airflow:${NC}"
  # WIN_HOST_IP di-set oleh setup-wsl.sh via ~/airflow-k8s-env.sh
  # Fallback: baca dari /etc/resolv.conf jika env var belum di-set
  ACCESS_IP="${WIN_HOST_IP:-$(grep nameserver /etc/resolv.conf | awk '{print $2}' | head -1)}"
  echo -e "  Airflow UI : ${GREEN}http://$ACCESS_IP:31151${NC}"
  echo -e "  Flower UI  : ${GREEN}http://$ACCESS_IP:31555${NC}"
  echo -e "  Login      : admin / admin"
  echo ""
  echo -e "  ${YELLOW}ℹ Buka URL di atas di browser Windows (bukan WSL)${NC}"
}

do_uninstall() {
  echo -e "${YELLOW}⚠ Ini akan menghapus Airflow dari namespace '$NAMESPACE'.${NC}"
  echo -e "Lanjut? (y/n):"
  read -r CONFIRM
  if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
    helm uninstall "$RELEASE_NAME" -n "$NAMESPACE"
    echo -e "${GREEN}✓ Airflow dihapus.${NC}"
  else
    echo "Dibatalkan."
  fi
}

# ---- Main -------------------------------------------------------------------

case "$ACTION" in
  install|upgrade|deploy)
    do_deploy
    ;;
  status)
    do_status
    ;;
  uninstall|delete|remove)
    do_uninstall
    ;;
  *)
    echo -e "${RED}Unknown action: $ACTION${NC}"
    echo "Usage: $0 [install|upgrade|status|uninstall]"
    exit 1
    ;;
esac