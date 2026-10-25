"""Baseline pembanding: Topological Round-Robin.

Tugas diambil dalam urutan topologis (Kahn, tie-break indeks tugas) lalu dibagikan
bergiliran VM1 -> VM2 -> VM3 -> VM4 tanpa mempertimbangkan heterogenitas.
"""
from typing import Any, Dict, List

from master.heft_algorithm import build_graph, get_comm_cost


def topological_order(dag_data: Dict[str, Any]) -> List[str]:
    tasks, succ, pred, _ = build_graph(dag_data)
    order_idx = {t["id"]: i for i, t in enumerate(dag_data["tasks"])}
    indeg = {t: len(pred[t]) for t in tasks}
    ready = sorted([t for t, d in indeg.items() if d == 0], key=order_idx.get)
    order: List[str] = []
    while ready:
        t = ready.pop(0)
        order.append(t)
        for s in succ[t]:
            indeg[s] -= 1
            if indeg[s] == 0:
                ready.append(s)
        ready.sort(key=order_idx.get)
    if len(order) != len(tasks):
        raise ValueError("DAG mengandung siklus")
    return order


def schedule_round_robin(dag_data: Dict[str, Any]) -> Dict[str, Any]:
    vms = [vm["id"] for vm in dag_data["vms"]]
    vm_host_map = {vm["id"]: vm["host"] for vm in dag_data["vms"]}
    penalty = dag_data["metadata"].get("inter_host_comm_penalty", 1.5)
    intra = dag_data["metadata"].get("intra_host_comm_factor", 1.0)

    tasks, _, pred, edge_map = build_graph(dag_data)
    topo_order = topological_order(dag_data)

    vm_schedules: Dict[str, List[Dict[str, Any]]] = {vm_id: [] for vm_id in vms}
    task_schedule: Dict[str, Dict[str, Any]] = {}

    for idx, t_id in enumerate(topo_order):
        assigned_vm = vms[idx % len(vms)]
        duration = tasks[t_id]["w"][assigned_vm]

        ready_time, limiting_comm = 0.0, 0.0
        for p_id in pred[t_id]:
            p_info = task_schedule[p_id]
            c_cost = get_comm_cost(p_id, t_id, p_info["vm_id"], assigned_vm,
                                   edge_map, vm_host_map, penalty, intra)
            arrival = p_info["aft"] + c_cost
            if arrival > ready_time:
                ready_time, limiting_comm = arrival, c_cost

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
