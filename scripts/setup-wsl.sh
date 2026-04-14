#!/usr/bin/env bash
# =============================================================================
# setup-wsl.sh
# =============================================================================
# Script untuk menghubungkan WSL (kubectl + helm) ke Minikube yang berjalan
# di Windows dengan driver Docker Desktop.
#
# Masalah:
#   - Minikube jalan di Windows
#   - kubectl/helm dijalankan dari WSL
#   - WSL tidak otomatis bisa akses kubeconfig dari Windows
#
# Solusi yang dilakukan script ini:
#   1. Install kubectl di WSL (jika belum ada)
#   2. Install helm di WSL (jika belum ada)
#   3. Copy kubeconfig dari Windows (~/.kube/config) ke WSL
#   4. Set KUBECONFIG environment variable
#   5. Verifikasi koneksi ke cluster
#
# CARA PAKAI:
#   chmod +x scripts/setup-wsl.sh
#   ./scripts/setup-wsl.sh
#
# Setelah selesai, tambahkan ke ~/.bashrc atau ~/.zshrc:
#   source ~/airflow-k8s-env.sh
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Global variables (diisi oleh fungsi-fungsi di bawah)
WIN_HOME=""
WIN_USER=""
WIN_HOST_IP=""
WSL_KUBE_CONFIG="$HOME/.kube/config-minikube-windows"
ENV_FILE="$HOME/airflow-k8s-env.sh"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  WSL → Minikube (Windows) Setup           ${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# -----------------------------------------------------------------------------
# Deteksi Windows username
# -----------------------------------------------------------------------------
detect_windows_user() {
  # Folder-folder sistem Windows yang harus di-skip
  SYSTEM_FOLDERS="^(Public|Default|Default User|All Users|desktop\.ini|defaultuser0)$"

  # Coba ambil dari USERPROFILE atau USERNAME yang di-set Windows
  WIN_USER="${WIN_USER:-}"

  if [ -z "$WIN_USER" ]; then
    # Ambil dari env variable USERPROFILE yang di-pass WSL dari Windows
    if [ -n "${USERPROFILE:-}" ]; then
      # Contoh: C:\Users\grimm04  →  ambil basename
      WIN_USER=$(basename "$(echo "$USERPROFILE" | sed 's|\\|/|g')")
    fi
  fi

  if [ -z "$WIN_USER" ]; then
    # Fallback: scan /mnt/c/Users/ dan filter folder sistem
    WIN_USER=$(ls /mnt/c/Users/ 2>/dev/null \
      | grep -v -E "$SYSTEM_FOLDERS" \
      | while read -r d; do
          # Hanya ambil folder yang punya subfolder AppData (tanda user nyata)
          [ -d "/mnt/c/Users/$d/AppData" ] && echo "$d"
        done \
      | head -1)
  fi

  if [ -z "$WIN_USER" ]; then
    echo -e "${YELLOW}Tidak bisa deteksi Windows username otomatis.${NC}"
  fi

  # Selalu tampilkan daftar pilihan agar user bisa konfirmasi / koreksi
  echo -e "  ${BLUE}Daftar user di C:\\Users\\:${NC}"
  ls /mnt/c/Users/ 2>/dev/null | grep -v -E "$SYSTEM_FOLDERS" | while read -r d; do
    marker=""
    [ "$d" = "$WIN_USER" ] && marker=" ${GREEN}← terdeteksi${NC}"
    echo -e "    - $d$marker"
  done
  echo ""

  if [ -n "$WIN_USER" ]; then
    echo -e "  Terdeteksi: ${YELLOW}$WIN_USER${NC}"
    echo -e "  Tekan Enter untuk konfirmasi, atau ketik nama lain jika salah:"
    read -r INPUT
    [ -n "$INPUT" ] && WIN_USER="$INPUT"
  else
    echo -e "  Ketik Windows username kamu (nama folder di C:\\Users\\):"
    read -r WIN_USER
  fi

  WIN_HOME="/mnt/c/Users/$WIN_USER"

  if [ ! -d "$WIN_HOME" ]; then
    echo -e "${RED}✗ Folder tidak ditemukan: $WIN_HOME${NC}"
    exit 1
  fi

  echo -e "  ${GREEN}✓ Windows user: $WIN_USER${NC}"
  echo -e "  ${GREEN}✓ Windows home: $WIN_HOME${NC}"
}

# -----------------------------------------------------------------------------
# Install kubectl di WSL
# -----------------------------------------------------------------------------
install_kubectl() {
  if command -v kubectl &>/dev/null; then
    echo -e "  ${GREEN}✓ kubectl sudah ada: $(kubectl version --client --short 2>/dev/null || kubectl version --client)${NC}"
    return
  fi

  echo -e "${BLUE}📦 Install kubectl di WSL...${NC}"
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
  chmod +x kubectl
  sudo mv kubectl /usr/local/bin/kubectl
  echo -e "  ${GREEN}✓ kubectl terinstall${NC}"
}

# -----------------------------------------------------------------------------
# Install helm di WSL
# -----------------------------------------------------------------------------
install_helm() {
  if command -v helm &>/dev/null; then
    echo -e "  ${GREEN}✓ helm sudah ada: $(helm version --short)${NC}"
    return
  fi

  echo -e "${BLUE}📦 Install helm di WSL...${NC}"
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
  echo -e "  ${GREEN}✓ helm terinstall${NC}"
}

# -----------------------------------------------------------------------------
# Copy & setup kubeconfig dari Windows ke WSL
# -----------------------------------------------------------------------------
setup_kubeconfig() {
  WSL_KUBE_DIR="$HOME/.kube"
  # WSL_KUBE_CONFIG sudah di-set sebagai global di atas

  echo ""
  echo -e "${BLUE}🔑 Setup kubeconfig...${NC}"

  # Cari kubeconfig Minikube di beberapa lokasi umum
  POSSIBLE_CONFIGS=(
    "$WIN_HOME/.kube/config"
    "$WIN_HOME/.minikube/config"
    "/mnt/c/ProgramData/minikube/config"
  )

  WIN_KUBE_CONFIG=""
  for path in "${POSSIBLE_CONFIGS[@]}"; do
    if [ -f "$path" ]; then
      WIN_KUBE_CONFIG="$path"
      echo -e "  ${GREEN}✓ kubeconfig ditemukan di: $path${NC}"
      break
    fi
  done

  # Jika tidak ketemu, coba cari manual
  if [ -z "$WIN_KUBE_CONFIG" ]; then
    echo -e "  ${YELLOW}⚠ kubeconfig tidak ditemukan di lokasi default.${NC}"
    echo ""
    echo -e "  Coba cari otomatis di C:\\Users\\$WIN_USER\\ ..."
    FOUND=$(find "$WIN_HOME" -name "config" -path "*/.kube/*" 2>/dev/null | head -1)

    if [ -n "$FOUND" ]; then
      echo -e "  ${GREEN}✓ Ditemukan: $FOUND${NC}"
      WIN_KUBE_CONFIG="$FOUND"
    else
      echo -e "  ${RED}✗ Tidak bisa menemukan kubeconfig otomatis.${NC}"
      echo ""
      echo -e "  Di Windows, buka PowerShell dan jalankan:"
      echo -e "    ${YELLOW}minikube start${NC}"
      echo -e "    ${YELLOW}echo \$env:USERPROFILE\\.kube\\config${NC}  (untuk cek lokasi config)"
      echo ""
      echo -e "  Lalu masukkan path lengkap kubeconfig kamu (format WSL, contoh:"
      echo -e "  /mnt/c/Users/grimm04/.kube/config):"
      read -r WIN_KUBE_CONFIG

      if [ ! -f "$WIN_KUBE_CONFIG" ]; then
        echo -e "  ${RED}✗ File tidak ditemukan: $WIN_KUBE_CONFIG${NC}"
        exit 1
      fi
    fi
  fi

  mkdir -p "$WSL_KUBE_DIR"
  cp "$WIN_KUBE_CONFIG" "$WSL_KUBE_CONFIG"
  chmod 600 "$WSL_KUBE_CONFIG"
  echo -e "  ${GREEN}✓ kubeconfig di-copy ke: $WSL_KUBE_CONFIG${NC}"

  # Fix server URL — ganti 127.0.0.1 dengan IP Windows host
  WIN_HOST_IP=$(detect_windows_host_ip)
  echo -e "  ${BLUE}ℹ Windows host IP dari WSL: $WIN_HOST_IP${NC}"

  if grep -q "server: https://127.0.0.1" "$WSL_KUBE_CONFIG"; then
    KUBE_PORT=$(grep "server: https://127.0.0.1" "$WSL_KUBE_CONFIG" | grep -oP ':\K[0-9]+')
    echo -e "  ${YELLOW}⚠ Server di kubeconfig masih 127.0.0.1:$KUBE_PORT — menggantinya...${NC}"
    sed -i "s|server: https://127.0.0.1:$KUBE_PORT|server: https://$WIN_HOST_IP:$KUBE_PORT|g" "$WSL_KUBE_CONFIG"
    echo -e "  ${GREEN}✓ Server URL diupdate ke: https://$WIN_HOST_IP:$KUBE_PORT${NC}"
  fi
}

# -----------------------------------------------------------------------------
# Deteksi IP Windows host dari dalam WSL (multi-method, robust)
# -----------------------------------------------------------------------------
detect_windows_host_ip() {
  local ip=""

  # Method 1: default gateway via ip route (paling reliable di WSL2)
  ip=$(ip route show default 2>/dev/null | awk '/default/ {print $3}' | head -1)
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && [[ "$ip" != "8.8.8.8" ]] && [[ "$ip" != "1.1.1.1" ]]; then
    echo "$ip"; return
  fi

  # Method 2: eth0 interface gateway
  ip=$(ip route show dev eth0 2>/dev/null | awk '/default/ {print $3}' | head -1)
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && [[ "$ip" != "8.8.8.8" ]] && [[ "$ip" != "1.1.1.1" ]]; then
    echo "$ip"; return
  fi

  # Method 3: host.docker.internal (Docker Desktop set ini di /etc/hosts)
  ip=$(getent hosts host.docker.internal 2>/dev/null | awk '{print $1}' | head -1)
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$ip"; return
  fi

  # Method 4: /etc/hosts entry untuk windows host
  ip=$(grep -i "host.docker.internal\|windows.host\|WSL" /etc/hosts 2>/dev/null | grep -v '^#' | awk '{print $1}' | head -1)
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$ip"; return
  fi

  # Method 5: resolv.conf tapi filter kalau DNS publik
  ip=$(grep nameserver /etc/resolv.conf | awk '{print $2}' | grep -v -E '^(8\.8\.|1\.1\.|9\.9\.)' | head -1)
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "$ip"; return
  fi

  # Gagal deteksi otomatis — minta input manual
  echo -e "\n  ${YELLOW}⚠ Tidak bisa deteksi IP Windows host otomatis.${NC}" >&2
  echo -e "  Jalankan perintah ini di PowerShell Windows untuk cari IP-nya:" >&2
  echo -e "    ${YELLOW}(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {" >&2
  echo -e "      \$_.InterfaceAlias -like '*WSL*' -or \$_.InterfaceAlias -like '*vEthernet*'" >&2
  echo -e "    }).IPAddress${NC}" >&2
  echo -e "\n  Masukkan IP Windows host kamu:" >&2
  read -r ip </dev/tty
  echo "$ip"
}

# -----------------------------------------------------------------------------
# Buat environment file yang bisa di-source
# -----------------------------------------------------------------------------
create_env_file() {
  # WIN_HOST_IP sudah di-set oleh setup_kubeconfig()
  if [ -z "$WIN_HOST_IP" ]; then
    WIN_HOST_IP=$(detect_windows_host_ip)
  fi

  cat > "$ENV_FILE" <<EOF
# =============================================================================
# Airflow K8s - WSL Environment
# Di-generate oleh scripts/setup-wsl.sh
# Source file ini di setiap sesi: source ~/airflow-k8s-env.sh
# Atau tambahkan ke ~/.bashrc: echo 'source ~/airflow-k8s-env.sh' >> ~/.bashrc
# =============================================================================

# Kubeconfig: gunakan config dari Windows Minikube
export KUBECONFIG="$HOME/.kube/config-minikube-windows"

# Windows host IP (untuk akses NodePort dari WSL)
export WIN_HOST_IP="$WIN_HOST_IP"

# Alias berguna
alias k='kubectl'
alias kgp='kubectl get pods -n airflow'
alias klogs='kubectl logs -n airflow'
alias airflow-ui='echo "http://\$WIN_HOST_IP:31151"'
alias flower-ui='echo "http://\$WIN_HOST_IP:31555"'

echo "✓ Airflow K8s environment loaded. WIN_HOST_IP=\$WIN_HOST_IP"
EOF

  echo ""
  echo -e "${GREEN}✓ Environment file dibuat: $ENV_FILE${NC}"
}

# -----------------------------------------------------------------------------
# Verifikasi koneksi
# -----------------------------------------------------------------------------
verify_connection() {
  echo ""
  echo -e "${BLUE}🔍 Verifikasi koneksi ke cluster...${NC}"

  export KUBECONFIG="$HOME/.kube/config-minikube-windows"

  if kubectl cluster-info &>/dev/null; then
    echo -e "  ${GREEN}✓ Berhasil terhubung ke cluster!${NC}"
    echo ""
    kubectl get nodes
  else
    echo -e "  ${RED}✗ Gagal terhubung ke cluster.${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo -e "  1. Pastikan Minikube sudah running di Windows:"
    echo -e "     PowerShell: minikube status"
    echo -e ""
    echo -e "  2. Pastikan Docker Desktop running dan Kubernetes enabled"
    echo -e ""
    echo -e "  3. Coba akses manual dari WSL:"
    echo -e "     kubectl --kubeconfig=$HOME/.kube/config-minikube-windows cluster-info"
    echo -e ""
    echo -e "  4. Jika masih gagal, lihat README.md section WSL Troubleshooting"
  fi
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
echo -e "${BLUE}Step 1: Deteksi Windows user${NC}"
detect_windows_user

echo ""
echo -e "${BLUE}Step 2: Install tools di WSL${NC}"
install_kubectl
install_helm

echo ""
echo -e "${BLUE}Step 3: Setup kubeconfig${NC}"
setup_kubeconfig

echo ""
echo -e "${BLUE}Step 4: Buat environment file${NC}"
create_env_file

verify_connection

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${GREEN}  Setup selesai!${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo -e "Langkah selanjutnya:"
echo -e ""
echo -e "  ${YELLOW}1. Load environment (wajib di setiap terminal baru):${NC}"
echo -e "     source ~/airflow-k8s-env.sh"
echo -e ""
echo -e "  ${YELLOW}2. Atau tambahkan permanen ke ~/.bashrc:${NC}"
echo -e "     echo 'source ~/airflow-k8s-env.sh' >> ~/.bashrc"
echo -e ""
echo -e "  ${YELLOW}3. Lalu deploy Airflow:${NC}"
echo -e "     ./scripts/deploy.sh"
echo ""