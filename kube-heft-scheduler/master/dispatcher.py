"""Real-World Cloud Dispatcher (asyncio + httpx).

Alur eksekusi tiap tugas n_i pada VM target p:
  1. Tunggu tugas sebelumnya pada VM yang sama (urutan jadwal dipertahankan).
  2. Tunggu seluruh data dari pendahulu tiba di p:
       - pendahulu di VM yang sama  -> data lokal, tanpa transfer.
       - pendahulu di VM berbeda    -> VM sumber mengirim payload riil (HTTP) ke p via
                                       DNS Service klaster, ditambah injeksi latensi
                                       topologi (intra-host 1.0x, inter-host 1.5x).
  3. Kirim POST /execute (SHA-256 CPU-bound) dan catat waktu mulai/selesai aktual.
  4. Segera setelah selesai, push data ke seluruh successor yang berada di VM lain.
"""
import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx

from master.heft_algorithm import build_graph, get_comm_cost


async def verify_and_calibrate_cluster(
    dag_data: Dict[str, Any], calib_iterations: int = 1_500_000
) -> Dict[str, Any]:
    vm_urls = {vm["id"]: vm["url"] for vm in dag_data["vms"]}
    health_results: Dict[str, Any] = {}
    per_vm: Dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=120.0) as client:
        for vm_id, url in vm_urls.items():
            resp = await client.get(f"{url}/health")
            resp.raise_for_status()
            health_results[vm_id] = resp.json()

        # Warm-up singkat agar interpreter & cache siap
        await asyncio.gather(*(
            client.post(f"{u}/calibrate", json={"iterations": 50_000}) for u in vm_urls.values()
        ))

        # Kalibrasi berurutan pada tiap VM (verifikasi heterogenitas CFS quota)
        for vm_id, url in vm_urls.items():
            r = await client.post(f"{url}/calibrate", json={"iterations": calib_iterations})
            r.raise_for_status()
            per_vm[vm_id] = r.json()

    ref = per_vm["vm-worker-1"]["iterations_per_sec"]
    for vm_id, d in per_vm.items():
        d["measured_speed_ratio"] = d["iterations_per_sec"] / ref

    return {
        "health": health_results,
        "per_vm": per_vm,
        "iterations_per_sec_on_p1": ref,
    }


async def execute_schedule_on_cloud(
    dag_data: Dict[str, Any],
    schedule_plan: Dict[str, Any],
    iterations_per_sec_on_p1: float,
) -> Dict[str, Any]:
    vm_urls = {vm["id"]: vm["url"] for vm in dag_data["vms"]}
    vm_internal = {vm["id"]: vm["internal_url"] for vm in dag_data["vms"]}
    vm_host_map = {vm["id"]: vm["host"] for vm in dag_data["vms"]}
    penalty = dag_data["metadata"].get("inter_host_comm_penalty", 1.5)
    intra = dag_data["metadata"].get("intra_host_comm_factor", 1.0)
    data_kb = {(e["from"], e["to"]): e.get("data_kb", 0) for e in dag_data["edges"]}

    tasks_meta, succ, pred, edge_map = build_graph(dag_data)
    task_plan = schedule_plan["task_schedule"]
    vm_queues = schedule_plan["vm_schedules"]

    vm_prev_task: Dict[str, Optional[str]] = {}
    for _, ordered_items in vm_queues.items():
        ordered = sorted(ordered_items, key=lambda x: x["ast"])
        for i, item in enumerate(ordered):
            vm_prev_task[item["task_id"]] = ordered[i - 1]["task_id"] if i > 0 else None

    done_events = {t: asyncio.Event() for t in tasks_meta}
    data_events = {edge: asyncio.Event() for edge in edge_map}
    data_arrival: Dict[tuple, float] = {}
    actual_results: Dict[str, Dict[str, Any]] = {}
    transfers: List[Dict[str, Any]] = []
    background: List[asyncio.Task] = []

    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    async with httpx.AsyncClient(timeout=180.0, limits=limits) as client:
        t0 = time.perf_counter()

        def now() -> float:
            return time.perf_counter() - t0

        async def push_data(src_task: str, dst_task: str):
            src_vm = task_plan[src_task]["vm_id"]
            dst_vm = task_plan[dst_task]["vm_id"]
            edge = (src_task, dst_task)
            if src_vm == dst_vm:
                data_arrival[edge] = actual_results[src_task]["actual_aft"]
                data_events[edge].set()
                return
            c_cost = get_comm_cost(src_task, dst_task, src_vm, dst_vm,
                                   edge_map, vm_host_map, penalty, intra)
            send_start = now()
            r = await client.post(
                f"{vm_urls[src_vm]}/transfer",
                json={
                    "edge": f"{src_task}->{dst_task}",
                    "dest_vm": dst_vm,
                    "dest_url": vm_internal[dst_vm],
                    "payload_kb": data_kb[edge],
                    "target_comm_sec": c_cost,
                },
            )
            r.raise_for_status()
            info = r.json()
            arrival = now()
            data_arrival[edge] = arrival
            transfers.append({
                "edge": f"{src_task}->{dst_task}",
                "src_vm": src_vm,
                "dst_vm": dst_vm,
                "link": "inter-host" if vm_host_map[src_vm] != vm_host_map[dst_vm] else "intra-host",
                "payload_kb": data_kb[edge],
                "model_comm_sec": round(c_cost, 4),
                "real_transfer_sec": round(info["real_transfer_sec"], 4),
                "injected_latency_sec": round(info["injected_latency_sec"], 4),
                "send_start": round(send_start, 4),
                "arrival": round(arrival, 4),
            })
            data_events[edge].set()

        async def run_single_task(t_id: str):
            prev_on_vm = vm_prev_task[t_id]
            if prev_on_vm is not None:
                await done_events[prev_on_vm].wait()
            for p_id in pred[t_id]:
                await data_events[(p_id, t_id)].wait()

            target_vm = task_plan[t_id]["vm_id"]
            iterations = int(tasks_meta[t_id]["base_seconds_on_p1"] * iterations_per_sec_on_p1)

            data_ready = max((data_arrival[(p, t_id)] for p in pred[t_id]), default=0.0)
            actual_ast = now()
            resp = await client.post(
                f"{vm_urls[target_vm]}/execute",
                json={"task_id": t_id, "iterations": iterations, "comm_delay_sec": 0.0},
            )
            resp.raise_for_status()
            actual_aft = now()
            worker_data = resp.json()

            actual_results[t_id] = {
                "task_id": t_id,
                "vm_id": target_vm,
                "host_id": worker_data["host_id"],
                "node_name": worker_data.get("node_name"),
                "iterations": iterations,
                "data_ready_time": round(data_ready, 4),
                "actual_ast": round(actual_ast, 4),
                "actual_aft": round(actual_aft, 4),
                "actual_duration": round(actual_aft - actual_ast, 4),
                "compute_time_sec": round(worker_data["compute_time_sec"], 4),
            }
            done_events[t_id].set()
            for s in succ[t_id]:
                background.append(asyncio.create_task(push_data(t_id, s)))

        await asyncio.gather(*(run_single_task(t) for t in tasks_meta))
        if background:
            await asyncio.gather(*background)

    total_makespan = max(r["actual_aft"] for r in actual_results.values())
    return {
        "algorithm": schedule_plan["algorithm"],
        "actual_results": actual_results,
        "transfers": sorted(transfers, key=lambda x: x["send_start"]),
        "actual_makespan": round(total_makespan, 4),
    }
