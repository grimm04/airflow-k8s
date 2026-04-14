# =============================================================================
# Encode-Credentials.ps1
# =============================================================================
# Script untuk meng-encode GitHub credentials ke base64 dan mengisi
# file secrets\git-credentials.yaml secara otomatis.
#
# CARA PAKAI:
#   .\scripts\Encode-Credentials.ps1
#
# Jika muncul error "execution policy", jalankan dulu di PowerShell (Admin):
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# =============================================================================

$ErrorActionPreference = "Stop"

# Path relatif dari root project
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir  = Split-Path -Parent $ScriptDir
$SecretFile  = Join-Path $ProjectDir "secrets\git-credentials.yaml"
$ExampleFile = Join-Path $ProjectDir "secrets\git-credentials.yaml.example"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Airflow Git Credentials Encoder       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# -----------------------------------------------------------------------------
# Input credentials
# -----------------------------------------------------------------------------
$GitHubUsername = Read-Host "Masukkan GitHub username kamu"
if ([string]::IsNullOrWhiteSpace($GitHubUsername)) {
    Write-Host "Error: Username tidak boleh kosong!" -ForegroundColor Red
    exit 1
}

$GitHubPAT = Read-Host "Masukkan GitHub Personal Access Token" -AsSecureString
$PlainPAT  = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($GitHubPAT)
)
if ([string]::IsNullOrWhiteSpace($PlainPAT)) {
    Write-Host "Error: Token tidak boleh kosong!" -ForegroundColor Red
    exit 1
}

# -----------------------------------------------------------------------------
# Encode ke base64 (tanpa newline / line wrapping)
# -----------------------------------------------------------------------------
$EncodedUsername = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($GitHubUsername))
$EncodedPAT      = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($PlainPAT))

Write-Host ""
Write-Host "✓ Encoding berhasil!" -ForegroundColor Green
Write-Host "  Username (base64) : $EncodedUsername"
Write-Host "  PAT      (base64) : $($EncodedPAT.Substring(0, [Math]::Min(20, $EncodedPAT.Length)))... (disembunyikan)"
Write-Host ""

# -----------------------------------------------------------------------------
# Pastikan file secret ada (copy dari example jika belum)
# -----------------------------------------------------------------------------
if (-not (Test-Path $SecretFile)) {
    if (Test-Path $ExampleFile) {
        Copy-Item $ExampleFile $SecretFile
        Write-Host "ℹ File secret dibuat dari template example." -ForegroundColor Cyan
    } else {
        Write-Host "Error: File secrets\git-credentials.yaml tidak ditemukan!" -ForegroundColor Red
        Write-Host "       Pastikan kamu menjalankan script dari root folder project." -ForegroundColor Red
        exit 1
    }
}

# -----------------------------------------------------------------------------
# Isi placeholder di secret file
# -----------------------------------------------------------------------------
$Confirm = Read-Host "Mau otomatis mengisi file secrets\git-credentials.yaml? (y/n)"
if ($Confirm -match '^[Yy]$') {
    # Backup file lama
    $BackupFile = "$SecretFile.bak"
    Copy-Item $SecretFile $BackupFile -Force
    Write-Host "ℹ Backup disimpan ke: secrets\git-credentials.yaml.bak" -ForegroundColor Cyan

    # Ganti placeholder — pakai [string]::Replace agar aman dari karakter khusus
    $Content = Get-Content $SecretFile -Raw
    $Content = $Content.Replace("<base64_encoded_git_username>", $EncodedUsername)
    $Content = $Content.Replace("<base64_encoded_git_pat>", $EncodedPAT)
    Set-Content $SecretFile -Value $Content -NoNewline

    Write-Host "✓ File secrets\git-credentials.yaml berhasil diisi!" -ForegroundColor Green
    Write-Host ""
    Write-Host "⚠ PERINGATAN: Jangan commit file ini ke Git!" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "Nilai base64 untuk diisi manual ke secrets\git-credentials.yaml:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  GIT_SYNC_USERNAME:  $EncodedUsername"
    Write-Host "  GIT_SYNC_PASSWORD:  $EncodedPAT"
    Write-Host "  GITSYNC_USERNAME:   $EncodedUsername"
    Write-Host "  GITSYNC_PASSWORD:   $EncodedPAT"
}

Write-Host ""
Write-Host "Langkah selanjutnya:" -ForegroundColor Cyan
Write-Host "  1. Edit config\values.yaml — isi 'repo' dengan URL GitHub kamu"
Write-Host "  2. Jalankan: .\scripts\Deploy.ps1"
Write-Host ""
