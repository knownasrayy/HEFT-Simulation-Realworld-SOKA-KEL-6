"""KubeHEFT Worker VM.

Setiap Pod (VM) menjalankan aplikasi ini. Beban kerja adalah SHA-256 hashing murni
(CPU-bound, tanpa sleep) sehingga kecepatan eksekusi benar-benar dibatasi oleh
CFS quota Kubernetes (`resources.limits.cpu`).
"""
import asyncio
import hashlib
import os
import socket
import time

import httpx
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI(title="KubeHEFT Worker VM")

VM_ID = os.getenv("VM_ID", "vm-unknown")
HOST_ID = os.getenv("HOST_ID", "host-unknown")
NODE_NAME = os.getenv("NODE_NAME", "node-unknown")
CPU_LIMIT = os.getenv("CPU_LIMIT", "1000m")

# Satu VM hanya mengeksekusi satu tugas komputasi pada satu waktu (non-preemptive)
processor_lock = asyncio.Lock()


class ExecuteRequest(BaseModel):
    task_id: str
    iterations: int
    comm_delay_sec: float = 0.0
    output_payload_kb: int = 0


class CalibrateRequest(BaseModel):
    iterations: int = 1_500_000


class TransferRequest(BaseModel):
    edge: str
    dest_vm: str
    dest_url: str
    payload_kb: int
    target_comm_sec: float = 0.0  # biaya komunikasi model (topology-aware)


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
        "node_name": NODE_NAME,
        "pod_hostname": socket.gethostname(),
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
        "host_id": HOST_ID,
        "cpu_limit": CPU_LIMIT,
        "iterations": req.iterations,
        "elapsed_sec": elapsed,
        "iterations_per_sec": req.iterations / max(elapsed, 1e-6),
    }


@app.post("/receive")
async def receive(request: Request):
    """Endpoint penerima payload data antar-VM (FR-02: transfer data riil)."""
    t0 = time.perf_counter()
    body = await request.body()
    return {
        "vm_id": VM_ID,
        "host_id": HOST_ID,
        "received_bytes": len(body),
        "recv_time_sec": time.perf_counter() - t0,
    }


@app.post("/transfer")
async def transfer(req: TransferRequest):
    """FR-02: kirim payload data riil dari VM ini ke VM tujuan melalui jaringan klaster.

    Setelah transfer HTTP riil selesai, ditambahkan injeksi latensi sehingga total
    waktu komunikasi = max(transfer_riil, biaya_model). Biaya model sudah memuat
    penalti lintas-host (inter-host 1.5x vs intra-host 1.0x).
    """
    payload = os.urandom(req.payload_kb * 1024)
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{req.dest_url}/receive",
            content=payload,
            headers={"Content-Type": "application/octet-stream"},
        )
        resp.raise_for_status()
        recv_info = resp.json()
    real_transfer = time.perf_counter() - t0
    injected = max(0.0, req.target_comm_sec - real_transfer)
    if injected > 0:
        await asyncio.sleep(injected)
    return {
        "edge": req.edge,
        "src_vm": VM_ID,
        "src_host": HOST_ID,
        "dest_vm": recv_info["vm_id"],
        "dest_host": recv_info["host_id"],
        "bytes": recv_info["received_bytes"],
        "real_transfer_sec": real_transfer,
        "injected_latency_sec": injected,
        "total_comm_sec": time.perf_counter() - t0,
    }


@app.post("/execute")
async def execute_task(req: ExecuteRequest):
    if req.comm_delay_sec > 0:
        await asyncio.sleep(req.comm_delay_sec)

    loop = asyncio.get_running_loop()
    async with processor_lock:
        start_ts = time.time()
        compute_start = time.perf_counter()
        digest = await loop.run_in_executor(None, cpu_bound_sha256, req.iterations)
        compute_end = time.perf_counter()
        end_ts = time.time()

    return {
        "task_id": req.task_id,
        "vm_id": VM_ID,
        "host_id": HOST_ID,
        "node_name": NODE_NAME,
        "start_timestamp": start_ts,
        "end_timestamp": end_ts,
        "comm_delay_sec": req.comm_delay_sec,
        "compute_time_sec": compute_end - compute_start,
        "digest_sample": digest[:16],
    }
