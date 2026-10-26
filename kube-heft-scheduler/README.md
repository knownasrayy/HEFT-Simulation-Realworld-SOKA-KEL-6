# KubeHEFT: Real-World Heuristic Task Scheduler pada Klaster Cloud Heterogen

[![Kubernetes](https://img.shields.io/badge/Kubernetes-Kind%20v1.32.2-blue?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

> **Tugas Besar:** Strategi Optimasi Komputasi Awan (SOKA) — Semester 5 (Kelompok 6)  
> **Algoritma Inti:** Heterogeneous Earliest Finish Time (HEFT) — Topcuoglu et al. (IEEE TPDS 2002)  
> **Infrastruktur Target:** 1 Datacenter (Kind Cluster), 2 Host (Worker Nodes), 4 VM (Heterogeneous Pods)

---

## 📌 Ringkasan Hasil Pengujian (5 Runs di Kubernetes)

| Metrik Evaluasi | HEFT (Teoritis) | HEFT (Aktual Cloud, mean ± std) | Round-Robin (Aktual Cloud, mean ± std) | Peningkatan / Reduksi |
| :--- | :---: | :---: | :---: | :---: |
| **Makespan ($C_{\max}$)** | `6.900` s | **`7.367 ± 0.314` s** | `13.437 ± 0.529` s | **45.18% Lebih Cepat** |
| **Schedule Length Ratio (SLR)** | `1.725` | **`1.842 ± 0.079`** | `3.359 ± 0.132` | **Efisien Mendekati CP** |
| **Speedup** | `1.304x` | **`1.224 ± 0.054x`** | `0.671 ± 0.026x` | **Parallel Speedup Nyata** |

**Konsistensi:** HEFT menghasilkan makespan lebih cepat pada **5 dari 5 kali pengujian (100% win rate)**.

---

## 📊 Visualisasi Hasil

### 1. Gantt Chart 3 Panel (Teori vs Real Cloud HEFT vs Real Cloud Round-Robin)
![Gantt Comparison](results/gantt_comparison.png)

### 2. Grafik Makespan Per Run (5 Pengujian)
![Makespan Runs](results/makespan_runs.png)

---

## 🏛️ Infrastruktur Klaster Cloud

### 1. Pemetaan Arsitektur
- **Datacenter:** 1 Klaster Kind (`heft-datacenter`) menggunakan Docker bridge network terisolasi.
- **Host 1:** Worker Node 1 (`heft-datacenter-worker`) berlabel `topology.host=host-1`.
- **Host 2:** Worker Node 2 (`heft-datacenter-worker2`) berlabel `topology.host=host-2`.
- **VM 1 s.d. VM 4:** Pod heterogen dibatasi oleh cgroups CFS Quota kernel Linux:
  - `vm-worker-1` (Host 1): `1000m` CPU (1.0 Core), 512 MiB RAM — Kecepatan: **1.00x** (Port 30081)
  - `vm-worker-2` (Host 1): `500m` CPU (0.5 Core), 256 MiB RAM — Kecepatan: **0.50x** (Port 30082)
  - `vm-worker-3` (Host 2): `750m` CPU (0.75 Core), 512 MiB RAM — Kecepatan: **0.75x** (Port 30083)
  - `vm-worker-4` (Host 2): `250m` CPU (0.25 Core), 256 MiB RAM — Kecepatan: **0.25x** (Port 30084)

### 2. Verifikasi Empiris Heterogenitas Hardware (Kalibrasi SHA-256)
- `vm-worker-1`: `1,879,404` iterasi/detik (**`1.000x`**)
- `vm-worker-2`: `1,074,174` iterasi/detik (**`0.572x`**)
- `vm-worker-3`: `1,780,466` iterasi/detik (**`0.947x`**)
- `vm-worker-4`: `480,020` iterasi/detik (**`0.255x`**)

### 3. Model Biaya Komunikasi Jaringan Sadar Topologi
- **Intra-VM ($p_a = p_b$):** Biaya = `0.0 detik`
- **Intra-Host ($p_a \neq p_b$, Host sama):** Biaya = $1.0 \times c_{\text{base}}$
- **Inter-Host (Host beda):** Biaya = $1.5 \times c_{\text{base}}$ (penalti latensi lintas-host)
- **Transfer Riil (FR-02):** Worker mengirim payload data HTTP ke `/receive` milik Pod tujuan via DNS Service internal (`http://vm-worker-X-svc:8000`).

---

## 🚀 Panduan Menjalankan

### Prasyarat
- Docker Desktop aktif (minimal 4 CPU, 4 GB RAM)
- `kind` dan `kubectl` terpasang
- Python 3.11+

### 1. Setup Klaster Cloud (Kind)
- **Windows (PowerShell):**
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\infra\setup_cluster.ps1
  ```
- **Linux / WSL2 (Bash):**
  ```bash
  chmod +x infra/*.sh
  ./infra/setup_cluster.sh
  ```

*Verifikasi topologi Pod dan Node:*
```powershell
kubectl --context kind-heft-datacenter get nodes -L topology.host
kubectl --context kind-heft-datacenter get pods -o wide
```

### 2. Setup Virtual Environment Python
- **Windows:**
  ```powershell
  py -3.12 -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  ```
- **Linux / WSL2:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

### 3. Eksekusi Eksperimen Benchmark
Pilih mode eksekusi yang diinginkan:

- **Mode Pengujian Penuh (Rekomendasi - 5 Runs):**
  ```powershell
  python -m master.run_experiment --runs 5
  ```
- **Mode Demo Cepat (1 Run Saja - Durasi ~20 Detik):**
  ```powershell
  python -m master.run_experiment --runs 1
  ```
- **Mode Kalkulasi Matematis Saja (Tanpa Klaster):**
  ```powershell
  python -m master.heft_algorithm
  ```

*Opsi Tambahan:* `--runs <int>` (jumlah run), `--cooldown <float>` (jeda detik antar-run), `--context <str>` (konteks kubectl).

---

## 🧹 Panduan Pembersihan Total Klaster (Teardown & Cleanup)

Setelah selesai melakukan pengujian atau demo, lakukan pembersihan untuk membebaskan RAM dan CPU:

1. **Hapus Klaster Kind:**
   - **Windows:** `powershell -ExecutionPolicy Bypass -File .\infra\teardown_cluster.ps1` (atau `kind delete cluster --name heft-datacenter`)
   - **Linux:** `./infra/teardown_cluster.sh`
2. **Verifikasi Container & Port Bersih:**
   - `docker ps` (pastikan tidak ada container `heft-datacenter-*`)
   - `netstat -ano | findstr "30081 30082 30083 30084"` (pastikan port sudah bebas)
3. **Nonaktifkan Environment Python:**
   - Jalankan `deactivate` pada terminal.
4. **(Opsional) Hapus Docker Image:**
   - Jalankan `docker rmi heft-worker:latest` untuk menghemat ruang disk SSD.
5. **(Opsional) Tutup Docker Desktop:**
   - Klik kanan ikon Docker Desktop di tray $\to$ **Quit Docker Desktop**.

> 🛡️ **Catatan:** Seluruh file laporan dan grafik di folder `results/` tetap aman tersimpan. Menghapus klaster tidak akan menghapus data hasil eksperimen.

---

## 📁 Struktur Berkas

```text
kube-heft-scheduler/
├── PRD.md                        # Blueprint PRD v2.0
├── README.md                     # Panduan penggunaan ini
├── requirements.txt              # Dependensi master (httpx, matplotlib, numpy, pydantic)
├── infra/
│   ├── kind-config.yaml          # Konfigurasi 1 Cluster, 2 Worker Node, port mapping 30081-30084
│   ├── k8s-workers.yaml          # Manifest 4 Pod Heterogen + 4 NodePort Services
│   ├── setup_cluster.ps1 / .sh   # Script otomasi build image & provisioning klaster
│   └── teardown_cluster.ps1 / .sh# Script pembersihan klaster
├── worker/
│   ├── Dockerfile                # Container image python:3.11-slim
│   ├── requirements.txt          # fastapi, uvicorn, pydantic, httpx
│   └── main.py                   # Worker REST API (/health, /calibrate, /execute, /transfer, /receive)
├── master/
│   ├── __init__.py
│   ├── dag_sample.json           # Graf 10-node DAG (Topcuoglu 2002)
│   ├── heft_algorithm.py         # Upward Rank ($rank_u$) & Insertion-based EFT
│   ├── baseline_scheduler.py     # Topological Round-Robin scheduler
│   ├── dispatcher.py             # Async HTTP client & real data transfer
│   ├── visualize.py              # Generator Gantt Chart & laporan Markdown
│   └── run_experiment.py         # Entrypoint utama runner pengujian
└── results/
    ├── evaluation_report.md      # Laporan metrik komparasi lengkap
    ├── execution_log.json        # Log mentah data eksekusi riil 5 runs
    ├── gantt_comparison.png      # Gambar Gantt Chart 3 panel
    └── makespan_runs.png         # Bar chart makespan tiap run
```
