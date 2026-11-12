$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "=== 1. Menyiapkan JDK 21 & CloudSim 7.0.1 ===" -ForegroundColor Cyan
$javacPath = (Get-ChildItem -Path "$env:USERPROFILE\.antigravity-ide\extensions\redhat.java*" -Recurse -Filter "javac.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)
$javaPath  = (Get-ChildItem -Path "$env:USERPROFILE\.antigravity-ide\extensions\redhat.java*" -Recurse -Filter "java.exe"  -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName)

if (-not $javacPath) { $javacPath = (Get-Command javac -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source) }
if (-not $javaPath)  { $javaPath  = (Get-Command java  -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source) }

if (-not $javacPath -or -not $javaPath) {
    throw "javac / java tidak ditemukan. Pastikan JDK 21 tersedia."
}

$cloudsimJar = "$env:USERPROFILE\.m2\repository\org\cloudbus\cloudsim\cloudsim\7.0.1\cloudsim-7.0.1.jar"
if (-not (Test-Path $cloudsimJar)) {
    throw "CloudSim JAR tidak ditemukan di $cloudsimJar"
}

$binDir = Join-Path $Root "cloudsim\bin"
$resDir = Join-Path $Root "results"
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
New-Item -ItemType Directory -Path $resDir -Force | Out-Null

$sources = Get-ChildItem -Path (Join-Path $Root "cloudsim\src") -Filter "*.java" | ForEach-Object { $_.FullName }
& $javacPath -d $binDir -cp $cloudsimJar $sources
if ($LASTEXITCODE -ne 0) { throw "Kompilasi Java CloudSim gagal!" }
Write-Host "Kompilasi Java berhasil." -ForegroundColor Green

Write-Host "`n=== 2. Menjalankan Simulasi CloudSim 7.0.1 ===" -ForegroundColor Cyan
$cp = "$binDir;$cloudsimJar"
$dagPath = Join-Path $Root "..\kube-heft-scheduler\master\dag_sample.json"

& $javaPath -cp $cp ComparisonCloudSimRunner "dag10-flat"    $dagPath (Join-Path $resDir "cloudsim_10task_flat.json")
& $javaPath -cp $cp ComparisonCloudSimRunner "dag10-topo"    $dagPath (Join-Path $resDir "cloudsim_10task_topo.json")
& $javaPath -cp $cp ComparisonCloudSimRunner "dag10-rr"      $dagPath (Join-Path $resDir "cloudsim_10task_rr.json")
& $javaPath -cp $cp ComparisonCloudSimRunner "synthetic-100" $dagPath (Join-Path $resDir "cloudsim_synthetic_100.json")

Write-Host "`n=== 3. Menjalankan Komparasi Terpadu (Teori vs CloudSim vs Realworld K8s) ===" -ForegroundColor Cyan
$venvKube = Join-Path $Root "..\kube-heft-scheduler\.venv\Scripts\python.exe"
$venvRoot = Join-Path $Root "..\.venv\Scripts\python.exe"
if (Test-Path $venvKube) {
    $pythonExe = $venvKube
} elseif (Test-Path $venvRoot) {
    $pythonExe = $venvRoot
} else {
    $pythonExe = "python"
}

& $pythonExe (Join-Path $Root "compare_heft.py") `
    --dag $dagPath `
    --cloudsim-flat (Join-Path $resDir "cloudsim_10task_flat.json") `
    --cloudsim-topo (Join-Path $resDir "cloudsim_10task_topo.json") `
    --cloudsim-rr (Join-Path $resDir "cloudsim_10task_rr.json") `
    --cloudsim-synth (Join-Path $resDir "cloudsim_synthetic_100.json") `
    --realworld-log (Join-Path $Root "..\kube-heft-scheduler\results\execution_log.json") `
    --out-dir $resDir

Write-Host "`nSelesai! Cek folder results\ untuk laporan, JSON, dan grafik." -ForegroundColor Green
