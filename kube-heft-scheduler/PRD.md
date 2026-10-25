# Product Requirements Document (PRD): Implementasi Real-World Algoritma HEFT pada Klaster Komputasi Awan Heterogen

| Atribut Dokumen | Detail Spesifikasi |
| :--- | :--- |
| **Nama Proyek** | KubeHEFT — Real-World Heterogeneous Cloud Task Scheduler |
| **Versi Dokumen** | 2.0 (Full End-to-End Implementation Blueprint) |
| **Referensi Utama** | H. Topcuoglu, S. Hariri, and Min-You Wu, *"Performance-Effective and Low-Complexity Task Scheduling for Heterogeneous Computing"*, IEEE Transactions on Parallel and Distributed Systems, Vol. 13, No. 3, pp. 260–274, Mar. 2002. |
| **Platform Cloud** | Kubernetes in Docker (Kind) di atas Linux / WSL2 |
| **Topologi Infrastruktur** | 1 Datacenter (Cluster), 2 Host (Worker Nodes), 4 VM (Heterogeneous Pods) |
| **Stack Teknologi** | Python 3.11+, FastAPI, Uvicorn, HTTPX, Asyncio, Matplotlib, Docker, Kubernetes |

---

## 1. Tujuan & Ruang Lingkup Sistem

Sistem ini mengimplementasikan algoritma heuristik **Heterogeneous Earliest Finish Time (HEFT)** pada lingkungan komputasi awan nyata (*real-world cloud environment*) menggunakan orkestrasi Kubernetes. Sistem mengeksekusi beban kerja komputasi CPU riil (*CPU-bound SHA-256 hashing*) dan mensimulasikan transfer payload jaringan antar-VM pada 4 unit komputasi (Pod) yang dibatasi kuota perangkat kerasnya menggunakan *Linux Control Groups (cgroups)*.

### 1.1. Target Capaian (Deliverables)
1. **Infrastruktur Cloud Terverifikasi:** 1 Klaster Kubernetes (`heft-datacenter`) dengan 2 Worker Node (`host-1`, `host-2`) dan 4 Pod Worker (`vm-worker-1` s.d. `vm-worker-4`) yang memiliki limitasi vCPU berbeda.
2. **Mesin Penjadwalan HEFT & Baseline:** Implementasi matematis *Upward Rank* ($rank_u$), *Insertion-Based Earliest Finish Time* ($EFT$), serta algoritma pembanding *Topological Round-Robin* ($RR$).
3. **Real-Time Async Dispatcher:** Orkestrator asinkron yang mengkalibrasi kecepatan perangkat keras riil, mengirim instruksi kerja ke ke-4 VM sesuai dependensi graf tugas (*Directed Acyclic Graph* / DAG), dan mencatat waktu eksekusi aktual.
4. **Laporan & Visualisasi Otomatis:** Pembuatan otomatis grafik *Gantt Chart* (`results/gantt_comparison.png`) serta laporan evaluasi metrik performa (`results/evaluation_report.md`) yang mencakup *Makespan*, *Speedup*, dan *Schedule Length Ratio (SLR)*.

---

## 2. Arsitektur Sistem & Pemetaan Topologi

### 2.1. Diagram Arsitektur Logis

```text
+-----------------------------------------------------------------------------------+
|                        MASTER ORCHESTRATOR (WSL2 / Host)                          |
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

### 2.2. Tabel Spesifikasi Heterogenitas VM

Keempat VM menjalankan *container image* yang identik, namun dipaksa memiliki kecepatan komputasi berbeda melalui *Kubernetes CFS Quota (`resources.limits.cpu`)*:

| ID VM | Nama Pod Kubernetes | Penempatan Host | Alokasi vCPU (`limits.cpu`) | Alokasi RAM | Rasio Kecepatan Komputasi Relatif | Port Ekspos (NodePort) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **$p_1$** | `vm-worker-1` | `host-1` | `1000m` (1.00 Core) | `512Mi` | **1.00x** (Paling Cepat) | `30081` |
| **$p_2$** | `vm-worker-2` | `host-1` | `500m` (0.50 Core) | `256Mi` | **0.50x** (Sedang) | `30082` |
| **$p_3$** | `vm-worker-3` | `host-2` | `750m` (0.75 Core) | `512Mi` | **0.75x** (Menengah) | `30083` |
| **$p_4$** | `vm-worker-4` | `host-2` | `250m` (0.25 Core) | `256Mi` | **0.25x** (Paling Lambat) | `30084` |

### 2.3. Model Biaya Komunikasi Jaringan Antar-VM

Biaya pengiriman data antar-tugas dependen $(n_m \to n_i)$ dengan bobot dasar $c_{\text{base}}(m, i)$ mengikuti aturan kesadaran topologi (*topology-aware communication cost*):
1. **Intra-VM ($p_a = p_b$):** $c_{m,i}(p_a, p_b) = 0.0\text{ detik}$ (data sudah tersedia di memori lokal VM yang sama).
2. **Intra-Host ($p_a \neq p_b$, tetapi $\text{host}(p_a) = \text{host}(p_b)$):** $c_{m,i}(p_a, p_b) = 1.0 \times c_{\text{base}}(m, i)$.
3. **Inter-Host ($\text{host}(p_a) \neq \text{host}(p_b)$):** $c_{m,i}(p_a, p_b) = 1.5 \times c_{\text{base}}(m, i)$ (penalti latensi lintas-host).

---

## 3. Spesifikasi Matematis Algoritma HEFT

### 3.1. Fase 1: Task Prioritizing (Perhitungan Upward Rank)
Rata-rata biaya komputasi tugas $n_i$ di seluruh $q = 4$ VM adalah:
$$\overline{w_i} = \frac{1}{q} \sum_{j=1}^{q} w_{i,j}$$

Nilai *Upward Rank* $rank_u(n_i)$ dihitung secara rekursif mulai dari *exit task* ($n_{\text{exit}}$) menuju *entry task*:
$$rank_u(n_{\text{exit}}) = \overline{w_{\text{exit}}}$$
$$rank_u(n_i) = \overline{w_i} + \max_{n_k \in succ(n_i)} \left( \overline{c_{i,k}} + rank_u(n_k) \right)$$

Daftar prioritas penjadwalan diperoleh dengan mengurutkan seluruh tugas secara menurun (*descending*) berdasarkan nilai $rank_u(n_i)$.

### 3.2. Fase 2: Processor Selection (Earliest Finish Time & Insertion Policy)
Untuk setiap tugas $n_i$ dalam daftar prioritas, uji penempatannya pada setiap VM $p_j \in P$:
1. Hitung waktu siap data (*data ready time*) dari seluruh pendahulu $pred(n_i)$:
   $$\text{ready\_time}(n_i, p_j) = \begin{cases} 0, & \text{jika } pred(n_i) = \emptyset \\ \max_{n_m \in pred(n_i)} \left( AFT(n_m) + c_{m,i}(p_{\text{sched}(m)}, p_j) \right), & \text{lainnya} \end{cases}$$
2. **Kebijakan Penyisipan (Insertion-Based Policy):**
   Telusuri celah waktu kosong (*idle slots*) $[t_{\text{start}}, t_{\text{end}}]$ di antara tugas-tugas yang sudah dijadwalkan pada VM $p_j$ (mulai dari $t = 0$ hingga $\infty$). Celah dinyatakan valid apabila:
   $$\max\left(t_{\text{start}}, \text{ready\_time}(n_i, p_j)\right) + w_{i,j} \le t_{\text{end}}$$
3. Pada celah valid paling awal yang ditemukan, tetapkan:
   $$EST(n_i, p_j) = \max\left(t_{\text{start}}, \text{ready\_time}(n_i, p_j)\right)$$
   $$EFT(n_i, p_j) = EST(n_i, p_j) + w_{i,j}$$
4. Pilih VM $p_{\text{best}} = \arg\min_{p_j \in P} EFT(n_i, p_j)$, lalu simpan jadwal $AST(n_i) = EST(n_i, p_{\text{best}})$ dan $AFT(n_i) = EFT(n_i, p_{\text{best}})$.

---

## 4. Struktur Direktori Proyek

```text
kube-heft-scheduler/
├── PRD.md                        # Dokumen spesifikasi ini
├── README.md                     # Dokumentasi penggunaan
├── requirements.txt              # Dependensi Python untuk Master Node
├── infra/
│   ├── kind-config.yaml          # Konfigurasi 1 Cluster, 2 Worker Node, & Port Mapping
│   ├── k8s-workers.yaml          # Manifest 4 Pod Heterogen & 4 NodePort Services
│   ├── setup_cluster.sh          # Script otomatis pembuatan klaster & deployment
│   └── teardown_cluster.sh       # Script pembersihan klaster Kind
├── worker/
│   ├── Dockerfile                # Container image untuk Worker VM
│   ├── requirements.txt          # fastapi, uvicorn, pydantic
│   └── main.py                   # Aplikasi FastAPI pengeksekusi beban CPU riil
├── master/
│   ├── __init__.py
│   ├── dag_sample.json           # Dataset 10-node DAG (Topcuoglu 2002)
│   ├── heft_algorithm.py         # Mesin kalkulasi Upward Rank, EST, EFT, Insertion Policy
│   ├── baseline_scheduler.py     # Mesin penjadwalan pembanding (Topological Round-Robin)
│   ├── dispatcher.py             # Async HTTP orchestrator untuk eksekusi di Kubernetes
│   ├── visualize.py              # Pembuat Gantt Chart (PNG) & laporan Markdown
│   └── run_experiment.py         # Entrypoint utama menjalankan seluruh eksperimen
└── results/
    ├── gantt_comparison.png      # Output grafik perbandingan jadwal
    ├── execution_log.json        # Data mentah hasil eksekusi riil
    └── evaluation_report.md      # Tabel metrik siap pakai untuk laporan kuliah
```

---

## 5. Spesifikasi Kode & Konfigurasi Lengkap

### 5.1. Root `requirements.txt`
```text
httpx>=0.27.0
matplotlib>=3.8.0
numpy>=1.26.0
pydantic>=2.6.0
```

### 5.2. Konfigurasi Klaster Kind (`infra/kind-config.yaml`)
```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: heft-datacenter
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30081
        hostPort: 30081
        protocol: TCP
      - containerPort: 30082
        hostPort: 30082
        protocol: TCP
      - containerPort: 30083
        hostPort: 30083
        protocol: TCP
      - containerPort: 30084
        hostPort: 30084
        protocol: TCP
  - role: worker
    labels:
      topology.host: host-1
  - role: worker
    labels:
      topology.host: host-2
```

### 5.3. Manifest Pod & Service Heterogen (`infra/k8s-workers.yaml`)
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: vm-worker-1
  labels:
    app: heft-worker
    vm-id: vm-worker-1
    host-id: host-1
spec:
  nodeSelector:
    topology.host: host-1
  containers:
    - name: worker
      image: heft-worker:latest
      imagePullPolicy: Never
      env:
        - name: VM_ID
          value: "vm-worker-1"
        - name: HOST_ID
          value: "host-1"
        - name: CPU_LIMIT
          value: "1000m"
      ports:
        - containerPort: 8000
      resources:
        requests:
          cpu: "250m"
          memory: "128Mi"
        limits:
          cpu: "1000m"
          memory: "512Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: vm-worker-1-svc
spec:
  type: NodePort
  selector:
    vm-id: vm-worker-1
  ports:
    - port: 8000
      targetPort: 8000
      nodePort: 30081
---
apiVersion: v1
kind: Pod
metadata:
  name: vm-worker-2
  labels:
    app: heft-worker
    vm-id: vm-worker-2
    host-id: host-1
spec:
  nodeSelector:
    topology.host: host-1
  containers:
    - name: worker
      image: heft-worker:latest
      imagePullPolicy: Never
      env:
        - name: VM_ID
          value: "vm-worker-2"
        - name: HOST_ID
          value: "host-1"
        - name: CPU_LIMIT
          value: "500m"
      ports:
        - containerPort: 8000
      resources:
        requests:
          cpu: "250m"
          memory: "128Mi"
        limits:
          cpu: "500m"
          memory: "256Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: vm-worker-2-svc
spec:
  type: NodePort
  selector:
    vm-id: vm-worker-2
  ports:
    - port: 8000
      targetPort: 8000
      nodePort: 30082
---
apiVersion: v1
kind: Pod
metadata:
  name: vm-worker-3
  labels:
    app: heft-worker
    vm-id: vm-worker-3
    host-id: host-2
spec:
  nodeSelector:
    topology.host: host-2
  containers:
    - name: worker
      image: heft-worker:latest
      imagePullPolicy: Never
      env:
        - name: VM_ID
          value: "vm-worker-3"
        - name: HOST_ID
          value: "host-2"
        - name: CPU_LIMIT
          value: "750m"
      ports:
        - containerPort: 8000
      resources:
        requests:
          cpu: "250m"
          memory: "128Mi"
        limits:
          cpu: "750m"
          memory: "512Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: vm-worker-3-svc
spec:
  type: NodePort
  selector:
    vm-id: vm-worker-3
  ports:
    - port: 8000
      targetPort: 8000
      nodePort: 30083
---
apiVersion: v1
kind: Pod
metadata:
  name: vm-worker-4
  labels:
    app: heft-worker
    vm-id: vm-worker-4
    host-id: host-2
spec:
  nodeSelector:
    topology.host: host-2
  containers:
    - name: worker
      image: heft-worker:latest
      imagePullPolicy: Never
      env:
        - name: VM_ID
          value: "vm-worker-4"
        - name: HOST_ID
          value: "host-2"
        - name: CPU_LIMIT
          value: "250m"
      ports:
        - containerPort: 8000
      resources:
        requests:
          cpu: "100m"
          memory: "128Mi"
        limits:
          cpu: "250m"
          memory: "256Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: vm-worker-4-svc
spec:
  type: NodePort
  selector:
    vm-id: vm-worker-4
  ports:
    - port: 8000
      targetPort: 8000
      nodePort: 30084
```

### 5.4. Script Provisioning Klaster (`infra/setup_cluster.sh` & `infra/teardown_cluster.sh`)

**`infra/setup_cluster.sh`:**
```bash
#!/usr/bin/env bash
set -euo pipefail

echo "[1/5] Building heft-worker:latest Docker image..."
docker build -t heft-worker:latest ./worker

echo "[2/5] Creating Kind cluster 'heft-datacenter' (1 Datacenter, 2 Hosts)..."
if kind get clusters | grep -q "^heft-datacenter$"; then
    echo "Cluster 'heft-datacenter' already exists. Skipping creation."
else
    kind create cluster --config ./infra/kind-config.yaml
fi

echo "[3/5] Loading heft-worker:latest image into Kind nodes..."
kind load docker-image heft-worker:latest --name heft-datacenter

echo "[4/5] Deploying 4 heterogeneous VM pods and NodePort services..."
kubectl apply -f ./infra/k8s-workers.yaml

echo "[5/5] Waiting for all 4 VM pods to be Ready..."
kubectl wait --for=condition=Ready pod -l app=heft-worker --timeout=120s

echo "=== Topology Verification ==="
kubectl get pods -o wide
```

**`infra/teardown_cluster.sh`:**
```bash
#!/usr/bin/env bash
set -euo pipefail
kind delete cluster --name heft-datacenter
```

### 5.5. Aplikasi Worker VM (`worker/Dockerfile`, `worker/requirements.txt`, `worker/main.py`)

**`worker/requirements.txt`:**
```text
fastapi>=0.110.0
uvicorn>=0.28.0
pydantic>=2.6.0
```

**`worker/Dockerfile`:**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**`worker/main.py`:**
```python
import asyncio
import hashlib
import os
import time
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="KubeHEFT Worker VM")

VM_ID = os.getenv("VM_ID", "vm-unknown")
HOST_ID = os.getenv("HOST_ID", "host-unknown")
CPU_LIMIT = os.getenv("CPU_LIMIT", "1000m")

processor_lock = asyncio.Lock()


class ExecuteRequest(BaseModel):
    task_id: str
    iterations: int
    comm_delay_sec: float = 0.0


class CalibrateRequest(BaseModel):
    iterations: int = 1500000


def cpu_bound_sha256(iterations: int) -> str:
    data = b"kube-heft-realworld-cloud-benchmark"
    for _ in range(iterations):
        data = hashlib.sha256(data).digest()
    return data.hex()


@app.get("/health")
async def health():
    return {
        "status": "ready",
        "vm_id": VM_ID,
        "host_id": HOST_ID,
        "cpu_limit": CPU_LIMIT,
    }


@app.post("/calibrate")
async def calibrate(req: CalibrateRequest):
    loop = asyncio.get_running_loop()
    async with processor_lock:
        t0 = time.perf_counter()
        await loop.run_in_executor(None, cpu_bound_sha256, req.iterations)
        elapsed = time.perf_counter() - t0
    return {
        "vm_id": VM_ID,
        "iterations": req.iterations,
        "elapsed_sec": elapsed,
        "iterations_per_sec": req.iterations / max(elapsed, 1e-6),
    }


@app.post("/execute")
async def execute_task(req: ExecuteRequest):
    if req.comm_delay_sec > 0:
        await asyncio.sleep(req.comm_delay_sec)

    loop = asyncio.get_running_loop()
    async with processor_lock:
        compute_start = time.perf_counter()
        digest = await loop.run_in_executor(None, cpu_bound_sha256, req.iterations)
        compute_end = time.perf_counter()

    return {
        "task_id": req.task_id,
        "vm_id": VM_ID,
        "host_id": HOST_ID,
        "comm_delay_sec": req.comm_delay_sec,
        "compute_time_sec": compute_end - compute_start,
        "digest_sample": digest[:16],
    }
```

### 5.6. Dataset DAG (`master/dag_sample.json`)
```json
{
  "metadata": {
    "name": "Topcuoglu_2002_10_Task_DAG_4VM",
    "inter_host_comm_penalty": 1.5
  },
  "vms": [
    {"id": "vm-worker-1", "host": "host-1", "cpu_limit": "1000m", "speed_factor": 1.0,  "url": "http://localhost:30081"},
    {"id": "vm-worker-2", "host": "host-1", "cpu_limit": "500m",  "speed_factor": 0.5,  "url": "http://localhost:30082"},
    {"id": "vm-worker-3", "host": "host-2", "cpu_limit": "750m",  "speed_factor": 0.75, "url": "http://localhost:30083"},
    {"id": "vm-worker-4", "host": "host-2", "cpu_limit": "250m",  "speed_factor": 0.25, "url": "http://localhost:30084"}
  ],
  "tasks": [
    {"id": "T1",  "base_seconds_on_p1": 1.2, "w": {"vm-worker-1": 1.2, "vm-worker-2": 2.4, "vm-worker-3": 1.60, "vm-worker-4": 4.8}},
    {"id": "T2",  "base_seconds_on_p1": 1.0, "w": {"vm-worker-1": 1.0, "vm-worker-2": 2.0, "vm-worker-3": 1.33, "vm-worker-4": 4.0}},
    {"id": "T3",  "base_seconds_on_p1": 0.8, "w": {"vm-worker-1": 0.8, "vm-worker-2": 1.6, "vm-worker-3": 1.07, "vm-worker-4": 3.2}},
    {"id": "T4",  "base_seconds_on_p1": 0.9, "w": {"vm-worker-1": 0.9, "vm-worker-2": 1.8, "vm-worker-3": 1.20, "vm-worker-4": 3.6}},
    {"id": "T5",  "base_seconds_on_p1": 0.7, "w": {"vm-worker-1": 0.7, "vm-worker-2": 1.4, "vm-worker-3": 0.93, "vm-worker-4": 2.8}},
    {"id": "T6",  "base_seconds_on_p1": 1.1, "w": {"vm-worker-1": 1.1, "vm-worker-2": 2.2, "vm-worker-3": 1.47, "vm-worker-4": 4.4}},
    {"id": "T7",  "base_seconds_on_p1": 0.6, "w": {"vm-worker-1": 0.6, "vm-worker-2": 1.2, "vm-worker-3": 0.80, "vm-worker-4": 2.4}},
    {"id": "T8",  "base_seconds_on_p1": 0.9, "w": {"vm-worker-1": 0.9, "vm-worker-2": 1.8, "vm-worker-3": 1.20, "vm-worker-4": 3.6}},
    {"id": "T9",  "base_seconds_on_p1": 1.3, "w": {"vm-worker-1": 1.3, "vm-worker-2": 2.6, "vm-worker-3": 1.73, "vm-worker-4": 5.2}},
    {"id": "T10", "base_seconds_on_p1": 0.5, "w": {"vm-worker-1": 0.5, "vm-worker-2": 1.0, "vm-worker-3": 0.67, "vm-worker-4": 2.0}}
  ],
  "edges": [
    {"from": "T1", "to": "T2",  "comm_cost": 0.9},
    {"from": "T1", "to": "T3",  "comm_cost": 0.6},
    {"from": "T1", "to": "T4",  "comm_cost": 0.5},
    {"from": "T1", "to": "T5",  "comm_cost": 0.7},
    {"from": "T1", "to": "T6",  "comm_cost": 0.8},
    {"from": "T2", "to": "T8",  "comm_cost": 0.9},
    {"from": "T2", "to": "T9",  "comm_cost": 0.8},
    {"from": "T3", "to": "T7",  "comm_cost": 1.1},
    {"from": "T4", "to": "T8",  "comm_cost": 1.3},
    {"from": "T4", "to": "T9",  "comm_cost": 1.1},
    {"from": "T5", "to": "T9",  "comm_cost": 0.6},
    {"from": "T6", "to": "T8",  "comm_cost": 0.7},
    {"from": "T7", "to": "T10", "comm_cost": 0.8},
    {"from": "T8", "to": "T10", "comm_cost": 0.5},
    {"from": "T9", "to": "T10", "comm_cost": 0.6}
  ]
}
```

### 5.7. Implementasi Algoritma HEFT (`master/heft_algorithm.py`)
```python
from typing import Dict, List, Any


def get_comm_cost(
    from_task: str,
    to_task: str,
    vm_from: str,
    vm_to: str,
    edge_map: Dict[tuple, float],
    vm_host_map: Dict[str, str],
    inter_host_penalty: float = 1.5,
) -> float:
    if vm_from == vm_to:
        return 0.0
    base_cost = edge_map.get((from_task, to_task), 0.0)
    if vm_host_map[vm_from] != vm_host_map[vm_to]:
        return base_cost * inter_host_penalty
    return base_cost


def schedule_heft(dag_data: Dict[str, Any]) -> Dict[str, Any]:
    vms = [vm["id"] for vm in dag_data["vms"]]
    vm_host_map = {vm["id"]: vm["host"] for vm in dag_data["vms"]}
    penalty = dag_data["metadata"].get("inter_host_comm_penalty", 1.5)

    tasks = {t["id"]: t for t in dag_data["tasks"]}
    succ = {t_id: [] for t_id in tasks}
    pred = {t_id: [] for t_id in tasks}
    edge_map = {}

    for edge in dag_data["edges"]:
        u, v, c = edge["from"], edge["to"], edge["comm_cost"]
        succ[u].append(v)
        pred[v].append(u)
        edge_map[(u, v)] = c

    # Rata-rata faktor komunikasi antar pasangan VM untuk perhitungan rank_u
    pair_factors = []
    for v1 in vms:
        for v2 in vms:
            if v1 == v2:
                pair_factors.append(0.0)
            elif vm_host_map[v1] == vm_host_map[v2]:
                pair_factors.append(1.0)
            else:
                pair_factors.append(penalty)
    avg_comm_multiplier = sum(pair_factors) / len(pair_factors)

    w_bar = {
        t_id: sum(t_data["w"].values()) / len(vms)
        for t_id, t_data in tasks.items()
    }

    rank_u: Dict[str, float] = {}

    def compute_rank_u(t_id: str) -> float:
        if t_id in rank_u:
            return rank_u[t_id]
        if not succ[t_id]:
            rank_u[t_id] = w_bar[t_id]
        else:
            rank_u[t_id] = w_bar[t_id] + max(
                (edge_map[(t_id, s)] * avg_comm_multiplier) + compute_rank_u(s)
                for s in succ[t_id]
            )
        return rank_u[t_id]

    for t_id in tasks:
        compute_rank_u(t_id)

    priority_list = sorted(
        tasks.keys(),
        key=lambda x: (-rank_u[x], int(x[1:]) if x[1:].isdigit() else x),
    )

    vm_schedules: Dict[str, List[Dict[str, Any]]] = {vm_id: [] for vm_id in vms}
    task_schedule: Dict[str, Dict[str, Any]] = {}

    for t_id in priority_list:
        best_vm = None
        best_est = float("inf")
        best_eft = float("inf")
        best_comm = 0.0

        for vm_id in vms:
            duration = tasks[t_id]["w"][vm_id]
            ready_time = 0.0
            limiting_comm = 0.0

            for p_id in pred[t_id]:
                p_info = task_schedule[p_id]
                c_cost = get_comm_cost(
                    p_id, t_id, p_info["vm_id"], vm_id, edge_map, vm_host_map, penalty
                )
                arrival = p_info["aft"] + c_cost
                if arrival > ready_time:
                    ready_time = arrival
                    limiting_comm = c_cost

            sched = vm_schedules[vm_id]
            est_candidate = ready_time

            if not sched:
                est_candidate = ready_time
            else:
                # Periksa celah sebelum tugas pertama hingga celah antar tugas
                prev_end = 0.0
                inserted = False
                for item in sched:
                    slot_start = max(prev_end, ready_time)
                    if slot_start + duration <= item["ast"]:
                        est_candidate = slot_start
                        inserted = True
                        break
                    prev_end = item["aft"]
                if not inserted:
                    est_candidate = max(sched[-1]["aft"], ready_time)

            eft_candidate = est_candidate + duration
            if eft_candidate < best_eft:
                best_eft = eft_candidate
                best_est = est_candidate
                best_vm = vm_id
                best_comm = limiting_comm

        entry = {
            "task_id": t_id,
            "vm_id": best_vm,
            "ast": round(best_est, 4),
            "aft": round(best_eft, 4),
            "duration": round(best_eft - best_est, 4),
            "comm_delay": round(best_comm, 4),
            "rank_u": round(rank_u[t_id], 4),
        }
        task_schedule[t_id] = entry
        vm_schedules[best_vm].append(entry)
        vm_schedules[best_vm].sort(key=lambda x: x["ast"])

    makespan = max(item["aft"] for item in task_schedule.values())
    return {
        "algorithm": "HEFT",
        "priority_order": priority_list,
        "rank_u": rank_u,
        "task_schedule": task_schedule,
        "vm_schedules": vm_schedules,
        "theoretical_makespan": round(makespan, 4),
    }
```

### 5.8. Implementasi Baseline Round-Robin (`master/baseline_scheduler.py`)
```python
from typing import Dict, Any, List
from master.heft_algorithm import get_comm_cost


def schedule_round_robin(dag_data: Dict[str, Any]) -> Dict[str, Any]:
    vms = [vm["id"] for vm in dag_data["vms"]]
    vm_host_map = {vm["id"]: vm["host"] for vm in dag_data["vms"]}
    penalty = dag_data["metadata"].get("inter_host_comm_penalty", 1.5)

    tasks = {t["id"]: t for t in dag_data["tasks"]}
    pred = {t_id: [] for t_id in tasks}
    edge_map = {}

    for edge in dag_data["edges"]:
        u, v, c = edge["from"], edge["to"], edge["comm_cost"]
        pred[v].append(u)
        edge_map[(u, v)] = c

    # Urutan topologis berdasarkan indeks tugas (T1..T10)
    topo_order = [t["id"] for t in dag_data["tasks"]]

    vm_schedules: Dict[str, List[Dict[str, Any]]] = {vm_id: [] for vm_id in vms}
    task_schedule: Dict[str, Dict[str, Any]] = {}

    for idx, t_id in enumerate(topo_order):
        assigned_vm = vms[idx % len(vms)]
        duration = tasks[t_id]["w"][assigned_vm]

        ready_time = 0.0
        limiting_comm = 0.0
        for p_id in pred[t_id]:
            p_info = task_schedule[p_id]
            c_cost = get_comm_cost(
                p_id, t_id, p_info["vm_id"], assigned_vm, edge_map, vm_host_map, penalty
            )
            arrival = p_info["aft"] + c_cost
            if arrival > ready_time:
                ready_time = arrival
                limiting_comm = c_cost

        vm_avail = vm_schedules[assigned_vm][-1]["aft"] if vm_schedules[assigned_vm] else 0.0
        ast = max(vm_avail, ready_time)
        aft = ast + duration

        entry = {
            "task_id": t_id,
            "vm_id": assigned_vm,
            "ast": round(ast, 4),
            "aft": round(aft, 4),
            "duration": round(duration, 4),
            "comm_delay": round(limiting_comm, 4),
        }
        task_schedule[t_id] = entry
        vm_schedules[assigned_vm].append(entry)

    makespan = max(item["aft"] for item in task_schedule.values())
    return {
        "algorithm": "Round-Robin",
        "priority_order": topo_order,
        "task_schedule": task_schedule,
        "vm_schedules": vm_schedules,
        "theoretical_makespan": round(makespan, 4),
    }
```

### 5.9. Real-World Cloud Dispatcher (`master/dispatcher.py`)
```python
import asyncio
import time
from typing import Dict, Any
import httpx
from master.heft_algorithm import get_comm_cost


async def verify_and_calibrate_cluster(dag_data: Dict[str, Any]) -> Dict[str, Any]:
    vm_urls = {vm["id"]: vm["url"] for vm in dag_data["vms"]}
    health_results = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for vm_id, url in vm_urls.items():
            resp = await client.get(f"{url}/health")
            resp.raise_for_status()
            health_results[vm_id] = resp.json()

        # Kalibrasi kecepatan CPU riil pada vm-worker-1 (1000m = 1.0x reference)
        cal_resp = await client.post(
            f"{vm_urls['vm-worker-1']}/calibrate",
            json={"iterations": 2000000},
        )
        cal_resp.raise_for_status()
        iterations_per_sec = cal_resp.json()["iterations_per_sec"]

    return {
        "health": health_results,
        "iterations_per_sec_on_p1": iterations_per_sec,
    }


async def execute_schedule_on_cloud(
    dag_data: Dict[str, Any],
    schedule_plan: Dict[str, Any],
    iterations_per_sec_on_p1: float,
) -> Dict[str, Any]:
    vm_urls = {vm["id"]: vm["url"] for vm in dag_data["vms"]}
    vm_host_map = {vm["id"]: vm["host"] for vm in dag_data["vms"]}
    penalty = dag_data["metadata"].get("inter_host_comm_penalty", 1.5)

    tasks_meta = {t["id"]: t for t in dag_data["tasks"]}
    pred = {t["id"]: [] for t in dag_data["tasks"]}
    edge_map = {}
    for edge in dag_data["edges"]:
        pred[edge["to"]].append(edge["from"])
        edge_map[(edge["from"], edge["to"])] = edge["comm_cost"]

    task_plan = schedule_plan["task_schedule"]
    vm_queues = schedule_plan["vm_schedules"]

    # Map pendahulu urutan eksekusi di dalam VM yang sama agar urutan jadwal terjaga
    vm_prev_task: Dict[str, str | None] = {}
    for vm_id, ordered_items in vm_queues.items():
        for i, item in enumerate(ordered_items):
            vm_prev_task[item["task_id"]] = ordered_items[i - 1]["task_id"] if i > 0 else None

    done_events = {t_id: asyncio.Event() for t_id in tasks_meta}
    actual_results: Dict[str, Dict[str, Any]] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        experiment_t0 = time.perf_counter()

        async def run_single_task(t_id: str):
            # 1. Tunggu seluruh parent di DAG selesai
            for p_id in pred[t_id]:
                await done_events[p_id].wait()

            # 2. Tunggu tugas sebelumnya pada VM yang sama selesai
            prev_on_vm = vm_prev_task[t_id]
            if prev_on_vm is not None:
                await done_events[prev_on_vm].wait()

            target_vm = task_plan[t_id]["vm_id"]

            # 3. Hitung sisa delay komunikasi dari parent yang paling akhir tiba
            now_rel = time.perf_counter() - experiment_t0
            required_ready_time = 0.0
            for p_id in pred[t_id]:
                p_res = actual_results[p_id]
                c_cost = get_comm_cost(
                    p_id, t_id, p_res["vm_id"], target_vm, edge_map, vm_host_map, penalty
                )
                required_ready_time = max(required_ready_time, p_res["actual_aft"] + c_cost)

            remaining_comm_delay = max(0.0, required_ready_time - now_rel)
            workload_iterations = int(
                tasks_meta[t_id]["base_seconds_on_p1"] * iterations_per_sec_on_p1
            )

            if remaining_comm_delay > 0:
                await asyncio.sleep(remaining_comm_delay)

            actual_ast = time.perf_counter() - experiment_t0
            resp = await client.post(
                f"{vm_urls[target_vm]}/execute",
                json={
                    "task_id": t_id,
                    "iterations": workload_iterations,
                    "comm_delay_sec": 0.0,
                },
            )
            resp.raise_for_status()
            actual_aft = time.perf_counter() - experiment_t0
            worker_data = resp.json()

            actual_results[t_id] = {
                "task_id": t_id,
                "vm_id": target_vm,
                "host_id": worker_data["host_id"],
                "actual_ast": round(actual_ast, 4),
                "actual_aft": round(actual_aft, 4),
                "actual_duration": round(actual_aft - actual_ast, 4),
                "comm_wait_sec": round(remaining_comm_delay, 4),
            }
            done_events[t_id].set()

        await asyncio.gather(*(run_single_task(t_id) for t_id in tasks_meta))
        total_makespan = max(r["actual_aft"] for r in actual_results.values())

    return {
        "algorithm": schedule_plan["algorithm"],
        "actual_results": actual_results,
        "actual_makespan": round(total_makespan, 4),
    }
```

### 5.10. Modul Visualisasi & Evaluasi (`master/visualize.py`)
```python
from typing import Dict, Any
import matplotlib.pyplot as plt


def compute_metrics(
    dag_data: Dict[str, Any],
    makespan: float,
) -> Dict[str, float]:
    tasks = dag_data["tasks"]
    vms = [vm["id"] for vm in dag_data["vms"]]

    # Minimum sequential execution time across any single VM
    min_seq_time = min(
        sum(t["w"][vm_id] for t in tasks) for vm_id in vms
    )

    # Critical path minimum computation cost (T1 -> T4 -> T9 -> T10 on fastest processor)
    # Dihitung secara dinamis menggunakan DP pada DAG dengan bobot min_p(w_{i,p})
    min_w = {t["id"]: min(t["w"].values()) for t in tasks}
    succ = {t["id"]: [] for t in tasks}
    for e in dag_data["edges"]:
        succ[e["from"]].append(e["to"])

    cp_memo: Dict[str, float] = {}

    def get_cp_min(t_id: str) -> float:
        if t_id in cp_memo:
            return cp_memo[t_id]
        if not succ[t_id]:
            cp_memo[t_id] = min_w[t_id]
        else:
            cp_memo[t_id] = min_w[t_id] + max(get_cp_min(s) for s in succ[t_id])
        return cp_memo[t_id]

    cp_min_sum = max(get_cp_min(t["id"]) for t in tasks)

    slr = makespan / cp_min_sum
    speedup = min_seq_time / makespan
    return {
        "makespan": round(makespan, 4),
        "slr": round(slr, 4),
        "speedup": round(speedup, 4),
        "cp_min_sum": round(cp_min_sum, 4),
        "min_seq_time": round(min_seq_time, 4),
    }


def generate_gantt_chart(
    dag_data: Dict[str, Any],
    heft_theo: Dict[str, Any],
    heft_actual: Dict[str, Any],
    rr_actual: Dict[str, Any],
    output_path: str = "results/gantt_comparison.png",
) -> None:
    vms = [vm["id"] for vm in dag_data["vms"]]
    colors = plt.cm.tab10.colors

    fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
    panels = [
        (
            axes[0],
            f"1. HEFT Theoretical Schedule (Makespan = {heft_theo['theoretical_makespan']:.2f}s)",
            heft_theo["task_schedule"],
            "ast",
            "aft",
        ),
        (
            axes[1],
            f"2. HEFT Real-World Cloud Execution (Makespan = {heft_actual['actual_makespan']:.2f}s)",
            heft_actual["actual_results"],
            "actual_ast",
            "actual_aft",
        ),
        (
            axes[2],
            f"3. Round-Robin Real-World Cloud Execution (Makespan = {rr_actual['actual_makespan']:.2f}s)",
            rr_actual["actual_results"],
            "actual_ast",
            "actual_aft",
        ),
    ]

    for ax, title, sched_dict, start_key, end_key in panels:
        for t_id, info in sched_dict.items():
            t_num = int(t_id[1:]) - 1
            vm_idx = vms.index(info["vm_id"])
            start = info[start_key]
            dur = info[end_key] - start
            ax.barh(
                vm_idx,
                dur,
                left=start,
                height=0.55,
                color=colors[t_num % 10],
                edgecolor="black",
                alpha=0.88,
            )
            ax.text(
                start + dur / 2,
                vm_idx,
                f"{t_id}\n({dur:.2f}s)",
                ha="center",
                va="center",
                color="white",
                fontweight="bold",
                fontsize=8,
            )
        ax.set_yticks(range(len(vms)))
        ax.set_yticklabels(
            [f"{v['id']}\n({v['host']}, {v['cpu_limit']})" for v in dag_data["vms"]]
        )
        ax.set_title(title, fontweight="bold")
        ax.grid(axis="x", linestyle="--", alpha=0.5)

    axes[2].set_xlabel("Time (Seconds)", fontweight="bold")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def generate_markdown_report(
    dag_data: Dict[str, Any],
    calibration: Dict[str, Any],
    heft_theo: Dict[str, Any],
    heft_actual: Dict[str, Any],
    rr_theo: Dict[str, Any],
    rr_actual: Dict[str, Any],
    output_path: str = "results/evaluation_report.md",
) -> None:
    m_heft_theo = compute_metrics(dag_data, heft_theo["theoretical_makespan"])
    m_heft_act = compute_metrics(dag_data, heft_actual["actual_makespan"])
    m_rr_act = compute_metrics(dag_data, rr_actual["actual_makespan"])

    improvement_pct = (
        (m_rr_act["makespan"] - m_heft_act["makespan"]) / m_rr_act["makespan"]
    ) * 100.0

    lines = [
        "# Laporan Evaluasi Implementasi Cloud: Algoritma HEFT vs. Round-Robin\n",
        "## 1. Topologi Klaster & Spesifikasi VM Heterogen\n",
        "| VM ID | Host Node | Limit CPU | Status Kesehatan |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for vm_id, h in calibration["health"].items():
        lines.append(f"| `{vm_id}` | `{h['host_id']}` | `{h['cpu_limit']}` | `{h['status']}` |")

    lines.extend([
        f"\n* **Hasil Kalibrasi Benchmark CPU (`vm-worker-1` @ 1000m):** `{calibration['iterations_per_sec_on_p1']:,.0f}` SHA-256 iterasi/detik.\n",
        "## 2. Urutan Prioritas Tugas (Fase 1 HEFT - Upward Rank)\n",
        f"**Urutan Eksekusi Prioritas:** `{' -> '.join(heft_theo['priority_order'])}`\n",
        "| Task ID | Upward Rank ($rank_u$) | VM Terpilih (HEFT) | EST Teoritis (s) | EFT Teoritis (s) | Aktual Mulai (s) | Aktual Selesai (s) |",
        "| :--- | :---: | :--- | :---: | :---: | :---: | :---: |",
    ])

    for t_id in heft_theo["priority_order"]:
        th = heft_theo["task_schedule"][t_id]
        ac = heft_actual["actual_results"][t_id]
        lines.append(
            f"| **{t_id}** | {th['rank_u']:.4f} | `{th['vm_id']}` | {th['ast']:.2f} | {th['aft']:.2f} | {ac['actual_ast']:.2f} | {ac['actual_aft']:.2f} |"
        )

    lines.extend([
        "\n## 3. Perbandingan Metrik Performa Utama\n",
        "| Skema Penjadwalan | Makespan ($C_{\\max}$) | Schedule Length Ratio (SLR) | Speedup |",
        "| :--- | :---: | :---: | :---: |",
        f"| **HEFT (Teoritis)** | {m_heft_theo['makespan']:.2f} s | {m_heft_theo['slr']:.3f} | {m_heft_theo['speedup']:.3f}x |",
        f"| **HEFT (Aktual Cloud Kubernetes)** | **{m_heft_act['makespan']:.2f} s** | **{m_heft_act['slr']:.3f}** | **{m_heft_act['speedup']:.3f}x** |",
        f"| **Round-Robin (Aktual Cloud Kubernetes)** | {m_rr_act['makespan']:.2f} s | {m_rr_act['slr']:.3f} | {m_rr_act['speedup']:.3f}x |",
        f"\n> **Kesimpulan Eksperimen:** Pada klaster Kubernetes heterogen nyata (1 Datacenter, 2 Host, 4 VM), algoritma **HEFT** mereduksi total *makespan* sebesar **{improvement_pct:.2f}%** dibandingkan penjadwalan *Round-Robin*.\n",
    ])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
```

### 5.11. Entrypoint Eksperimen Utama (`master/run_experiment.py`)
```python
import asyncio
import json
import os
from master.heft_algorithm import schedule_heft
from master.baseline_scheduler import schedule_round_robin
from master.dispatcher import verify_and_calibrate_cluster, execute_schedule_on_cloud
from master.visualize import generate_gantt_chart, generate_markdown_report


async def main():
    os.makedirs("results", exist_ok=True)
    with open("master/dag_sample.json", "r", encoding="utf-8") as f:
        dag_data = json.load(f)

    print("[1/5] Menghitung jadwal teoritis HEFT dan Round-Robin...")
    heft_theo = schedule_heft(dag_data)
    rr_theo = schedule_round_robin(dag_data)
    print(f"      -> Urutan Prioritas HEFT : {heft_theo['priority_order']}")
    print(f"      -> Makespan Teoritis HEFT: {heft_theo['theoretical_makespan']:.2f}s")
    print(f"      -> Makespan Teoritis RR  : {rr_theo['theoretical_makespan']:.2f}s")

    print("[2/5] Memverifikasi kesehatan 4 Pod VM & mengkalibrasi CPU klaster...")
    calibration = await verify_and_calibrate_cluster(dag_data)
    print(f"      -> Kecepatan Kalibrasi p1: {calibration['iterations_per_sec_on_p1']:,.0f} iterasi/detik")

    print("[3/5] Mengeksekusi jadwal HEFT secara riil di klaster Kubernetes...")
    heft_actual = await execute_schedule_on_cloud(
        dag_data, heft_theo, calibration["iterations_per_sec_on_p1"]
    )
    print(f"      -> Makespan Aktual HEFT  : {heft_actual['actual_makespan']:.2f}s")

    print("[4/5] Mengeksekusi jadwal Round-Robin secara riil di klaster Kubernetes...")
    rr_actual = await execute_schedule_on_cloud(
        dag_data, rr_theo, calibration["iterations_per_sec_on_p1"]
    )
    print(f"      -> Makespan Aktual RR    : {rr_actual['actual_makespan']:.2f}s")

    print("[5/5] Menyimpan log, grafik Gantt Chart, dan laporan evaluasi...")
    with open("results/execution_log.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "calibration": calibration,
                "heft_theoretical": heft_theo,
                "heft_actual": heft_actual,
                "rr_theoretical": rr_theo,
                "rr_actual": rr_actual,
            },
            f,
            indent=2,
        )

    generate_gantt_chart(dag_data, heft_theo, heft_actual, rr_actual)
    generate_markdown_report(
        dag_data, calibration, heft_theo, heft_actual, rr_theo, rr_actual
    )
    print("Selesai! Cek results/gantt_comparison.png dan results/evaluation_report.md")


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 6. Kriteria Penerimaan (Acceptance Criteria)

1. **Verifikasi Topologi Cloud:** Output `kubectl get pods -o wide` menunjukkan 4 Pod berstatus `Running`, dengan `vm-worker-1` & `vm-worker-2` berjalan di node `heft-datacenter-worker` (`host-1`), serta `vm-worker-3` & `vm-worker-4` berjalan di node `heft-datacenter-worker2` (`host-2`).
2. **Verifikasi Heterogenitas Perangkat Keras:** Karena kuota `limits.cpu` (`1000m`, `750m`, `500m`, `250m`), beban iterasi SHA-256 yang sama dieksekusi dengan durasi yang berbanding terbalik secara proporsional pada masing-masing Pod.
3. **Validitas Algoritma HEFT:** Urutan $rank_u$ menempatkan `T1` sebagai tugas pertama dan `T10` sebagai tugas terakhir, menghindari penempatan tugas jalur kritis pada `vm-worker-4` (`250m`), dan menghasilkan *Actual Makespan* yang lebih rendah secara signifikan dibandingkan *Round-Robin*.
4. **Bukti Artefak Laporan:** Terbentuknya file `results/gantt_comparison.png`, `results/execution_log.json`, dan `results/evaluation_report.md` tanpa *error*.

---

## 7. Panduan Eksekusi Otomatis untuk AI Coding Agent

Gunakan prompt di bawah ini pada **Antigravity (Gemini Flash)** atau **Claude Code** di terminal WSL2:

```text
Baca file PRD.md di direktori ini. Ekstrak dan buat seluruh file proyek sesuai struktur dan isi kode yang tertulis di PRD.md (requirements.txt, infra/*, worker/*, dan master/*). Setelah semua file dibuat:
1. Berikan izin eksekusi (chmod +x) pada infra/setup_cluster.sh dan infra/teardown_cluster.sh.
2. Jalankan ./infra/setup_cluster.sh untuk membangun Docker image, membuat klaster Kind 2-Host, dan mendeploy 4 Pod VM heterogen.
3. Buat virtual environment Python atau instal requirements.txt, lalu jalankan python3 -m master.run_experiment.
4. Tampilkan isi results/evaluation_report.md dan output kubectl get pods -o wide setelah eksperimen selesai.
```