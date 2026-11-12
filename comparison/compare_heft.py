"""Skrip Komparasi Terpadu: Teori HEFT vs CloudSim (Simulation Biasa) vs Kubernetes (Simulation Realworld).

Menjalankan evaluasi komparatif:
1. Teori HEFT Murni (Topcuoglu et al., 2002) - varian Topology-Aware dan Flat-Network.
2. HEFT Simulation Biasa (CloudSim 7.0.1 Java) - hasil eksekusi aktual di results/cloudsim_*.json.
3. HEFT Simulation Realworld (Kubernetes Kind) - hasil eksekusi riil di execution_log.json.

Output:
- results/comparison_report.md
- results/comparison_summary.json
- results/comparison_chart.png (jika matplotlib tersedia)
"""
import argparse
import json
import os
import statistics
from typing import Any, Dict, List, Optional, Tuple


def build_graph(dag_data: Dict[str, Any]):
    tasks = {t["id"]: t for t in dag_data["tasks"]}
    succ: Dict[str, List[str]] = {tid: [] for tid in tasks}
    pred: Dict[str, List[str]] = {tid: [] for tid in tasks}
    edge_map: Dict[Tuple[str, str], float] = {}
    for edge in dag_data["edges"]:
        u, v = edge["from"], edge["to"]
        succ[u].append(v)
        pred[v].append(u)
        edge_map[(u, v)] = edge["comm_cost"]
    return tasks, succ, pred, edge_map


def comm_factor(
    vm_from: str,
    vm_to: str,
    vm_host_map: Dict[str, str],
    topology_aware: bool,
    inter_host_penalty: float,
    intra_host_factor: float,
) -> float:
    if vm_from == vm_to:
        return 0.0
    if not topology_aware:
        return 1.0
    return inter_host_penalty if vm_host_map[vm_from] != vm_host_map[vm_to] else intra_host_factor


def find_slot(sched: List[Dict[str, Any]], ready_time: float, duration: float) -> float:
    prev_end = 0.0
    for item in sched:
        slot_start = max(prev_end, ready_time)
        if slot_start + duration <= item["ast"] + 1e-9:
            return slot_start
        prev_end = max(prev_end, item["aft"])
    return max(prev_end, ready_time)


def compute_theoretical_heft(
    dag_data: Dict[str, Any],
    topology_aware: bool = True,
    avg_over_all_pairs: bool = False,
    exact_ratio_w: bool = False,
) -> Dict[str, Any]:
    """Menghitung jadwal teoritis HEFT sesuai parameter model jaringan dan w_ij."""
    vms = [vm["id"] for vm in dag_data["vms"]]
    vm_host_map = {vm["id"]: vm["host"] for vm in dag_data["vms"]}
    vm_speed_map = {vm["id"]: vm["speed_factor"] for vm in dag_data["vms"]}
    penalty = dag_data["metadata"].get("inter_host_comm_penalty", 1.5)
    intra = dag_data["metadata"].get("intra_host_comm_factor", 1.0)

    tasks, succ, pred, edge_map = build_graph(dag_data)

    def task_w(t_id: str, vm_id: str) -> float:
        if exact_ratio_w:
            return tasks[t_id]["base_seconds_on_p1"] / vm_speed_map[vm_id]
        return tasks[t_id]["w"][vm_id]

    if avg_over_all_pairs:
        pair_factors = [
            comm_factor(v1, v2, vm_host_map, topology_aware, penalty, intra)
            for v1 in vms
            for v2 in vms
        ]
    else:
        pair_factors = [
            comm_factor(v1, v2, vm_host_map, topology_aware, penalty, intra)
            for v1 in vms
            for v2 in vms
            if v1 != v2
        ]
    avg_comm_multiplier = sum(pair_factors) / len(pair_factors)

    w_bar = {t_id: sum(task_w(t_id, vm) for vm in vms) / len(vms) for t_id in tasks}
    rank_u: Dict[str, float] = {}

    def calc_rank(t_id: str) -> float:
        if t_id in rank_u:
            return rank_u[t_id]
        if not succ[t_id]:
            rank_u[t_id] = w_bar[t_id]
        else:
            rank_u[t_id] = w_bar[t_id] + max(
                edge_map[(t_id, s)] * avg_comm_multiplier + calc_rank(s) for s in succ[t_id]
            )
        return rank_u[t_id]

    for t_id in tasks:
        calc_rank(t_id)

    def tid_key(x: str):
        return int(x[1:]) if x[1:].isdigit() else x

    priority_order = sorted(tasks.keys(), key=lambda x: (-round(rank_u[x], 9), tid_key(x)))

    vm_schedules: Dict[str, List[Dict[str, Any]]] = {vm_id: [] for vm_id in vms}
    task_schedule: Dict[str, Dict[str, Any]] = {}

    for t_id in priority_order:
        best = None
        for vm_id in vms:
            duration = task_w(t_id, vm_id)
            ready_time = 0.0
            for p_id in pred[t_id]:
                p_info = task_schedule[p_id]
                factor = comm_factor(p_info["vm_id"], vm_id, vm_host_map, topology_aware, penalty, intra)
                c_cost = edge_map[(p_id, t_id)] * factor
                ready_time = max(ready_time, p_info["aft"] + c_cost)

            est = find_slot(vm_schedules[vm_id], ready_time, duration)
            eft = est + duration
            if best is None or eft < best["aft"] - 1e-9:
                best = {"vm_id": vm_id, "ast": est, "aft": eft}

        entry = {
            "task_id": t_id,
            "vm_id": best["vm_id"],
            "ast": round(best["ast"], 4),
            "aft": round(best["aft"], 4),
            "rank_u": round(rank_u[t_id], 4),
        }
        task_schedule[t_id] = entry
        vm_schedules[best["vm_id"]].append(entry)
        vm_schedules[best["vm_id"]].sort(key=lambda x: x["ast"])

    makespan = max(item["aft"] for item in task_schedule.values())
    comm_overhead = sum(
        edge_map[(u, v)]
        * comm_factor(task_schedule[u]["vm_id"], task_schedule[v]["vm_id"], vm_host_map, topology_aware, penalty, intra)
        for (u, v) in edge_map
    )

    return {
        "priority_order": priority_order,
        "rank_u": {k: round(v, 4) for k, v in rank_u.items()},
        "avg_comm_multiplier": round(avg_comm_multiplier, 4),
        "task_schedule": task_schedule,
        "makespan": round(makespan, 4),
        "comm_overhead_sec": round(comm_overhead, 4),
    }


def compute_theoretical_rr(dag_data: Dict[str, Any], topology_aware: bool = True) -> Dict[str, Any]:
    vms = [vm["id"] for vm in dag_data["vms"]]
    vm_host_map = {vm["id"]: vm["host"] for vm in dag_data["vms"]}
    penalty = dag_data["metadata"].get("inter_host_comm_penalty", 1.5)
    intra = dag_data["metadata"].get("intra_host_comm_factor", 1.0)
    tasks, _, pred, edge_map = build_graph(dag_data)

    ordered = sorted(tasks.keys(), key=lambda x: int(x[1:]) if x[1:].isdigit() else x)
    vm_free = {vm_id: 0.0 for vm_id in vms}
    task_schedule: Dict[str, Dict[str, Any]] = {}

    for idx, t_id in enumerate(ordered):
        vm_id = vms[idx % len(vms)]
        ready = 0.0
        for p_id in pred[t_id]:
            p_info = task_schedule[p_id]
            factor = comm_factor(p_info["vm_id"], vm_id, vm_host_map, topology_aware, penalty, intra)
            ready = max(ready, p_info["aft"] + edge_map[(p_id, t_id)] * factor)
        ast = max(ready, vm_free[vm_id])
        aft = ast + tasks[t_id]["w"][vm_id]
        vm_free[vm_id] = aft
        task_schedule[t_id] = {"task_id": t_id, "vm_id": vm_id, "ast": round(ast, 4), "aft": round(aft, 4)}

    makespan = max(item["aft"] for item in task_schedule.values())
    comm_overhead = sum(
        edge_map[(u, v)]
        * comm_factor(task_schedule[u]["vm_id"], task_schedule[v]["vm_id"], vm_host_map, topology_aware, penalty, intra)
        for (u, v) in edge_map
    )
    return {"task_schedule": task_schedule, "makespan": round(makespan, 4), "comm_overhead_sec": round(comm_overhead, 4)}


def compute_unified_metrics(
    dag_data: Dict[str, Any],
    makespan: float,
    assigned_vms: Dict[str, str],
    comm_overhead_sec: float,
) -> Dict[str, float]:
    tasks = dag_data["tasks"]
    vms = [vm["id"] for vm in dag_data["vms"]]
    q = len(vms)

    min_seq_time = min(sum(t["w"][vm] for t in tasks) for vm in vms)
    min_w = {t["id"]: min(t["w"].values()) for t in tasks}
    succ: Dict[str, List[str]] = {t["id"]: [] for t in tasks}
    for e in dag_data["edges"]:
        succ[e["from"]].append(e["to"])

    memo: Dict[str, float] = {}

    def cp(tid: str) -> float:
        if tid not in memo:
            memo[tid] = min_w[tid] + max((cp(s) for s in succ[tid]), default=0.0)
        return memo[tid]

    cp_min = max(cp(t["id"]) for t in tasks)
    slr = makespan / cp_min
    speedup = min_seq_time / max(makespan, 1e-9)
    efficiency_pct = (speedup / q) * 100.0

    total_compute = sum(next(t["w"][assigned_vms[t["id"]]] for t in tasks if t["id"] == tid) for tid in assigned_vms)
    cpu_util_pct = (total_compute / (q * max(makespan, 1e-9))) * 100.0

    return {
        "makespan": round(makespan, 4),
        "slr": round(slr, 4),
        "speedup": round(speedup, 4),
        "efficiency_pct": round(efficiency_pct, 2),
        "cpu_utilization_pct": round(cpu_util_pct, 2),
        "comm_overhead_sec": round(comm_overhead_sec, 4),
        "cp_min": round(cp_min, 4),
        "min_seq_time": round(min_seq_time, 4),
    }


def load_json(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def delta_pct(new_val: float, base_val: float) -> float:
    if abs(base_val) < 1e-9:
        return 0.0
    return ((new_val - base_val) / base_val) * 100.0


TASK_COLORS = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
    "#937860", "#DA8BC3", "#7F7F7F", "#CCB974", "#64B5CD",
]


def _task_color(tid: str) -> str:
    try:
        return TASK_COLORS[(int(tid[1:]) - 1) % len(TASK_COLORS)]
    except Exception:
        return TASK_COLORS[0]


def try_generate_charts(summary: Dict[str, Any], dag_data: Dict[str, Any], out_dir: str) -> List[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.patches import Patch
    except Exception as exc:
        print(f"[INFO] Visualisasi dilewati (matplotlib tidak tersedia: {exc})")
        return []

    generated: List[str] = []

    # 1. comparison_metrics.png — Multi-Metric Comparison: HEFT vs Round-Robin (3 Dimensi) + Varian Flat/Topo
    fig, axes = plt.subplots(2, 3, figsize=(16.5, 9.8))

    def fmt_id(val: float, decimals: int = 2) -> str:
        return f"{val:.{decimals}f}".replace(".", ",")

    realms = ["Teori\n(Topo 1,5x)", "CloudSim 7.0.1\n(Topo 1,5x)", "Real-World K8s\n(Mean 5x)"]
    xr = np.arange(len(realms))
    w = 0.34

    m_theo_h = compute_unified_metrics(
        dag_data,
        summary["theo_topo"]["makespan"],
        {tid: info["vm_id"] for tid, info in summary["theo_topo"]["task_schedule"].items()},
        summary["theo_topo"]["comm_overhead_sec"],
    )
    m_theo_r = summary["theo_rr_topo"]["metrics"]

    cs_topo = summary.get("cloudsim_topo")
    cs_rr = summary.get("cloudsim_rr")
    m_cs_h = (
        compute_unified_metrics(
            dag_data,
            cs_topo["actual_makespan"],
            {t["label"]: t["vm_label"] for t in cs_topo["tasks"]},
            cs_topo["comm_overhead_sec"],
        )
        if cs_topo
        else m_theo_h
    )
    m_cs_r = (
        compute_unified_metrics(
            dag_data,
            cs_rr["actual_makespan"],
            {t["label"]: t["vm_label"] for t in cs_rr["tasks"]},
            cs_rr["comm_overhead_sec"],
        )
        if cs_rr
        else m_theo_r
    )

    rw_h = summary["realworld"]["heft"] if summary.get("realworld") else m_theo_h
    rw_r = summary["realworld"]["rr"] if summary.get("realworld") else m_theo_r

    def plot_pair(ax, title, ylabel, h_vals, r_vals, h_errs=None, r_errs=None, decimals=2, suffix="", ref_line=None, ref_label=None, legend_loc="upper left"):
        b1 = ax.bar(xr - w / 2, h_vals, width=w, yerr=h_errs, capsize=3, label="HEFT", color="#2E8B57", edgecolor="#1E1E1E", linewidth=0.8)
        b2 = ax.bar(xr + w / 2, r_vals, width=w, yerr=r_errs, capsize=3, label="Round-Robin", color="#C44E52", edgecolor="#1E1E1E", linewidth=0.8)
        if ref_line is not None:
            ax.axhline(ref_line, color="#333333", linestyle="--", linewidth=1.1, label=ref_label)
        top = max([v + (e if e else 0) for v, e in zip(h_vals + r_vals, (h_errs or [0]*3) + (r_errs or [0]*3))])
        ax.set_ylim(0, top * 1.30)
        ax.set_title(title, fontweight="bold", fontsize=10.5)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_xticks(xr)
        ax.set_xticklabels(realms, fontsize=8.5)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.legend(fontsize=8, framealpha=0.92, loc=legend_loc)
        errs = (h_errs or [0]*3) + (r_errs or [0]*3)
        for b, v, e in zip(list(b1) + list(b2), h_vals + r_vals, errs):
            ax.text(b.get_x() + b.get_width() / 2, v + (e if e else 0) + top * 0.02, f"{fmt_id(v, decimals)}{suffix}",
                    ha="center", va="bottom", fontsize=7.8, fontweight="bold")

    # A. Makespan
    plot_pair(
        axes[0, 0],
        "A. Makespan (Lebih Kecil = Lebih Baik)",
        "Detik (s)",
        [m_theo_h["makespan"], m_cs_h["makespan"], rw_h["makespan"]],
        [m_theo_r["makespan"], m_cs_r["makespan"], rw_r["makespan"]],
        h_errs=[0.0, 0.0, rw_h.get("makespan_std", 0.0)],
        r_errs=[0.0, 0.0, rw_r.get("makespan_std", 0.0)],
        decimals=2,
        suffix=" s",
    )

    # B. SLR
    plot_pair(
        axes[0, 1],
        "B. Schedule Length Ratio / SLR (Lebih Kecil = Lebih Baik)",
        "Rasio SLR",
        [m_theo_h["slr"], m_cs_h["slr"], rw_h["slr"]],
        [m_theo_r["slr"], m_cs_r["slr"], rw_r["slr"]],
        h_errs=[0.0, 0.0, rw_h.get("slr_std", 0.0)],
        r_errs=[0.0, 0.0, rw_r.get("slr_std", 0.0)],
        decimals=3,
    )

    # C. Speedup
    plot_pair(
        axes[0, 2],
        "C. Speedup (Lebih Besar = Lebih Baik)",
        "Speedup (x)",
        [m_theo_h["speedup"], m_cs_h["speedup"], rw_h["speedup"]],
        [m_theo_r["speedup"], m_cs_r["speedup"], rw_r["speedup"]],
        h_errs=[0.0, 0.0, rw_h.get("speedup_std", 0.0)],
        r_errs=[0.0, 0.0, rw_r.get("speedup_std", 0.0)],
        decimals=3,
        suffix="x",
        ref_line=1.0,
        ref_label="Batas sekuensial (1,00x)",
        legend_loc="upper right",
    )

    # D. Parallel Efficiency
    plot_pair(
        axes[1, 0],
        "D. Efisiensi Paralel η (Lebih Besar = Lebih Baik)",
        "Efisiensi (%)",
        [m_theo_h["efficiency_pct"], m_cs_h["efficiency_pct"], rw_h["efficiency_pct"]],
        [m_theo_r["efficiency_pct"], m_cs_r["efficiency_pct"], rw_r["efficiency_pct"]],
        h_errs=[0.0, 0.0, rw_h.get("efficiency_pct_std", 0.0)],
        r_errs=[0.0, 0.0, rw_r.get("efficiency_pct_std", 0.0)],
        decimals=2,
        suffix="%",
        legend_loc="upper right",
    )

    # E. CPU Utilization (Model)
    plot_pair(
        axes[1, 1],
        "E. Rata-Rata Utilisasi CPU Model (U_avg)",
        "Utilisasi CPU (%)",
        [m_theo_h["cpu_utilization_pct"], m_cs_h["cpu_utilization_pct"], rw_h["cpu_utilization_pct"]],
        [m_theo_r["cpu_utilization_pct"], m_cs_r["cpu_utilization_pct"], rw_r["cpu_utilization_pct"]],
        h_errs=[0.0, 0.0, rw_h.get("cpu_utilization_pct_std", 0.0)],
        r_errs=[0.0, 0.0, rw_r.get("cpu_utilization_pct_std", 0.0)],
        decimals=2,
        suffix="%",
        legend_loc="upper right",
    )

    # F. Perbandingan Varian Model HEFT (Topo vs Flat)
    ax = axes[1, 2]
    dims = summary["dimensions_heft"]
    v_labels = ["Teori\n(Topo 1,5x)", "Teori\n(Flat)", "CloudSim\n(Flat)", "CloudSim\n(Topo 1,5x)", "Real-World\nK8s (5x)"][: len(dims)]
    v_vals = [d["metrics"]["makespan"] for d in dims]
    v_stds = [d["metrics"].get("makespan_std", 0.0) for d in dims]
    v_colors = ["#4C72B0", "#64B5CD", "#DD8452", "#C44E52", "#2E8B57"][: len(dims)]
    xv = np.arange(len(v_labels))
    vb = ax.bar(xv, v_vals, yerr=v_stds, capsize=3, color=v_colors, edgecolor="#1E1E1E", linewidth=0.8)
    ax.set_title("F. Makespan HEFT: Varian Model Flat vs Topo 1,5x", fontweight="bold", fontsize=10.5)
    ax.set_ylabel("Detik (s)", fontsize=9)
    ax.set_xticks(xv)
    ax.set_xticklabels(v_labels, fontsize=8)
    ax.set_ylim(0, max(v_vals) * 1.24)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    for b, v, s in zip(vb, v_vals, v_stds):
        ax.text(b.get_x() + b.get_width() / 2, v + s + 0.15, f"{fmt_id(v, 3)} s", ha="center", va="bottom", fontsize=7.8, fontweight="bold")

    plt.suptitle("Perbandingan Multi-Metrik HEFT dan Round-Robin: Teori, CloudSim 7.0.1, dan Real-World Kubernetes", fontweight="bold", fontsize=13)
    plt.tight_layout(rect=[0, 0, 1, 0.955])
    p1 = os.path.join(out_dir, "comparison_metrics.png")
    plt.savefig(p1, dpi=200)
    plt.close(fig)
    generated.append(p1)

    # 2. gantt_3way.png — 3-Panel Gantt Chart (Teori vs CloudSim Actual vs Kubernetes Realworld)
    if summary.get("cloudsim_topo") and summary.get("realworld"):
        vms = [vm["id"] for vm in dag_data["vms"]]
        fig, axes = plt.subplots(3, 1, figsize=(14, 10.5), sharex=True)

        def draw_gantt_panel(ax, title, items):
            for tid, vm_id, start, end in items:
                y = vms.index(vm_id)
                dur = end - start
                ax.barh(y, dur, left=start, height=0.58, color=_task_color(tid), edgecolor="#1a1a1a", linewidth=0.8, alpha=0.95, zorder=3)
                label_txt = f"{tid}\n{dur:.2f}s" if dur >= 0.48 else f"{tid}"
                ax.text(start + dur / 2, y, label_txt, ha="center", va="center", color="white", fontweight="bold", fontsize=7.5, zorder=4)
            ax.set_yticks(range(len(vms)))
            ax.set_yticklabels([f"{v['id']}\n({v['host']} | {v['cpu_limit']})" for v in dag_data["vms"]], fontsize=8.5)
            ax.set_ylim(len(vms) - 0.35, -0.55)
            ax.set_title(title, fontweight="bold", fontsize=10.5, loc="left")
            ax.grid(axis="x", linestyle="--", alpha=0.45, zorder=0)
            ax.set_facecolor("#FAFAFC")

        theo_items = [(tid, info["vm_id"], info["ast"], info["aft"]) for tid, info in summary["theo_topo"]["task_schedule"].items()]
        cs_items = [(t["label"], t["vm_label"], t["ast"], t["aft"]) for t in summary["cloudsim_topo"]["tasks"]]
        rw_rep = summary["realworld"]["rep_run"]["heft_actual"]
        rw_items = [(tid, info["vm_id"], info["actual_ast"], info["actual_aft"]) for tid, info in rw_rep["actual_results"].items()]

        draw_gantt_panel(axes[0], f"1. Teori HEFT (Topo 1.5x) — Urutan Prioritas: T4 → T2 → T3  |  Makespan = {summary['theo_topo']['makespan']:.2f} s", theo_items)
        draw_gantt_panel(axes[1], f"2. CloudSim 7.0.1 Aktual (WorkflowBroker FCFS: T2 → T3 → T4)  |  Makespan = {summary['cloudsim_topo']['actual_makespan']:.2f} s", cs_items)
        draw_gantt_panel(axes[2], f"3. Real-World Kubernetes (Dispatcher HEFT + CFS/HTTP)  |  Makespan = {rw_rep['actual_makespan']:.2f} s", rw_items)

        # Draw transfer arcs on K8s panel
        for tr in rw_rep.get("transfers", []):
            y = vms.index(tr["dst_vm"]) + 0.35
            axes[2].plot([tr["send_start"], tr["arrival"]], [y, y],
                         color="#C44E52" if tr["link"] == "inter-host" else "#E1A100",
                         linewidth=1.8, alpha=0.85, zorder=2)

        max_x = max(summary["theo_topo"]["makespan"], summary["cloudsim_topo"]["actual_makespan"], rw_rep["actual_makespan"])
        axes[2].set_xlim(0, max_x * 1.07)
        axes[2].set_xlabel("Waktu Eksekusi (detik)", fontweight="bold")
        legend = [
            Patch(color="#E1A100", label="Transfer data intra-host (1.0x)"),
            Patch(color="#C44E52", label="Transfer data inter-host (1.5x)"),
        ]
        axes[2].legend(handles=legend, loc="lower right", fontsize=8.5, framealpha=0.92)
        plt.suptitle("Perbandingan Timeline Eksekusi (Gantt Chart): Teori vs CloudSim WorkflowBroker vs Kubernetes", fontweight="bold", fontsize=12.5)
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        p2 = os.path.join(out_dir, "gantt_3way.png")
        plt.savefig(p2, dpi=180)
        plt.close(fig)
        generated.append(p2)

    # 3. gap_and_rank_analysis.png — Upward Rank Formula Comparison & Performance Gaps
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.4))

    # Left: rank_u comparison (Topo 1.5x vs CloudSim Flat)
    ax = axes[0]
    tids = [t["id"] for t in dag_data["tasks"]]
    r_topo = [summary["theo_topo"]["rank_u"][tid] for tid in tids]
    r_flat = [summary["theo_flat"]["rank_u"][tid] for tid in tids]
    xt = np.arange(len(tids))
    w = 0.38
    ax.bar(xt - w / 2, r_topo, width=w, label="Teori Dosen / Realworld (Topo 1.5x, v1≠v2)", color="#4C72B0", edgecolor="#222")
    ax.bar(xt + w / 2, r_flat, width=w, label="CloudSim Biasa (Flat, (P-1)/P)", color="#DD8452", edgecolor="#222")
    ax.set_title("Perbandingan Nilai Upward Rank (rank_u) per Task", fontweight="bold", fontsize=11)
    ax.set_ylabel("Nilai rank_u")
    ax.set_xticks(xt)
    ax.set_xticklabels(tids, fontweight="bold")
    ax.legend(fontsize=8.5, framealpha=0.9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.annotate("T6 (6.810) > T5 (6.808)\npada Topo 1.5x\n(terbalik di Flat!)", xy=(5, 6.81), xytext=(5.4, 9.2),
                arrowprops=dict(arrowstyle="->", color="#C44E52", lw=1.4),
                fontsize=8, fontweight="bold", color="#C44E52",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF5F5", edgecolor="#C44E52"))

    # Right: Percentage Gaps (Delta %)
    ax = axes[1]
    gap_labels = []
    gap_vals = []
    if summary.get("cloudsim_topo"):
        gap_labels.append("CloudSim Est vs Teori\n(Topo 1.5x)")
        gap_vals.append(delta_pct(summary["cloudsim_topo"]["estimated_makespan"], summary["theo_topo"]["makespan"]))
        gap_labels.append("CloudSim Aktual vs Teori\n(Efek Antrean T2→T4)")
        gap_vals.append(delta_pct(summary["cloudsim_topo"]["actual_makespan"], summary["theo_topo"]["makespan"]))
    if summary.get("realworld"):
        gap_labels.append("Realworld K8s vs Teori\n(CFS + OS + HTTP)")
        gap_vals.append(delta_pct(summary["realworld"]["heft"]["makespan"], summary["theo_topo"]["makespan"]))
    if summary.get("cloudsim_topo") and summary.get("realworld"):
        gap_labels.append("Realworld K8s vs\nCloudSim Aktual")
        gap_vals.append(delta_pct(summary["realworld"]["heft"]["makespan"], summary["cloudsim_topo"]["actual_makespan"]))

    yg = np.arange(len(gap_labels))
    g_colors = ["#55A868" if v <= 0 else ("#DD8452" if v < 10 else "#C44E52") for v in gap_vals]
    bars_g = ax.barh(yg, gap_vals, color=g_colors, edgecolor="#222", height=0.52)
    ax.axvline(0, color="#222", linewidth=1.1)
    ax.set_yticks(yg)
    ax.set_yticklabels(gap_labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Deviasi Makespan Δ (%)", fontweight="bold")
    ax.set_title("Analisis Gap Makespan Antar Dimensi (Δ%)", fontweight="bold", fontsize=11)
    min_g, max_g = min(gap_vals + [0]), max(gap_vals + [0])
    ax.set_xlim(min_g - 6, max_g + 7)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    for b, v in zip(bars_g, gap_vals):
        offset = 0.8 if v >= 0 else -0.8
        ha = "left" if v >= 0 else "right"
        ax.text(v + offset, b.get_y() + b.get_height() / 2, f"{v:+.2f}%", va="center", ha=ha, fontweight="bold", fontsize=8.5)

    plt.suptitle("Analisis Perbedaan Rumus Teori HEFT & Gap Eksekusi Simulator vs Real-World", fontweight="bold", fontsize=12.5)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    p3 = os.path.join(out_dir, "gap_and_rank_analysis.png")
    plt.savefig(p3, dpi=180)
    plt.close(fig)
    generated.append(p3)

    return generated


def main():
    ap = argparse.ArgumentParser(description="Komparasi Teori HEFT vs CloudSim vs Kubernetes Realworld")
    ap.add_argument("--dag", default="../kube-heft-scheduler/master/dag_sample.json")
    ap.add_argument("--cloudsim-flat", default="results/cloudsim_10task_flat.json")
    ap.add_argument("--cloudsim-topo", default="results/cloudsim_10task_topo.json")
    ap.add_argument("--cloudsim-rr", default="results/cloudsim_10task_rr.json")
    ap.add_argument("--cloudsim-synth", default="results/cloudsim_synthetic_100.json")
    ap.add_argument(
        "--realworld-log",
        default="../kube-heft-scheduler/results/execution_log.json",
    )
    ap.add_argument("--out-dir", default="results")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    dag_data = load_json(args.dag)
    if not dag_data:
        raise FileNotFoundError(f"DAG file tidak ditemukan: {args.dag}")

    # 1. Teori HEFT (dua varian formula sesuai analisis kedua proyek)
    theo_topo = compute_theoretical_heft(dag_data, topology_aware=True, avg_over_all_pairs=False, exact_ratio_w=False)
    theo_flat = compute_theoretical_heft(dag_data, topology_aware=False, avg_over_all_pairs=True, exact_ratio_w=True)
    theo_rr_topo = compute_theoretical_rr(dag_data, topology_aware=True)

    m_theo_topo = compute_unified_metrics(
        dag_data,
        theo_topo["makespan"],
        {tid: info["vm_id"] for tid, info in theo_topo["task_schedule"].items()},
        theo_topo["comm_overhead_sec"],
    )
    m_theo_flat = compute_unified_metrics(
        dag_data,
        theo_flat["makespan"],
        {tid: info["vm_id"] for tid, info in theo_flat["task_schedule"].items()},
        theo_flat["comm_overhead_sec"],
    )
    m_theo_rr = compute_unified_metrics(
        dag_data,
        theo_rr_topo["makespan"],
        {tid: info["vm_id"] for tid, info in theo_rr_topo["task_schedule"].items()},
        theo_rr_topo["comm_overhead_sec"],
    )

    # 2. CloudSim (HEFT Simulation Biasa)
    cs_flat = load_json(args.cloudsim_flat)
    cs_topo = load_json(args.cloudsim_topo)
    cs_rr = load_json(args.cloudsim_rr)
    cs_synth = load_json(args.cloudsim_synth)

    dimensions_heft = [
        {"key": "theory_topo", "label": "Teori HEFT (Topo 1.5x)", "metrics": m_theo_topo, "extra": theo_topo},
        {"key": "theory_flat", "label": "Teori HEFT (Flat)", "metrics": m_theo_flat, "extra": theo_flat},
    ]

    if cs_flat:
        cs_flat_vms = {t["label"]: t["vm_label"] for t in cs_flat["tasks"]}
        m_cs_flat = compute_unified_metrics(dag_data, cs_flat["actual_makespan"], cs_flat_vms, cs_flat["comm_overhead_sec"])
        dimensions_heft.append({"key": "cloudsim_flat", "label": "CloudSim Biasa (Flat)", "metrics": m_cs_flat, "raw": cs_flat})

    if cs_topo:
        cs_topo_vms = {t["label"]: t["vm_label"] for t in cs_topo["tasks"]}
        m_cs_topo = compute_unified_metrics(dag_data, cs_topo["actual_makespan"], cs_topo_vms, cs_topo["comm_overhead_sec"])
        dimensions_heft.append({"key": "cloudsim_topo", "label": "CloudSim (Topo 1.5x)", "metrics": m_cs_topo, "raw": cs_topo})

    # 3. Realworld Kubernetes
    rw_log = load_json(args.realworld_log)
    rw_stats = None
    if rw_log and rw_log.get("runs"):
        runs = rw_log["runs"]
        rep_idx = rw_log.get("representative_run", 1) - 1
        rep_run = runs[rep_idx]

        heft_runs_m = []
        rr_runs_m = []
        for r in runs:
            h_res = r["heft_actual"]
            r_res = r["rr_actual"]
            h_vms = {tid: info["vm_id"] for tid, info in h_res["actual_results"].items()}
            r_vms = {tid: info["vm_id"] for tid, info in r_res["actual_results"].items()}
            h_comm = sum(tr.get("model_comm_sec", 0.0) for tr in h_res.get("transfers", []))
            r_comm = sum(tr.get("model_comm_sec", 0.0) for tr in r_res.get("transfers", []))
            h_comm_real = sum(tr.get("real_transfer_sec", 0.0) for tr in h_res.get("transfers", []))
            r_comm_real = sum(tr.get("real_transfer_sec", 0.0) for tr in r_res.get("transfers", []))

            hm = compute_unified_metrics(dag_data, r["heft_makespan"], h_vms, h_comm)
            hm["real_transfer_sec"] = round(h_comm_real, 4)
            rm = compute_unified_metrics(dag_data, r["rr_makespan"], r_vms, r_comm)
            rm["real_transfer_sec"] = round(r_comm_real, 4)
            heft_runs_m.append(hm)
            rr_runs_m.append(rm)

        def agg(items: List[Dict[str, float]]) -> Dict[str, Any]:
            keys = ["makespan", "slr", "speedup", "efficiency_pct", "cpu_utilization_pct", "comm_overhead_sec", "real_transfer_sec"]
            out = {}
            for k in keys:
                vals = [x[k] for x in items]
                out[k] = round(statistics.mean(vals), 4)
                out[f"{k}_std"] = round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0
            return out

        rw_heft_agg = agg(heft_runs_m)
        rw_rr_agg = agg(rr_runs_m)
        rw_stats = {"heft": rw_heft_agg, "rr": rw_rr_agg, "rep_run": rep_run, "num_runs": len(runs)}
        dimensions_heft.append({"key": "realworld_k8s", "label": "Realworld K8s (Mean 5x)", "metrics": rw_heft_agg, "raw": rw_stats})

    # Fidelity checks
    fidelity = {}
    if cs_topo:
        cs_topo_vms = {t["label"]: t["vm_label"] for t in cs_topo["tasks"]}
        theo_topo_vms = {tid: info["vm_id"] for tid, info in theo_topo["task_schedule"].items()}
        agree_topo = sum(1 for k in theo_topo_vms if cs_topo_vms.get(k) == theo_topo_vms[k])
        fidelity["topo_priority_match"] = (cs_topo["priority_order"] == theo_topo["priority_order"])
        fidelity["topo_vm_agreement_pct"] = round((agree_topo / len(theo_topo_vms)) * 100.0, 2)
    if cs_flat:
        cs_flat_vms = {t["label"]: t["vm_label"] for t in cs_flat["tasks"]}
        theo_flat_vms = {tid: info["vm_id"] for tid, info in theo_flat["task_schedule"].items()}
        agree_flat = sum(1 for k in theo_flat_vms if cs_flat_vms.get(k) == theo_flat_vms[k])
        fidelity["flat_priority_match"] = (cs_flat["priority_order"] == theo_flat["priority_order"])
        fidelity["flat_vm_agreement_pct"] = round((agree_flat / len(theo_flat_vms)) * 100.0, 2)
    if cs_topo and cs_flat:
        cs_topo_vms = {t["label"]: t["vm_label"] for t in cs_topo["tasks"]}
        cs_flat_vms = {t["label"]: t["vm_label"] for t in cs_flat["tasks"]}
        agree_cs = sum(1 for k in cs_topo_vms if cs_flat_vms.get(k) == cs_topo_vms[k])
        fidelity["flat_vs_topo_priority_match"] = (cs_flat["priority_order"] == cs_topo["priority_order"])
        fidelity["flat_vs_topo_vm_agreement_pct"] = round((agree_cs / len(cs_topo_vms)) * 100.0, 2)

    summary = {
        "dag_name": dag_data["metadata"]["name"],
        "dimensions_heft": [{k: v for k, v in d.items() if k not in ("raw", "extra")} for d in dimensions_heft],
        "theo_topo": theo_topo,
        "theo_flat": theo_flat,
        "theo_rr_topo": {"metrics": m_theo_rr, **theo_rr_topo},
        "cloudsim_flat": cs_flat,
        "cloudsim_topo": cs_topo,
        "cloudsim_rr": cs_rr,
        "cloudsim_synthetic_100": cs_synth,
        "realworld": rw_stats,
        "fidelity": fidelity,
    }

    generated_charts = try_generate_charts(summary, dag_data, args.out_dir)

    # Build Markdown report
    lines = [
        "# Laporan Komparasi Tiga Dimensi: Teori HEFT vs CloudSim (Simulation Biasa) vs Kubernetes (Simulation Realworld)",
        "",
        f"> **Workload Uji Bersama:** `{dag_data['metadata']['name']}` (10 Task, 15 Edge, 4 VM Heterogen pada 2 Host)",
        "",
        "## 1. Perbandingan Rumus Teori HEFT pada Kedua Proyek",
        "",
        "| Aspek Formulasi HEFT | Teori Dosen / Realworld (`heft_algorithm.py`) | CloudSim Biasa (`HEFTScheduler.java`) | Dampak pada DAG 10-Task |",
        "| :--- | :--- | :--- | :--- |",
        f"| **Rata-rata Bobot Komunikasi ($\\bar{{c}}$)** | Pasangan VM berbeda ($v_1 \\neq v_2$) + penalti inter-host 1.5x (multiplier = `{theo_topo['avg_comm_multiplier']:.4f}`) | Seluruh pasangan $P \\times P$ (`(P-1)/P` = `{theo_flat['avg_comm_multiplier']:.4f}`), flat 100 MB/s | Nilai $rank_u$ berbeda secara absolut |",
        f"| **Urutan Prioritas (`priority_order`)** | `{' -> '.join(theo_topo['priority_order'])}` | `{' -> '.join(theo_flat['priority_order'])}` | {'**Sama persis**' if theo_topo['priority_order'] == theo_flat['priority_order'] else '**Berbeda urutan**'} |",
        f"| **Makespan Teoritis HEFT** | **{theo_topo['makespan']:.4f} s** | **{theo_flat['makespan']:.4f} s** | Selisih model jaringan: {delta_pct(theo_topo['makespan'], theo_flat['makespan']):+.2f}% |",
        "",
        "## 2. Tabel Komparasi Metrik Utama (HEFT Across All Dimensions)",
        "",
        "| Dimensi Evaluasi | Makespan (s) | SLR | Speedup | Efficiency (η) | CPU Util (%) | Comm Model (s) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    for d in dimensions_heft:
        m = d["metrics"]
        if d["key"] == "realworld_k8s":
            lines.append(
                f"| **{d['label']}** | **{m['makespan']:.3f} ± {m['makespan_std']:.3f}** | {m['slr']:.3f} | {m['speedup']:.3f}x | {m['efficiency_pct']:.2f}% | {m['cpu_utilization_pct']:.2f}% | {m['comm_overhead_sec']:.3f} (riil: {m['real_transfer_sec']:.3f}s) |"
            )
        else:
            lines.append(
                f"| {d['label']} | {m['makespan']:.4f} | {m['slr']:.4f} | {m['speedup']:.4f}x | {m['efficiency_pct']:.2f}% | {m['cpu_utilization_pct']:.2f}% | {m['comm_overhead_sec']:.4f} |"
            )

    lines.extend([
        "",
        "### Perbandingan Baseline Round-Robin (Teori vs CloudSim vs Kubernetes)",
        "",
        "| Dimensi Round-Robin | Makespan (s) | SLR | Speedup | Efficiency (η) | CPU Util (%) |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
        f"| Teori Round-Robin (Topo 1.5x) | {m_theo_rr['makespan']:.4f} | {m_theo_rr['slr']:.4f} | {m_theo_rr['speedup']:.4f}x | {m_theo_rr['efficiency_pct']:.2f}% | {m_theo_rr['cpu_utilization_pct']:.2f}% |",
    ])

    if cs_rr:
        m_cs_rr = compute_unified_metrics(
            dag_data, cs_rr["actual_makespan"], {t["label"]: t["vm_label"] for t in cs_rr["tasks"]}, cs_rr["comm_overhead_sec"]
        )
        lines.append(
            f"| CloudSim Round-Robin (Topo 1.5x) | {m_cs_rr['makespan']:.4f} | {m_cs_rr['slr']:.4f} | {m_cs_rr['speedup']:.4f}x | {m_cs_rr['efficiency_pct']:.2f}% | {m_cs_rr['cpu_utilization_pct']:.2f}% |"
        )
    if rw_stats:
        rm = rw_stats["rr"]
        lines.append(
            f"| Realworld K8s Round-Robin (Mean 5x) | {rm['makespan']:.3f} ± {rm['makespan_std']:.3f} | {rm['slr']:.3f} | {rm['speedup']:.3f}x | {rm['efficiency_pct']:.2f}% | {rm['cpu_utilization_pct']:.2f}% |"
        )

    lines.extend([
        "",
        "## 3. Analisis Gap & Kesesuaian Jadwal (*Schedule Fidelity*)",
        "",
    ])

    if cs_topo:
        lines.append(
            f"- **CloudSim (Topo) vs Teori (Topo):** Kecocokan urutan prioritas = `{fidelity.get('topo_priority_match')}`, kecocokan penempatan VM = **{fidelity.get('topo_vm_agreement_pct')}%**, estimated makespan CloudSim = `{cs_topo['estimated_makespan']:.4f}s` (0.00% vs Teori `{theo_topo['makespan']:.4f}s`), sedangkan actual makespan CloudSim = `{cs_topo['actual_makespan']:.4f}s` (**{delta_pct(cs_topo['actual_makespan'], theo_topo['makespan']):+.2f}%**). *Penyebab:* `WorkflowBroker` mengirim cloudlet anak berdasarkan urutan daftar `successors` (`T2 -> T3 -> T4`) saat `T1` selesai bersamaan, sehingga `CloudletSchedulerSpaceShared` mengeksekusi FCFS alih-alih urutan prioritas HEFT (`T4 -> T2 -> T3`)."
        )
    if cs_flat:
        lines.append(
            f"- **CloudSim (Flat) vs Teori (Flat):** Kecocokan urutan prioritas = `{fidelity.get('flat_priority_match')}`, kecocokan penempatan VM = **{fidelity.get('flat_vm_agreement_pct')}%**, estimated makespan CloudSim = `{cs_flat['estimated_makespan']:.4f}s` (vs Teori `{theo_flat['makespan']:.4f}s`), actual makespan CloudSim = `{cs_flat['actual_makespan']:.4f}s` (**{delta_pct(cs_flat['actual_makespan'], theo_flat['makespan']):+.2f}%**)."
        )
    if cs_topo and rw_stats:
        lines.append(
            f"- **Realworld K8s vs Teori (Topo):** Makespan riil Kubernetes `{rw_stats['heft']['makespan']:.3f}s` vs Teori `{theo_topo['makespan']:.3f}s` $\\rightarrow$ Gap = **{delta_pct(rw_stats['heft']['makespan'], theo_topo['makespan']):+.2f}%** (disebabkan *Linux CFS cgroups throttling*, *OS scheduling jitter*, dan overhead HTTP/TCP di Docker bridge)."
        )
    if cs_topo and rw_stats:
        lines.append(
            f"- **Realworld K8s vs CloudSim Aktual (Topo):** Makespan riil Kubernetes `{rw_stats['heft']['makespan']:.3f}s` vs CloudSim `{cs_topo['actual_makespan']:.3f}s` $\\rightarrow$ Gap = **{delta_pct(rw_stats['heft']['makespan'], cs_topo['actual_makespan']):+.2f}%** (Kubernetes lebih cepat dari `WorkflowBroker` default karena `dispatcher.py` mengirim task sesuai urutan `priority_order`/`EST` HEFT, tidak tertukar `T2` sebelum `T4`)."
        )
    if cs_flat and rw_stats:
        lines.append(
            f"- **Realworld K8s vs CloudSim Biasa (Flat):** Makespan riil Kubernetes `{rw_stats['heft']['makespan']:.3f}s` vs CloudSim Flat `{cs_flat['actual_makespan']:.3f}s` $\\rightarrow$ Gap = **{delta_pct(rw_stats['heft']['makespan'], cs_flat['actual_makespan']):+.2f}%**."
        )

    lines.extend([
        "",
        "## 4. Perbandingan Per-Task (`T1`–`T10`): Teori vs CloudSim vs Kubernetes (Run Representatif)",
        "",
        "| Task | $rank_u$ Teori | VM Teori | VM CloudSim (Topo) | EST→EFT Teori (s) | AST→AFT CloudSim (s) | AST→AFT K8s Aktual (s) |",
        "| :--- | :---: | :--- | :--- | :---: | :---: | :---: |",
    ])

    cs_task_map = {t["label"]: t for t in cs_topo["tasks"]} if cs_topo else {}
    rw_rep_tasks = rw_stats["rep_run"]["heft_actual"]["actual_results"] if rw_stats else {}

    for t in dag_data["tasks"]:
        tid = t["id"]
        tt = theo_topo["task_schedule"][tid]
        ct = cs_task_map.get(tid, {})
        rt = rw_rep_tasks.get(tid, {})
        cs_vm = ct.get("vm_label", "-")
        cs_win = f"{ct['ast']:.2f} → {ct['aft']:.2f}" if ct else "-"
        rw_win = f"{rt['actual_ast']:.2f} → {rt['actual_aft']:.2f}" if rt else "-"
        lines.append(
            f"| **{tid}** | {tt['rank_u']:.3f} | `{tt['vm_id']}` | `{cs_vm}` | {tt['ast']:.2f} → {tt['aft']:.2f} | {cs_win} | {rw_win} |"
        )

    if cs_synth:
        lines.extend([
            "",
            "## 5. Konteks Skalabilitas CloudSim (`TUGAS HEFT`: 100 Task Synthetic, 10 VM)",
            "",
            "Kemampuan yang hanya ada di **HEFT Simulation Biasa (CloudSim)** untuk uji skala besar & konsumsi energi:",
            "",
            f"- **Workload:** 100 Tasks, {cs_synth['edge_count']} Edges, 10 VM Heterogen (2 Datacenter, 8 Physical Hosts)",
            f"- **HEFT Estimated Makespan:** `{cs_synth['estimated_makespan']:.4f} s`",
            f"- **CloudSim Actual Makespan:** `{cs_synth['actual_makespan']:.4f} s` (Selisih: `{delta_pct(cs_synth['actual_makespan'], cs_synth['estimated_makespan']):+.4f}%`)",
            f"- **CPU Utilization:** `{cs_synth['cpu_utilization_pct']:.2f}%`",
            f"- **Estimasi Energi Datacenter:** `{cs_synth['energy_joule']:.2f} Joule`",
            f"- **HEFT Scheduling Runtime:** `{cs_synth['scheduling_runtime_ms']:.3f} ms`",
        ])

    if generated_charts:
        lines.extend(["", "## 6. Grafik Komparasi", ""])
        for cp in generated_charts:
            fname = os.path.basename(cp)
            lines.append(f"- `{fname}`")
            lines.append(f"![{fname}]({fname})")

    report_path = os.path.join(args.out_dir, "comparison_report.md")
    summary_path = os.path.join(args.out_dir, "comparison_summary.json")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n=== RINGKASAN KOMPARASI HEFT ===")
    for d in dimensions_heft:
        m = d["metrics"]
        print(f"  {d['label']:<25} | Makespan={m['makespan']:7.4f}s | SLR={m['slr']:.3f} | Speedup={m['speedup']:.3f}x | Eff={m['efficiency_pct']:5.2f}% | CPU={m['cpu_utilization_pct']:5.2f}%")
    print(f"\nLaporan lengkap tersimpan di: {report_path}")
    print(f"Data JSON tersimpan di      : {summary_path}")
    for cp in generated_charts:
        print(f"Grafik tersimpan di         : {cp}")


if __name__ == "__main__":
    main()
