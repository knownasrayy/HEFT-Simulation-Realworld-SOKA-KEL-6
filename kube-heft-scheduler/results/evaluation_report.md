# Laporan Evaluasi KubeHEFT: Algoritma HEFT vs Round-Robin pada Klaster Kubernetes Heterogen

> Referensi: Topcuoglu, Hariri & Wu (2002), *Performance-Effective and Low-Complexity Task Scheduling for Heterogeneous Computing*, IEEE TPDS 13(3).

## 1. Verifikasi Topologi Cloud (1 Datacenter, 2 Host, 4 VM)

```text
kubectl get nodes -L topology.host
NAME                            STATUS   ROLES           AGE    VERSION   TOPOLOGY.HOST
heft-datacenter-control-plane   Ready    control-plane   2m7s   v1.32.2   
heft-datacenter-worker          Ready    <none>          114s   v1.32.2   host-1
heft-datacenter-worker2         Ready    <none>          114s   v1.32.2   host-2
kubectl get pods -o wide
NAME          READY   STATUS    RESTARTS   AGE    IP           NODE                      NOMINATED NODE   READINESS GATES
vm-worker-1   1/1     Running   0          104s   10.244.2.2   heft-datacenter-worker    <none>           <none>
vm-worker-2   1/1     Running   0          104s   10.244.2.3   heft-datacenter-worker    <none>           <none>
vm-worker-3   1/1     Running   0          104s   10.244.1.2   heft-datacenter-worker2   <none>           <none>
vm-worker-4   1/1     Running   0          104s   10.244.1.3   heft-datacenter-worker2   <none>           <none>
```

| VM ID | Host (label) | Kind Node | Limit CPU | Status |
| :--- | :--- | :--- | :---: | :---: |
| `vm-worker-1` | `host-1` | `heft-datacenter-worker` | `1000m` | ready |
| `vm-worker-2` | `host-1` | `heft-datacenter-worker` | `500m` | ready |
| `vm-worker-3` | `host-2` | `heft-datacenter-worker2` | `750m` | ready |
| `vm-worker-4` | `host-2` | `heft-datacenter-worker2` | `250m` | ready |

## 2. Verifikasi Heterogenitas Perangkat Keras (Kalibrasi CFS Quota)

| VM ID | Limit CPU | Rasio Target | Iterasi SHA-256/detik | Rasio Terukur |
| :--- | :---: | :---: | ---: | :---: |
| `vm-worker-1` | `1000m` | 1.00x | 2,764,185 | **1.000x** |
| `vm-worker-2` | `500m` | 0.50x | 2,049,077 | **0.741x** |
| `vm-worker-3` | `750m` | 0.75x | 1,965,960 | **0.711x** |
| `vm-worker-4` | `250m` | 0.25x | 874,619 | **0.316x** |

## 3. Fase 1 HEFT — Upward Rank & Fase 2 — Pemilihan VM (EFT + Insertion)

* Rata-rata faktor komunikasi antar-VM berbeda ($\overline{c}$ multiplier): `1.3333`
* **Urutan prioritas:** `T1 -> T4 -> T2 -> T6 -> T5 -> T3 -> T9 -> T8 -> T7 -> T10`
* **Critical path (bobot min):** `T1 -> T2 -> T9 -> T10` — $CP_{MIN}$ = 4.00 s

| Task | $\overline{w_i}$ | $rank_u$ | VM HEFT | EST teori | EFT teori | AST aktual | AFT aktual |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: |
| **T1** | 2.500 | 11.399 | `vm-worker-1` | 0.00 | 1.20 | 0.00 | 1.54 |
| **T4** | 1.875 | 7.892 | `vm-worker-1` | 1.20 | 2.10 | 1.54 | 2.68 |
| **T2** | 2.083 | 7.699 | `vm-worker-1` | 2.10 | 3.10 | 2.68 | 3.42 |
| **T6** | 2.292 | 6.810 | `vm-worker-3` | 2.40 | 3.87 | 3.02 | 4.67 |
| **T5** | 1.458 | 6.808 | `vm-worker-2` | 1.90 | 3.30 | 2.26 | 3.58 |
| **T3** | 1.667 | 6.493 | `vm-worker-1` | 3.10 | 3.90 | 3.42 | 4.14 |
| **T9** | 2.708 | 4.550 | `vm-worker-1` | 3.90 | 5.20 | 4.21 | 5.57 |
| **T8** | 1.875 | 3.584 | `vm-worker-3` | 4.45 | 5.65 | 4.80 | 5.96 |
| **T7** | 1.250 | 3.359 | `vm-worker-1` | 5.20 | 5.80 | 5.57 | 6.13 |
| **T10** | 1.042 | 1.042 | `vm-worker-1` | 6.40 | 6.90 | 6.72 | 7.09 |

**Tabel EFT kandidat per VM (dasar pemilihan VM):**

| Task | EFT `vm-worker-1` | EFT `vm-worker-2` | EFT `vm-worker-3` | EFT `vm-worker-4` | Terpilih |
| :--- | :---: | :---: | :---: | :---: | :--- |
| T1 | **1.20** | 2.40 | 1.60 | 4.80 | `vm-worker-1` |
| T4 | **2.10** | 3.50 | 3.15 | 5.55 | `vm-worker-1` |
| T2 | **3.10** | 4.10 | 3.88 | 6.55 | `vm-worker-1` |
| T6 | 4.20 | 4.20 | **3.87** | 6.80 | `vm-worker-3` |
| T5 | 3.80 | **3.30** | 4.80 | 5.05 | `vm-worker-2` |
| T3 | **3.90** | 4.90 | 4.94 | 5.30 | `vm-worker-1` |
| T9 | **5.20** | 6.50 | 6.03 | 9.50 | `vm-worker-1` |
| T8 | 6.10 | 6.72 | **5.65** | 8.17 | `vm-worker-3` |
| T7 | **5.80** | 6.20 | 6.45 | 7.95 | `vm-worker-1` |
| T10 | **6.90** | 7.60 | 7.67 | 9.00 | `vm-worker-1` |

## 4. Penempatan Tugas: HEFT vs Round-Robin

| Task | VM HEFT | VM Round-Robin |
| :--- | :--- | :--- |
| T1 | `vm-worker-1` | `vm-worker-1` |
| T2 | `vm-worker-1` | `vm-worker-2` |
| T3 | `vm-worker-1` | `vm-worker-3` |
| T4 | `vm-worker-1` | `vm-worker-4` |
| T5 | `vm-worker-2` | `vm-worker-1` |
| T6 | `vm-worker-3` | `vm-worker-2` |
| T7 | `vm-worker-1` | `vm-worker-3` |
| T8 | `vm-worker-3` | `vm-worker-4` |
| T9 | `vm-worker-1` | `vm-worker-1` |
| T10 | `vm-worker-1` | `vm-worker-2` |

## 5. Transfer Data Antar-VM Riil (Run Representatif)

| Skema | Edge | Sumber → Tujuan | Link | Payload | Transfer riil (s) | Biaya model (s) |
| :--- | :--- | :--- | :--- | ---: | :---: | :---: |
| HEFT | T1->T5 | `vm-worker-1` → `vm-worker-2` | intra-host | 700 KB | 0.0345 | 0.70 |
| HEFT | T1->T6 | `vm-worker-1` → `vm-worker-3` | inter-host | 800 KB | 0.0842 | 1.20 |
| HEFT | T4->T8 | `vm-worker-1` → `vm-worker-3` | inter-host | 1300 KB | 0.1058 | 1.95 |
| HEFT | T2->T8 | `vm-worker-1` → `vm-worker-3` | inter-host | 900 KB | 0.1293 | 1.35 |
| HEFT | T5->T9 | `vm-worker-2` → `vm-worker-1` | intra-host | 600 KB | 0.0562 | 0.60 |
| HEFT | T8->T10 | `vm-worker-3` → `vm-worker-1` | inter-host | 500 KB | 0.0758 | 0.75 |
| RR | T1->T2 | `vm-worker-1` → `vm-worker-2` | intra-host | 900 KB | 0.0160 | 0.90 |
| RR | T1->T3 | `vm-worker-1` → `vm-worker-3` | inter-host | 600 KB | 0.1808 | 0.90 |
| RR | T1->T4 | `vm-worker-1` → `vm-worker-4` | inter-host | 500 KB | 0.1680 | 0.75 |
| RR | T1->T6 | `vm-worker-1` → `vm-worker-2` | intra-host | 800 KB | 0.2095 | 0.80 |
| RR | T2->T8 | `vm-worker-2` → `vm-worker-4` | inter-host | 900 KB | 0.4089 | 1.35 |
| RR | T2->T9 | `vm-worker-2` → `vm-worker-1` | intra-host | 800 KB | 0.3875 | 0.80 |
| RR | T7->T10 | `vm-worker-3` → `vm-worker-2` | inter-host | 800 KB | 0.0792 | 1.20 |
| RR | T4->T9 | `vm-worker-4` → `vm-worker-1` | inter-host | 1100 KB | 0.1891 | 1.65 |
| RR | T6->T8 | `vm-worker-2` → `vm-worker-4` | inter-host | 700 KB | 0.0199 | 1.05 |
| RR | T9->T10 | `vm-worker-1` → `vm-worker-2` | intra-host | 600 KB | 0.0082 | 0.60 |
| RR | T8->T10 | `vm-worker-4` → `vm-worker-2` | inter-host | 500 KB | 0.0842 | 0.75 |

## 6. Hasil Pengujian Berulang (5 run)

| Run | Makespan HEFT (s) | Makespan RR (s) | Reduksi |
| :---: | :---: | :---: | :---: |
| 1 ⭐ | 7.087 | 14.179 | 50.02% |
| 2 | 7.385 | 17.004 | 56.57% |
| 3 | 6.529 | 14.774 | 55.81% |
| 4 | 6.901 | 14.959 | 53.86% |
| 5 | 7.571 | 15.535 | 51.27% |

⭐ = run representatif (median HEFT) yang digambar pada Gantt Chart.

## 7. Perbandingan Metrik Performa Utama

| Skema Penjadwalan | Makespan $C_{max}$ (s) | SLR | Speedup |
| :--- | :---: | :---: | :---: |
| HEFT (Teoritis) | 6.900 | 1.725 | 1.304x |
| Round-Robin (Teoritis) | 12.700 | 3.175 | 0.709x |
| **HEFT (Aktual Kubernetes, mean ± std)** | **7.094 ± 0.409** | **1.774 ± 0.102** | **1.272 ± 0.074** |
| Round-Robin (Aktual Kubernetes, mean ± std) | 15.290 ± 1.073 | 3.823 ± 0.268 | 0.591 ± 0.040 |

* $SLR = C_{max} / \sum_{n_i \in CP_{MIN}} \min_{p_j} w_{i,j}$, dengan $CP_{MIN}$ = 4.00 s
* $Speedup = \min_{p_j} \sum_{n_i} w_{i,j} / C_{max}$, dengan waktu sekuensial minimum = 9.00 s

> **Kesimpulan:** HEFT menghasilkan makespan lebih rendah daripada Round-Robin pada **5/5** run, dengan reduksi makespan rata-rata **53.60%** pada klaster Kubernetes heterogen nyata (1 Datacenter, 2 Host, 4 VM).

## 8. Artefak

* `results/gantt_comparison.png` — Gantt: HEFT teoritis, HEFT aktual, RR aktual
* `results/makespan_runs.png` — Makespan tiap run
* `results/execution_log.json` — Data mentah seluruh eksekusi
