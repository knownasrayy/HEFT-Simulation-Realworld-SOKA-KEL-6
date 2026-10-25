# KubeHEFT — Real-World Heterogeneous Cloud Task Scheduler

Implementasi nyata algoritma **HEFT** (Topcuoglu, Hariri & Wu, IEEE TPDS 2002) pada klaster
Kubernetes (Kind) heterogen: **1 Datacenter, 2 Host, 4 VM**, dibandingkan dengan baseline
**Topological Round-Robin**.

| Komponen | Implementasi |
| :--- | :--- |
| Datacenter | Kind cluster `heft-datacenter` |
| Host 1 / Host 2 | Worker node `heft-datacenter-worker` (`topology.host=host-1`) / `heft-datacenter-worker2` (`host-2`) |
| VM 1–4 | Pod `vm-worker-1..4` dengan `limits.cpu` 1000m / 500m / 750m / 250m |
| Master | Python (Windows/WSL) — HEFT engine, RR baseline, async dispatcher |

## Struktur

```text
kube-heft-scheduler/
├── infra/      kind-config.yaml, k8s-workers.yaml, setup/teardown (.sh & .ps1)
├── worker/     FastAPI worker: /health, /calibrate, /execute, /transfer, /receive
├── master/     dag_sample.json, heft_algorithm.py, baseline_scheduler.py,
│               dispatcher.py, visualize.py, run_experiment.py
└── results/    gantt_comparison.png, makespan_runs.png, execution_log.json, evaluation_report.md
```

## Cara Menjalankan

**Prasyarat:** Docker Desktop, `kind`, `kubectl`, Python 3.11+.

### Windows (PowerShell)
```powershell
cd kube-heft-scheduler
powershell -ExecutionPolicy Bypass -File .\infra\setup_cluster.ps1
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m master.run_experiment --runs 5
```

### Linux / WSL2
```bash
cd kube-heft-scheduler
chmod +x infra/*.sh && ./infra/setup_cluster.sh
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python3 -m master.run_experiment --runs 5
```

Hanya menghitung jadwal teoritis (tanpa klaster): `python -m master.heft_algorithm`

Membersihkan klaster: `./infra/teardown_cluster.sh` atau `.\infra\teardown_cluster.ps1`

## Catatan Desain (penyempurnaan dari PRD)

1. **Transfer data antar-VM riil (FR-02):** saat tugas induk selesai, VM sumber mengirim payload
   (`data_kb`) via HTTP ke VM tujuan melalui DNS Service internal klaster (`vm-worker-X-svc:8000`).
   Latensi topologi diinjeksi sehingga total komunikasi = `max(transfer_riil, biaya_model)`
   (intra-host 1.0x, inter-host 1.5x).
2. **Rata-rata biaya komunikasi `c̄`** dihitung atas pasangan VM *berbeda* (sesuai paper).
3. **Kalibrasi seluruh 4 VM** untuk membuktikan heterogenitas CFS quota secara empiris.
4. **Pengujian berulang** (`--runs N`, urutan HEFT/RR diselang-seling) dengan mean ± std.
5. **Bukti topologi** (`kubectl get nodes/pods -o wide`) otomatis masuk ke laporan.
6. Bobot DAG: struktur 10-node/15-edge dari paper, biaya komputasi disesuaikan dengan rasio
   kecepatan VM (`w_ij = base / speed_factor`).
