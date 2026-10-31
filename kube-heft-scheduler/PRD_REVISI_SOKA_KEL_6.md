# Product Requirements Document (PRD) v3.0: Post-Demo Revision & Tri-Dimensional Evaluation Framework

| Atribut Dokumen | Detail Spesifikasi |
| :--- | :--- |
| **Nama Proyek** | KubeHEFT — Real-World Heterogeneous Cloud Task Scheduler |
| **Versi Dokumen** | **3.0 (Post-Demo Revision — Tri-Dimensional Benchmark & Multi-Metric Evaluation)** |
| **Mata Kuliah** | Strategi Optimasi Komputasi Awan (SOKA) — Semester 5 |
| **Kelompok** | 6 (Kelas C) |
| **Anggota Kelompok**| Rayhan Agnan Kusuma (5027241102), Ahmad Idza Anafin (5027241017), Andi Naufal Zaki (5027241059), Zidny Ilman Nafi'an (5027221072) |
| **Dosen Pengampu** | Henning Titi Ciptaningtyas, S.Kom, M.Kom. |
| **Tanggal Revisi** | 31 Oktober 2026 |

---

## 1. Latar Belakang & Mandat Revisi Evaluasi Dosen

Berdasarkan sesi evaluasi dan demonstrasi langsung di hadapan dosen pengampu (**Bu Henning Titi Ciptaningtyas, S.Kom, M.Kom.**) pada tanggal 31 Oktober 2026, implementasi prototipe *real-world* KubeHEFT di atas klaster Kubernetes dinilai telah berhasil membuktikan disparitas performa antara algoritma HEFT dan Round-Robin. 

Namun, terdapat **3 catatan revisi akademik krusial** yang harus diintegrasikan ke dalam sistem dan laporan akhir:
1. **Komparasi Tiga Dimensi (*Tri-Dimensional Benchmark*):**  
   Pengujian tidak boleh hanya membandingkan teori vs real-world, melainkan harus menyandingkan tiga dimensi secara utuh:
   $$\text{Dimensi 1: Matematis Teoritis} \longleftrightarrow \text{Dimensi 2: Simulator (CloudSim)} \longleftrightarrow \text{Dimensi 3: Real-World (Kubernetes)}$$
   Serta menghitung persentase deviasi (*diferensiasi/gap*) antara kondisi ideal simulator dengan lingkungan nyata klaster cloud.
2. **Ekspansi Metrik Evaluasi Komprehensif (Multi-Metric Framework):**  
   Evaluasi performa tidak boleh terbatas pada *Makespan* ($C_{\max}$) saja, melainkan wajib mencakup minimal 4–5 metrik kinerja komputasi awan:
   - *Schedule Length Ratio* ($SLR$)
   - *Speedup* ($S$)
   - *Scheduling / Parallel Efficiency* ($\eta$)
   - *Average Processor / CPU Utilization* ($U_{\text{avg}}$)
   - *Communication / Latency Overhead* ($O_{\text{comm}}$)
3. **Penyusunan Laporan Akhir Akademik Lengkap (*Final Comprehensive Report*):**  
   Menyusun dokumen laporan komprehensif berstandar ilmiah siap kumpul yang mencakup latar belakang, kajian teori, arsitektur topologi, formulasi matematis, hasil pengujian 3 dimensi, analisis diferensiasi, hingga daftar pustaka formal IEEE.

---

## 2. Tujuan Sistem (System Objectives)

1. **FR-REV-01 (Data Integration):** Mengintegrasikan baseline data pengujian 10-node DAG 4 VM dari simulator CloudSim ke dalam *Master Evaluation Engine* tanpa perlu merusak struktur simulator yang telah dibuat sebelumnya.
2. **FR-REV-02 (Multi-Metric Engine):** Mengembangkan modul kalkulasi metrik analitis matematis yang mengekstrak $C_{\max}$, $SLR$, $Speedup$, $\eta$, $U_{\text{avg}}$, dan $O_{\text{comm}}$ dari hasil log eksekusi riil dan teoritis.
3. **FR-REV-03 (Gap Differentiation Model):** Menghitung secara matematis persentase selisih diferensiasi performa:
   $$\Delta_{\text{Sim-Theo}} = \frac{M_{\text{sim}} - M_{\text{theo}}}{M_{\text{theo}}} \times 100\%$$
   $$\Delta_{\text{Real-Sim}} = \frac{M_{\text{real}} - M_{\text{sim}}}{M_{\text{sim}}} \times 100\%$$
   $$\Delta_{\text{Real-Theo}} = \frac{M_{\text{real}} - M_{\text{theo}}}{M_{\text{theo}}} \times 100\%$$
   Serta membedah secara ilmiah faktor penyebab fisik di lingkungan container Kubernetes (Linux cgroups throttling latency, OS context-switch jitter, veth network bridge serialization).
4. **FR-REV-04 (Tri-Dimensional Visualization):** Menghasilkan artefak grafik visual baru:
   - `results/three_dimensional_comparison.png`: Grafik komparasi batang multi-metrik 3 dimensi (Teori vs CloudSim vs K8s).
   - `results/differentiation_gap_analysis.png`: Grafik analisis persentase gap diferensiasi.
   - Pembaruan `results/gantt_comparison.png` dan `results/makespan_runs.png`.
5. **FR-REV-05 (Academic Report Generation):** Meng-generate dokumen laporan akhir akademik lengkap `results/LAPORAN_AKHIR_SOKA_KELOMPOK_6.md` dan `results/evaluation_report.md` yang siap diunggah ke Google Drive / folder pengumpulan SOKA Kelas C.

---

## 3. Spesifikasi Teknis & Pemetaan Arsitektur 3 Dimensi

### 3.1. Topologi Standar Uji (10 Tasks, 4 VMs, 2 Hosts, 1 Datacenter)

| Komponen | Spesifikasi Logis & Fisik | Karakteristik Perangkat Keras |
| :--- | :--- | :--- |
| **Datacenter** | 1 Datacenter virtual (`heft-datacenter`) | Docker Bridge Network terisolasi |
| **Host 1** | Worker Node 1 (`heft-datacenter-worker`) | Label: `topology.host = host-1` |
| **Host 2** | Worker Node 2 (`heft-datacenter-worker2`) | Label: `topology.host = host-2` |
| **VM 1 ($p_1$)** | Pod `vm-worker-1` (di Host 1) | `limits.cpu: 1000m` (1.0 Core) — Kecepatan: **1.00x** (Port 30081) |
| **VM 2 ($p_2$)** | Pod `vm-worker-2` (di Host 1) | `limits.cpu: 500m` (0.5 Core) — Kecepatan: **0.50x** (Port 30082) |
| **VM 3 ($p_3$)** | Pod `vm-worker-3` (di Host 2) | `limits.cpu: 750m` (0.75 Core) — Kecepatan: **0.75x** (Port 30083) |
| **VM 4 ($p_4$)** | Pod `vm-worker-4` (di Host 2) | `limits.cpu: 250m` (0.25 Core) — Kecepatan: **0.25x** (Port 30084) |

### 3.2. Formulasi Metrik Evaluasi Tambahan

1. **Makespan ($C_{\max}$):**
   $$C_{\max} = \max_{n_i \in V} AFT(n_i)$$
2. **Schedule Length Ratio ($SLR$):**
   $$SLR = \frac{C_{\max}}{\sum_{n_i \in CP_{\min}} \min_{p_j \in P} \{w_{i,j}\}}$$
   Di mana $CP_{\min} = \{T_1, T_2, T_9, T_{10}\}$ dengan total komputasi minimum = $1.20 + 1.00 + 1.30 + 0.50 = 4.00\text{ s}$.
3. **Speedup ($S$):**
   $$S = \frac{\min_{p_j \in P} \sum_{n_i \in V} w_{i,j}}{C_{\max}} = \frac{9.00\text{ s}}{C_{\max}}$$
4. **Scheduling / Parallel Efficiency ($\eta$):**
   $$\eta = \frac{S}{q} \times 100\% = \frac{S}{4} \times 100\%$$
   Mengukur efisiensi pemanfaatan $q=4$ prosesor secara paralel relatif terhadap percepatan ideal linear.
5. **Average CPU Utilization ($U_{\text{avg}}$):**
   $$U_{\text{avg}} = \frac{\sum_{i=1}^{v} w_{i, \text{assigned}(i)}}{q \times C_{\max}} \times 100\%$$
   Mengukur persentase waktu sibuk rata-rata seluruh prosesor selama masa workflow berlangsung.
6. **Communication Overhead ($O_{\text{comm}}$):**
   $$O_{\text{comm}} = \sum_{(n_m, n_i) \in E, p_{\text{src}} \neq p_{\text{dst}}} c_{m,i}$$
   Total akumulasi durasi transfer payload data yang melintasi jaringan antar-VM.

---

## 4. Rencana Kerja Eksekusi & Deliverables

1. **Modul Integrasi Data Simulator (`master/simulator_data.py`):** Berisi data deterministik CloudSim 7.0.1 untuk graf 10-node DAG HEFT dan Round-Robin.
2. **Modul Visualisasi Multi-Metrik (`master/visualize.py`):** Diperbarui untuk mengkalkulasi 6 metrik, merender grafik 3 dimensi, grafik gap analisis, dan laporan markdown komprehensif.
3. **Eksekusi Generator Analisis:** Menghasilkan seluruh file artefak di folder `results/`.
4. **Sinkronisasi Dokumentasi (`README.md`):** Memperbarui ringkasan komparasi 3 dimensi pada dokumentasi GitHub repositori.
5. **Git Commit & Push:** Mengunggah seluruh hasil revisi ke repositori `HEFT-Simulation-Realworld-SOKA-KEL-6`.
