$ErrorActionPreference = "Stop"
$kindBin = Join-Path $env:USERPROFILE ".local\bin"
if (-not (Get-Command kind -ErrorAction SilentlyContinue)) { $env:Path = "$env:Path;$kindBin" }
kind delete cluster --name heft-datacenter
