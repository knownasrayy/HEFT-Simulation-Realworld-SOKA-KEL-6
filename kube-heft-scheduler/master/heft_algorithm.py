"""Implementasi algoritma HEFT (Topcuoglu, Hariri & Wu, 2002).

Fase 1 - Task Prioritizing : upward rank (rank_u) rekursif dari exit task.
Fase 2 - Processor Selection: Earliest Finish Time dengan insertion-based policy.
"""
from typing import Any, Dict, List, Tuple


def build_graph(dag_data: Dict[str, Any]):
    tasks = {t["id"]: t for t in dag_data["tasks"]}
    succ: Dict[str, List[str]] = {t_id: [] for t_id in tasks}
    pred: Dict[str, List[str]] = {t_id: [] for t_id in tasks}
    edge_map: Dict[Tuple[str, str], float] = {}
    for edge in dag_data["edges"]:
        u, v = edge["from"], edge["to"]
        succ[u].append(v)
        pred[v].append(u)
        edge_map[(u, v)] = edge["comm_cost"]
    return tasks, succ, pred, edge_map


def comm_factor(vm_from: str, vm_to: str, vm_host_map: Dict[str, str],
                inter_host_penalty: float = 1.5, intra_host_factor: float = 1.0) -> float:
    """Faktor pengali biaya komunikasi berbasis topologi."""
    if vm_from == vm_to:
        return 0.0
    if vm_host_map[vm_from] != vm_host_map[vm_to]:
        return inter_host_penalty
    return intra_host_factor


def get_comm_cost(
    from_task: str,
    to_task: str,
    vm_from: str,
    vm_to: str,
    edge_map: Dict[tuple, float],
    vm_host_map: Dict[str, str],
    inter_host_penalty: float = 1.5,
    intra_host_factor: float = 1.0,
) -> float:
    """c_{m,i}(p_a, p_b): 0 jika VM sama, 1.0x intra-host, 1.5x inter-host."""
    base_cost = edge_map.get((from_task, to_task), 0.0)
    return base_cost * comm_factor(vm_from, vm_to, vm_host_map, inter_host_penalty, intra_host_factor)


def _find_slot(sched: List[Dict[str, Any]], ready_time: float, duration: float) -> float:
    """Insertion-based policy: cari idle slot paling awal yang cukup menampung tugas.

    `sched` sudah terurut berdasarkan AST. Celah dimulai dari t=0.
    """
    prev_end = 0.0
    for item in sched:
        slot_start = max(prev_end, ready_time)
        if slot_start + duration <= item["ast"] + 1e-9:
            return slot_start
        prev_end = max(prev_end, item["aft"])
    return max(prev_end, ready_time)


def schedule_heft(dag_data: Dict[str, Any]) -> Dict[str, Any]:
    vms = [vm["id"] for vm in dag_data["vms"]]
    vm_host_map = {vm["id"]: vm["host"] for vm in dag_data["vms"]}
    penalty = dag_data["metadata"].get("inter_host_comm_penalty", 1.5)
    intra = dag_data["metadata"].get("intra_host_comm_factor", 1.0)

    tasks, succ, pred, edge_map = build_graph(dag_data)

    # c̄_{i,k}: rata-rata biaya komunikasi edge atas seluruh pasangan VM BERBEDA
    # (sesuai paper: komunikasi pada prosesor yang sama bernilai nol dan tidak dirata-rata).
    pair_factors = [
        comm_factor(v1, v2, vm_host_map, penalty, intra)
        for v1 in vms for v2 in vms if v1 != v2
    ]
    avg_comm_multiplier = sum(pair_factors) / len(pair_factors)

    # w̄_i: rata-rata biaya komputasi di seluruh q VM
    w_bar = {t_id: sum(t["w"][vm] for vm in vms) / len(vms) for t_id, t in tasks.items()}

    rank_u: Dict[str, float] = {}

    def compute_rank_u(t_id: str) -> float:
        if t_id in rank_u:
            return rank_u[t_id]
        if not succ[t_id]:
            rank_u[t_id] = w_bar[t_id]
        else:
            rank_u[t_id] = w_bar[t_id] + max(
                edge_map[(t_id, s)] * avg_comm_multiplier + compute_rank_u(s)
                for s in succ[t_id]
            )
        return rank_u[t_id]

    for t_id in tasks:
        compute_rank_u(t_id)

    def _tid_key(x: str):
        return int(x[1:]) if x[1:].isdigit() else x

    priority_list = sorted(tasks.keys(), key=lambda x: (-rank_u[x], _tid_key(x)))

    vm_schedules: Dict[str, List[Dict[str, Any]]] = {vm_id: [] for vm_id in vms}
    task_schedule: Dict[str, Dict[str, Any]] = {}
    eft_table: Dict[str, Dict[str, Dict[str, float]]] = {}

    for t_id in priority_list:
        best = None
        eft_table[t_id] = {}
        for vm_id in vms:
            duration = tasks[t_id]["w"][vm_id]
            ready_time, limiting_comm = 0.0, 0.0
            for p_id in pred[t_id]:
                p_info = task_schedule[p_id]
                c_cost = get_comm_cost(p_id, t_id, p_info["vm_id"], vm_id,
                                       edge_map, vm_host_map, penalty, intra)
                arrival = p_info["aft"] + c_cost
                if arrival > ready_time:
                    ready_time, limiting_comm = arrival, c_cost

            est = _find_slot(vm_schedules[vm_id], ready_time, duration)
            eft = est + duration
            eft_table[t_id][vm_id] = {"est": round(est, 4), "eft": round(eft, 4)}
            if best is None or eft < best["eft"] - 1e-9:
                best = {"vm_id": vm_id, "est": est, "eft": eft, "comm": limiting_comm}

        entry = {
            "task_id": t_id,
            "vm_id": best["vm_id"],
            "ast": round(best["est"], 4),
            "aft": round(best["eft"], 4),
            "duration": round(best["eft"] - best["est"], 4),
            "comm_delay": round(best["comm"], 4),
            "rank_u": round(rank_u[t_id], 4),
        }
        task_schedule[t_id] = entry
        vm_schedules[best["vm_id"]].append(entry)
        vm_schedules[best["vm_id"]].sort(key=lambda x: x["ast"])

    makespan = max(item["aft"] for item in task_schedule.values())
    return {
        "algorithm": "HEFT",
        "priority_order": priority_list,
        "rank_u": {k: round(v, 4) for k, v in rank_u.items()},
        "w_bar": {k: round(v, 4) for k, v in w_bar.items()},
        "avg_comm_multiplier": round(avg_comm_multiplier, 4),
        "eft_table": eft_table,
        "task_schedule": task_schedule,
        "vm_schedules": vm_schedules,
        "theoretical_makespan": round(makespan, 4),
    }


if __name__ == "__main__":
    import json
    import os

    path = os.path.join(os.path.dirname(__file__), "dag_sample.json")
    with open(path, encoding="utf-8") as f:
        result = schedule_heft(json.load(f))
    print("Priority:", " -> ".join(result["priority_order"]))
    for t in result["priority_order"]:
        s = result["task_schedule"][t]
        print(f"{t:>4} rank_u={s['rank_u']:7.4f}  {s['vm_id']}  [{s['ast']:6.2f}, {s['aft']:6.2f}]")
    print("Makespan:", result["theoretical_makespan"])
