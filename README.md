# KubeHEFT — Real-World Heterogeneous Cloud Task Scheduler (SOKA Kelompok 6)

> **Tugas Mata Kuliah:** Strategi Optimasi Komputasi Awan (SOKA) — Semester 5  
> **Kelompok:** 6  
> **Algoritma Inti:** Heterogeneous Earliest Finish Time (HEFT) — Topcuoglu, Hariri, & Wu (IEEE TPDS 2002)  
> **Infrastruktur Target:** Kubernetes in Docker (Kind) pada Linux / WSL2 / Windows  
> **Topologi Fisik & Logis:** 1 Datacenter (Cluster), 2 Host (Worker Nodes), 4 VM (Heterogeneous Pods)

---

## 📌 Ringkasan Hasil Eksperimen

Pengujian riil dijalankan sebanyak **5 kali pengulangan (run)** di atas klaster Kubernetes heterogen nyata dengan membandingkan **HEFT** terhadap **Topological Round-Robin (RR)**:

| Metrik Evaluasi | HEFT (Teoritis) | HEFT (Aktual Cloud, mean ± std) | Round-Robin (Aktual Cloud, mean ± std) | Peningkatan / Reduksi |
| :--- | :---: | :---: | :---: | :---: |
| **Makespan ($C_{\max}$)** | `6.900` s | **`7.367 ± 0.314` s** | `13.437 ± 0.529` s | **45.18% Lebih Cepat** |
| **Schedule Length Ratio (SLR)** | `1.725` | **`1.842 ± 0.079`** | `3.359 ± 0.132` | **Lebih Efisien Menuju CP** |
| **Speedup** | `1.304x` | **`1.224 ± 0.054x`** | `0.671 ± 0.026x` | **Parallel Speedup Nyata** |

> **Konsistensi:** HEFT menghasilkan makespan yang lebih rendah secara konsisten pada **5 dari 5 run pengujian** (100% win rate).

---

## 📊 Visualisasi Gantt Chart & Makespan

### 1. Gantt Chart 3 Panel (Teori vs Real Cloud HEFT vs Real Cloud Round-Robin)
![Gantt Comparison](kube-heft-scheduler/results/gantt_comparison.png)

### 2. Bar Chart Makespan Setiap Pengulangan (5 Runs)
![Makespan Runs](kube-heft-scheduler/results/makespan_runs.png)

---

## 🏛️ Pemetaan Arsitektur & Topologi

```text
+-----------------------------------------------------------------------------------+
|                        MASTER ORCHESTRATOR (Host / WSL2)                          |
|  +------------------+   +---------------------+   +----------------------------+  |
|  | DAG & Matrix     |-->| HEFT & Round-Robin  |-->| Async HTTP Task Dispatcher |  |
|  | Loader (JSON)    |   | Scheduling Engine   |   | (httpx + asyncio)          |  |
|  +------------------+   +---------------------+   +-------------+--------------+  |
+-----------------------------------------------------------------|-----------------+
                                                                  |
                         HTTP REST API (Port 30081 - 30084)       |
                                                                  v
+-----------------------------------------------------------------------------------+
|                     DATACENTER: KIND CLUSTER (heft-datacenter)                    |
|                                                                                   |
|  +-------------------------------------+   +-----------------------------------+  |
|  |           HOST 1 (Node 1)           |   |          HOST 2 (Node 2)          |  |
|  |  label: topology.host = host-1      |   |  label: topology.host = host-2    |  |
|  |                                     |   |                                   |  |
|  |  +---------------+ +-------------+  |   |  +-------------+ +-------------+  |  |
|  |  |  vm-worker-1  | | vm-worker-2 |  |   |  | vm-worker-3 | | vm-worker-4 |  |  |
|  |  |  CPU: 1000m   | | CPU: 500m   |  |   |  | CPU: 750m   | | CPU: 250m   |  |  |
|  |  |  RAM: 512Mi   | | RAM: 256Mi  |  |   |  | RAM: 512Mi  | | RAM: 256Mi  |  |  |
|  |  |  Port: 30081  | | Port: 30082 |  |   |  | Port: 30083 | | Port: 30084 |  |  |
|  |  +---------------+ +-------------+  |   |  +-------------+ +-------------+  |  |
|  +-------------------------------------+   +-----------------------------------+  |
+-----------------------------------------------------------------------------------+
```

### Spesifikasi Heterogenitas Pod (VM)
- **`vm-worker-1`** (Host 1): `limits.cpu: 1000m` (1.0 Core), Kecepatan Relatif: **1.00x** (Tercepat)
- **`vm-worker-2`** (Host 1): `limits.cpu: 500m` (0.5 Core), Kecepatan Relatif: **0.50x** (Sedang)
- **`vm-worker-3`** (Host 2): `limits.cpu: 750m` (0.75 Core), Kecepatan Relatif: **0.75x** (Menengah)
- **`vm-worker-4`** (Host 2): `limits.cpu: 250m` (0.25 Core), Kecepatan Relatif: **0.25x** (Paling Lambat)

---

## 📁 Struktur Direktori Repositori

```text
HEFT-Simulation-Realworld-SOKA-KEL-6/
├── README.md                                                        # Dokumentasi utama repositori
├── Implementasi Real-World Algoritma HEFT pada Klaster... .md      # PRD v2.0 Dokumen Acuan
├── kube-heft-scheduler/
│   ├── PRD.md                                                      # Salinan PRD di root proyek
│   ├── README.md                                                   # Panduan teknis penggunaan
│   ├── requirements.txt                                            # Dependensi Python master
│   ├── infra/
│   │   ├── kind-config.yaml                                        # Definisi 1 Cluster, 2 Worker Node
│   │   ├── k8s-workers.yaml                                        # Manifest 4 Pod Heterogen + NodePort
│   │   ├── setup_cluster.sh / .ps1                                 # Skrip build & deploy otomatis
│   │   └── teardown_cluster.sh / .ps1                              # Skrip penghapusan klaster
│   ├── worker/
│   │   ├── Dockerfile                                              # Container image python:3.11-slim
│   │   ├── requirements.txt                                        # Dependensi FastAPI worker
│   │   └── main.py                                                 # CPU-bound hashing & data transfer API
│   ├── master/
│   │   ├── dag_sample.json                                         # Dataset 10-node DAG (Topcuoglu 2002)
│   │   ├── heft_algorithm.py                                       # Mesin HEFT (Upward Rank & EFT)
│   │   ├── baseline_scheduler.py                                   # Mesin Round-Robin baseline
│   │   ├── dispatcher.py                                           # Async HTTP task dispatcher & transfer riil
│   │   ├── visualize.py                                            # Pembuat Gantt Chart & laporan metrik
│   │   └── run_experiment.py                                       # Skrip otomatis benchmark berulang
│   └── results/
│       ├── gantt_comparison.png                                    # Grafik Gantt Chart 3 panel
│       ├── makespan_runs.png                                       # Grafik perbandingan 5 runs
│       ├── evaluation_report.md                                    # Laporan evaluasi lengkap
│       └── execution_log.json                                      # Log data mentah hasil pengujian
```

---

## 🚀 Panduan Menjalankan Eksperimen

### Prasyarat
- Docker Desktop (sedang berjalan)
- `kind` (Kubernetes in Docker)
- `kubectl`
- Python 3.11+

### Windows (PowerShell)
```powershell
# 1. Masuk ke direktori scheduler
cd kube-heft-scheduler

# 2. Bangun image worker & deploy klaster Kind
powershell -ExecutionPolicy Bypass -File .\infra\setup_cluster.ps1

# 3. Buat virtual environment & install dependensi
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 4. Jalankan eksperimen (misal 5 run pengujian)
.\.venv\Scripts\python.exe -m master.run_experiment --runs 5
```

### Linux / WSL2 (Bash)
```bash
# 1. Masuk ke direktori scheduler
cd kube-heft-scheduler

# 2. Setup klaster
chmod +x infra/*.sh
./infra/setup_cluster.sh

# 3. Setup Python venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Jalankan eksperimen
python3 -m master.run_experiment --runs 5
```

### Membersihkan Klaster (Teardown)
- **Windows:** `powershell -ExecutionPolicy Bypass -File .\infra\teardown_cluster.ps1`
- **Linux:** `./infra/teardown_cluster.sh`

---

## 👥 Tim Pengembang (Kelompok 6)
- **Mata Kuliah:** Strategi Optimasi Komputasi Awan (SOKA)
- **Program Studi:** Informatika / Ilmu Komputer - Semester 5
