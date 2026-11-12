# HEFT Comparison: Teori vs CloudSim 7.0.1 vs Real-World Kubernetes

Modul ini mengeksekusi komparasi *apple-to-apple* antara **Teori HEFT (Topcuoglu et al., 2002)**, **HEFT Simulation Biasa (CloudSim 7.0.1 Java)**, dan **HEFT Simulation Real-World (Kubernetes Kind)** menggunakan dataset DAG 10-task yang sama ([`kube-heft-scheduler/master/dag_sample.json`](../kube-heft-scheduler/master/dag_sample.json)).

## Struktur Modul

- `cloudsim/src/` — Runner Java **CloudSim 7.0.1** (diadaptasi dari proyek `heft-simulation-master` Kelompok 6) dengan 4 mode:
  1. `dag10-flat`: Model jaringan flat (`100 MB/s`, `(P-1)/P` — sesuai implementasi asli `HEFTScheduler.java`).
  2. `dag10-topo`: Model jaringan topology-aware (`1.0x` intra-host, `1.5x` inter-host, rata-rata pasangan `v1 != v2`).
  3. `dag10-rr`: Baseline Round-Robin di atas CloudSim 7.0.1.
  4. `synthetic-100`: Uji skalabilitas 100 Task / 10 VM / 2 Datacenter / 8 Host beserta metrik energi & runtime penjadwalan.
- `compare_heft.py` — Mesin evaluasi Python yang menggabungkan Teori HEFT, hasil nyata CloudSim 7.0.1 (`results/cloudsim_*.json`), dan hasil nyata Kubernetes Kind ([`execution_log.json`](../kube-heft-scheduler/results/execution_log.json)).
- `run_comparison.ps1` — Skrip eksekusi sekali jalan.
- `README_LAPORAN.md` — Laporan akademis lengkap hasil komparasi 3 dimensi beserta visualisasi.

## Cara Menjalankan

Jalankan dari folder `comparison/` di PowerShell (membutuhkan JDK 21, `cloudsim-7.0.1.jar`, dan Python 3.11+ dengan `matplotlib` & `numpy`):

```powershell
.\run_comparison.ps1
```

## Output (`results/`)

- `results/comparison_report.md` — Ringkasan otomatis metrik & jadwal per-task.
- `results/comparison_summary.json` — Seluruh data numerik terstruktur.
- `results/comparison_metrics.png` — Grafik perbandingan 6-panel multi-metrik HEFT & Round-Robin.
- `results/gantt_3way.png` — Gantt chart 3 dimensi (Teori vs CloudSim `WorkflowBroker` vs Real-World Kubernetes).
- `results/gap_and_rank_analysis.png` — Analisis perbedaan rumus `rank_u` dan gap makespan ($\Delta\%$).
- `results/cloudsim_*.json` — Log mentah simulasi CloudSim 7.0.1.
