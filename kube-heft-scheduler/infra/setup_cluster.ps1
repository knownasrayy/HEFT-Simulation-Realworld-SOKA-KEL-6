# Versi PowerShell dari setup_cluster.sh (Windows + Docker Desktop).
# Jalankan dari root proyek: powershell -ExecutionPolicy Bypass -File .\infra\setup_cluster.ps1
$ErrorActionPreference = "Stop"
$kindBin = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Get-Command kind -ErrorAction SilentlyContinue)) { $env:Path = "$env:Path;$kindBin" }

function Invoke-Step([string]$cmd) {
    Write-Host "  > $cmd" -ForegroundColor DarkGray
    $ErrorActionPreference = "Continue"
    Invoke-Expression "$cmd 2>&1" | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Host $_.Exception.Message } else { Write-Host $_ }
    }
    $code = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($code -ne 0) { throw "Command failed ($code): $cmd" }
}

Write-Host "[1/5] Building heft-worker:latest Docker image..." -ForegroundColor Cyan
Invoke-Step "docker build -t heft-worker:latest ./worker"

Write-Host "[2/5] Creating Kind cluster 'heft-datacenter' (1 Datacenter, 2 Hosts)..." -ForegroundColor Cyan
$ErrorActionPreference = "Continue"
$clusters = (kind get clusters 2>&1 | Out-String)
$ErrorActionPreference = "Stop"
if ($clusters -match "(?m)^heft-datacenter$") {
    Write-Host "Cluster 'heft-datacenter' already exists. Skipping creation."
} else {
    Invoke-Step "kind create cluster --config ./infra/kind-config.yaml"
}

Write-Host "[3/5] Loading heft-worker:latest image into Kind nodes..." -ForegroundColor Cyan
Invoke-Step "kind load docker-image heft-worker:latest --name heft-datacenter"

Write-Host "[4/5] Deploying 4 heterogeneous VM pods and NodePort services..." -ForegroundColor Cyan
Invoke-Step "kubectl --context kind-heft-datacenter apply -f ./infra/k8s-workers.yaml"

Write-Host "[5/5] Waiting for all 4 VM pods to be Ready..." -ForegroundColor Cyan
Invoke-Step "kubectl --context kind-heft-datacenter wait --for=condition=Ready pod -l app=heft-worker --timeout=180s"

Write-Host "=== Topology Verification ===" -ForegroundColor Green
kubectl --context kind-heft-datacenter get nodes -L topology.host
kubectl --context kind-heft-datacenter get pods -o wide
