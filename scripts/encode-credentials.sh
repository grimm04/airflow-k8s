#!/usr/bin/env bash
# =============================================================================
# encode-credentials.sh
# =============================================================================
# Script interaktif untuk meng-encode GitHub credentials ke base64
# dan otomatis mengisi file secrets/git-credentials.yaml
#
# CARA PAKAI:
#   chmod +x scripts/encode-credentials.sh
#   ./scripts/encode-credentials.sh
# =============================================================================

set -e

# Warna output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SECRET_FILE="$PROJECT_DIR/secrets/git-credentials.yaml"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Airflow Git Credentials Encoder       ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Input GitHub username
echo -e "${YELLOW}Masukkan GitHub username kamu:${NC}"
read -r GITHUB_USERNAME

if [ -z "$GITHUB_USERNAME" ]; then
  echo -e "${RED}Error: Username tidak boleh kosong!${NC}"
  exit 1
fi

# Input GitHub PAT (hidden)
echo -e "${YELLOW}Masukkan GitHub Personal Access Token (input tersembunyi):${NC}"
read -rs GITHUB_PAT
echo ""

if [ -z "$GITHUB_PAT" ]; then
  echo -e "${RED}Error: Token tidak boleh kosong!${NC}"
  exit 1
fi

# Encode ke base64 (tanpa newline — flag berbeda antara Linux dan macOS)
if echo | base64 -w0 &>/dev/null 2>&1; then
  # Linux: gunakan -w0 untuk disable line wrapping
  ENCODED_USERNAME=$(echo -n "$GITHUB_USERNAME" | base64 -w0)
  ENCODED_PAT=$(echo -n "$GITHUB_PAT" | base64 -w0)
else
  # macOS: base64 tidak punya -w, tapi tidak wrap secara default
  ENCODED_USERNAME=$(echo -n "$GITHUB_USERNAME" | base64)
  ENCODED_PAT=$(echo -n "$GITHUB_PAT" | base64)
fi

echo ""
echo -e "${GREEN}✓ Encoding berhasil!${NC}"
echo ""
echo -e "  Username (base64): ${ENCODED_USERNAME}"
echo -e "  PAT      (base64): ${ENCODED_PAT:0:20}... (disembunyikan)"
echo ""

# Konfirmasi sebelum menulis ke file
echo -e "${YELLOW}Mau otomatis mengisi file secrets/git-credentials.yaml? (y/n):${NC}"
read -r CONFIRM

if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
  # Backup file lama
  if [ -f "$SECRET_FILE" ]; then
    cp "$SECRET_FILE" "${SECRET_FILE}.bak"
    echo -e "${BLUE}ℹ Backup disimpan ke: secrets/git-credentials.yaml.bak${NC}"
  fi

  # Ganti placeholder dengan nilai ter-encode
  # Menggunakan Python sebagai pengganti sed untuk menghindari konflik
  # karakter khusus dalam base64 (seperti +, /, =) dengan delimiter sed.
  python3 - <<PYEOF
import sys

with open("$SECRET_FILE", "r") as f:
    content = f.read()

content = content.replace("<base64_encoded_git_username>", "$ENCODED_USERNAME")
content = content.replace("<base64_encoded_git_pat>", "$ENCODED_PAT")

with open("$SECRET_FILE", "w") as f:
    f.write(content)
PYEOF

  echo -e "${GREEN}✓ File secrets/git-credentials.yaml berhasil diisi!${NC}"
  echo ""
  echo -e "${RED}⚠ PERINGATAN: Jangan commit file ini ke Git!${NC}"
  echo -e "  Pastikan 'secrets/git-credentials.yaml' ada di .gitignore"
else
  echo ""
  echo -e "${BLUE}Nilai base64 untuk diisi manual ke secrets/git-credentials.yaml:${NC}"
  echo ""
  echo "  GIT_SYNC_USERNAME:  $ENCODED_USERNAME"
  echo "  GIT_SYNC_PASSWORD:  $ENCODED_PAT"
  echo "  GITSYNC_USERNAME:   $ENCODED_USERNAME"
  echo "  GITSYNC_PASSWORD:   $ENCODED_PAT"
fi

echo ""
echo -e "${BLUE}Langkah selanjutnya:${NC}"
echo "  1. kubectl apply -f secrets/git-credentials.yaml -n airflow"
echo "  2. Edit config/values.yaml - isi 'repo' dengan URL GitHub kamu"
echo "  3. Jalankan: ./scripts/deploy.sh"
echo ""