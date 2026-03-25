# ─────────────────────────────────────────────────────────────
# Start-EmbeddingInstance.ps1
# Launches the Ollama embedding instance on T400 (GPU 1)
# Port 11435 — nomic-embed-text
#
# The main Ollama service (port 11434, RTX 5070 Ti) starts
# automatically on boot — no need to manage it here.
#
# Usage: Right-click → "Run with PowerShell"
#        OR run from terminal: .\Start-EmbeddingInstance.ps1
# ─────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Ollama Embedding Instance Launcher" -ForegroundColor Cyan
Write-Host "  T400 (GPU 1) → Port 11435" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# ── Check main Ollama service is already running ─────────────
Write-Host "[*] Checking main Ollama service (port 11434)..." -ForegroundColor Yellow
try {
    Invoke-RestMethod http://localhost:11434/api/tags -ErrorAction Stop | Out-Null
    Write-Host "    [11434] Main LLM instance  ✅ Already running" -ForegroundColor Green
} catch {
    Write-Host "    [11434] Main LLM instance  ⚠️  Not detected — it may still be starting up." -ForegroundColor Yellow
    Write-Host "            Proceeding anyway..." -ForegroundColor Yellow
}
Write-Host ""

# ── Kill any existing instance on port 11435 ─────────────────
Write-Host "[*] Clearing any existing process on port 11435..." -ForegroundColor Yellow
$existing = Get-NetTCPConnection -LocalPort 11435 -ErrorAction SilentlyContinue
if ($existing) {
    $pid11435 = $existing.OwningProcess | Select-Object -First 1
    Stop-Process -Id $pid11435 -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    Write-Host "    Cleared." -ForegroundColor Green
} else {
    Write-Host "    Nothing to clear." -ForegroundColor Green
}
Write-Host ""

# ── Start T400 embedding instance on port 11435 ──────────────
Write-Host "[*] Starting embedding instance on T400 (GPU 1) → port 11435..." -ForegroundColor Yellow

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "`$env:CUDA_VISIBLE_DEVICES='1'; `$env:OLLAMA_HOST='127.0.0.1:11435'; ollama serve"
)

Write-Host "    Instance launched in new window." -ForegroundColor Green
Write-Host ""

# ── Wait and verify ───────────────────────────────────────────
Write-Host "[*] Waiting for instance to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

$retries = 0
$maxRetries = 6
$ready = $false

while ($retries -lt $maxRetries -and -not $ready) {
    try {
        Invoke-RestMethod http://localhost:11435/api/tags -ErrorAction Stop | Out-Null
        $ready = $true
    } catch {
        $retries++
        Write-Host "    Still starting... ($retries/$maxRetries)" -ForegroundColor Gray
        Start-Sleep -Seconds 3
    }
}

Write-Host ""
if ($ready) {
    Write-Host "    [11435] Embedding instance ✅ Online" -ForegroundColor Green
} else {
    Write-Host "    [11435] Embedding instance ❌ Not responding — check the new window for errors" -ForegroundColor Red
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Ready. Startup sequence:" -ForegroundColor Cyan
Write-Host "  1. Activate RAG environment:" -ForegroundColor Cyan
Write-Host "     cd C:\RAG" -ForegroundColor White
Write-Host "     .\rag-env\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "  2. Run your pipeline:" -ForegroundColor Cyan
Write-Host "     python scripts\ingest.py" -ForegroundColor White
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit this window..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
