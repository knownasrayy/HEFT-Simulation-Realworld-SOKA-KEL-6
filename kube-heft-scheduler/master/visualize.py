"""Visualisasi Gantt Chart & laporan evaluasi Markdown."""
import statistics
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

TASK_COLORS = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
    "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
]


def compute_metrics(dag_data: Dict[str, Any], makespan: float) -> Dict[str, float]:
    tasks = dag_data["tasks"]
    vms = [vm["id"] for vm in dag_data["vms"]]

    # Waktu eksekusi sekuensial minimum pada satu VM (pembilang Speedup)
    min_seq_time = min(sum(t["w"][vm_id] for t in tasks) for vm_id in vms)

    # CP_MIN: jalur kritis DAG dengan bobot min_p(w_{i,p}) (penyebut SLR)
    min_w = {t["id"]: min(t["w"].values()) for t in tasks}
    succ: Dict[str, List[str]] = {t["id"]: [] for t in tasks}
    for e in dag_data["edges"]:
        succ[e["from"]].append(e["to"])
    memo: Dict[str, float] = {}

    def cp(t_id: str) -> float:
        if t_id not in memo:
            memo[t_id] = min_w[t_id] + max((cp(s) for s in succ[t_id]), default=0.0)
        return memo[t_id]

    cp_min_sum = max(cp(t["id"]) for t in tasks)
    return {
        "makespan": round(makespan, 4),
        "slr": round(makespan / cp_min_sum, 4),
        "speedup": round(min_seq_time / makespan, 4),
        "cp_min_sum": round(cp_min_sum, 4),
        "min_seq_time": round(min_seq_time, 4),
    }


def critical_path(dag_data: Dict[str, Any]) -> List[str]:
    tasks = dag_data["tasks"]
    min_w = {t["id"]: min(t["w"].values()) for t in tasks}
    succ: Dict[str, List[str]] = {t["id"]: [] for t in tasks}
    has_pred = set()
    for e in dag_data["edges"]:
        succ[e["from"]].append(e["to"])
        has_pred.add(e["to"])
    memo: Dict[str, float] = {}

    def cp(t_id: str) -> float:
        if t_id not in memo:
            memo[t_id] = min_w[t_id] + max((cp(s) for s in succ[t_id]), default=0.0)
        return memo[t_id]

    cur = max((t["id"] for t in tasks if t["id"] not in has_pred), key=cp)
    path = [cur]
    while succ[cur]:
        cur = max(succ[cur], key=cp)
        path.append(cur)
    return path


def _task_color(t_id: str) -> str:
    try:
        return TASK_COLORS[(int(t_id[1:]) - 1) % len(TASK_COLORS)]
    except ValueError:
        return TASK_COLORS[hash(t_id) % len(TASK_COLORS)]


def _draw_panel(ax, dag_data, title, sched_dict, start_key, end_key, transfers=None):
    vms = [vm["id"] for vm in dag_data["vms"]]
    for t_id, info in sched_dict.items():
        y = vms.index(info["vm_id"])
        start, dur = info[start_key], info[end_key] - info[start_key]
        ax.barh(y, dur, left=start, height=0.6, color=_task_color(t_id),
                edgecolor="#1a1a1a", linewidth=0.8, alpha=0.95, zorder=3)
        ax.text(start + dur / 2, y, f"{t_id}\n{dur:.2f}s", ha="center", va="center",
                color="white", fontweight="bold", fontsize=7.5, zorder=4)
    if transfers:
        for tr in transfers:
            y = vms.index(tr["dst_vm"]) + 0.36
            ax.plot([tr["send_start"], tr["arrival"]], [y, y],
                    color="#C44E52" if tr["link"] == "inter-host" else "#E1A100",
                    linewidth=1.6, alpha=0.8, zorder=2)
    ax.set_yticks(range(len(vms)))
    ax.set_yticklabels([f"{v['id']}\n{v['host']} | {v['cpu_limit']}" for v in dag_data["vms"]],
                       fontsize=8.5)
    ax.invert_yaxis()
    ax.set_title(title, fontweight="bold", fontsize=11, loc="left")
    ax.grid(axis="x", linestyle="--", alpha=0.45, zorder=0)
    ax.set_facecolor("#FAFAFC")


def generate_gantt_chart(dag_data, heft_theo, heft_actual, rr_actual,
                         output_path: str = "results/gantt_comparison.png") -> None:
    fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True)
    _draw_panel(axes[0], dag_data,
                f"1. HEFT Theoretical Schedule  (Makespan = {heft_theo['theoretical_makespan']:.2f} s)",
                heft_theo["task_schedule"], "ast", "aft")
    _draw_panel(axes[1], dag_data,
                f"2. HEFT Real-World Execution on Kubernetes  (Makespan = {heft_actual['actual_makespan']:.2f} s)",
                heft_actual["actual_results"], "actual_ast", "actual_aft", heft_actual.get("transfers"))
    _draw_panel(axes[2], dag_data,
                f"3. Round-Robin Real-World Execution on Kubernetes  (Makespan = {rr_actual['actual_makespan']:.2f} s)",
                rr_actual["actual_results"], "actual_ast", "actual_aft", rr_actual.get("transfers"))
    axes[2].set_xlabel("Time (seconds)", fontweight="bold")
    legend = [Patch(color="#E1A100", label="Data transfer intra-host (1.0x)"),
              Patch(color="#C44E52", label="Data transfer inter-host (1.5x)")]
    fig.legend(handles=legend, loc="lower center", ncol=2, fontsize=9, frameon=False)
    fig.suptitle("KubeHEFT — HEFT vs Round-Robin on Heterogeneous Kind Cluster "
                 "(1 Datacenter, 2 Hosts, 4 VMs)", fontweight="bold", fontsize=12.5)
    plt.tight_layout(rect=(0, 0.03, 1, 0.97))
    plt.savefig(output_path, dpi=200)
    plt.close()


def generate_runs_chart(runs: List[Dict[str, Any]], heft_theo_ms: float, rr_theo_ms: float,
                        output_path: str = "results/makespan_runs.png") -> None:
    idx = list(range(1, len(runs) + 1))
    h = [r["heft_makespan"] for r in runs]
    rr = [r["rr_makespan"] for r in runs]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    w = 0.38
    ax.bar([i - w / 2 for i in idx], h, w, label="HEFT (actual)", color="#4C72B0", zorder=3)
    ax.bar([i + w / 2 for i in idx], rr, w, label="Round-Robin (actual)", color="#C44E52", zorder=3)
    ax.axhline(heft_theo_ms, color="#4C72B0", linestyle="--", linewidth=1.2,
               label=f"HEFT theoretical ({heft_theo_ms:.2f}s)")
    ax.axhline(rr_theo_ms, color="#C44E52", linestyle="--", linewidth=1.2,
               label=f"RR theoretical ({rr_theo_ms:.2f}s)")
    for i, (a, b) in enumerate(zip(h, rr), start=1):
        ax.text(i - w / 2, a + 0.1, f"{a:.2f}", ha="center", fontsize=8)
        ax.text(i + w / 2, b + 0.1, f"{b:.2f}", ha="center", fontsize=8)
    ax.set_xticks(idx)
    ax.set_xticklabels([f"Run {i}" for i in idx])
    ax.set_ylabel("Makespan (s)")
    ax.set_title("Actual Makespan per Run — HEFT vs Round-Robin", fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.45, zorder=0)
    ax.legend(fontsize=8.5, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def _mean_std(values: List[float]) -> str:
    if len(values) < 2:
        return f"{values[0]:.3f}"
    return f"{statistics.mean(values):.3f} ± {statistics.stdev(values):.3f}"


def generate_markdown_report(
    dag_data, calibration, heft_theo, rr_theo, runs, rep_idx, topology_text,
    output_path: str = "results/evaluation_report.md",
) -> None:
    rep = runs[rep_idx]
    heft_actual, rr_actual = rep["heft_actual"], rep["rr_actual"]
    m_ht = compute_metrics(dag_data, heft_theo["theoretical_makespan"])
    m_rt = compute_metrics(dag_data, rr_theo["theoretical_makespan"])
    heft_ms = [r["heft_makespan"] for r in runs]
    rr_ms = [r["rr_makespan"] for r in runs]
    heft_m = [compute_metrics(dag_data, x) for x in heft_ms]
    rr_m = [compute_metrics(dag_data, x) for x in rr_ms]
    wins = sum(1 for a, b in zip(heft_ms, rr_ms) if a < b)
    improvement = (statistics.mean(rr_ms) - statistics.mean(heft_ms)) / statistics.mean(rr_ms) * 100
    cp = critical_path(dag_data)

    L: List[str] = []
    L += ["# Laporan Evaluasi KubeHEFT: Algoritma HEFT vs Round-Robin pada Klaster Kubernetes Heterogen\n",
          "> Referensi: Topcuoglu, Hariri & Wu (2002), *Performance-Effective and Low-Complexity Task "
          "Scheduling for Heterogeneous Computing*, IEEE TPDS 13(3).\n",
          "## 1. Verifikasi Topologi Cloud (1 Datacenter, 2 Host, 4 VM)\n",
          "```text", topology_text.strip(), "```\n",
          "| VM ID | Host (label) | Kind Node | Limit CPU | Status |",
          "| :--- | :--- | :--- | :---: | :---: |"]
    for vm_id, h in calibration["health"].items():
        L.append(f"| `{vm_id}` | `{h['host_id']}` | `{h.get('node_name', '-')}` | `{h['cpu_limit']}` | {h['status']} |")

    L += ["\n## 2. Verifikasi Heterogenitas Perangkat Keras (Kalibrasi CFS Quota)\n",
          "| VM ID | Limit CPU | Rasio Target | Iterasi SHA-256/detik | Rasio Terukur |",
          "| :--- | :---: | :---: | ---: | :---: |"]
    vm_speed = {v["id"]: v for v in dag_data["vms"]}
    for vm_id, d in calibration["per_vm"].items():
        L.append(f"| `{vm_id}` | `{d['cpu_limit']}` | {vm_speed[vm_id]['speed_factor']:.2f}x | "
                 f"{d['iterations_per_sec']:,.0f} | **{d['measured_speed_ratio']:.3f}x** |")

    L += ["\n## 3. Fase 1 HEFT — Upward Rank & Fase 2 — Pemilihan VM (EFT + Insertion)\n",
          f"* Rata-rata faktor komunikasi antar-VM berbeda ($\\overline{{c}}$ multiplier): "
          f"`{heft_theo['avg_comm_multiplier']}`",
          f"* **Urutan prioritas:** `{' -> '.join(heft_theo['priority_order'])}`",
          f"* **Critical path (bobot min):** `{' -> '.join(cp)}` — $CP_{{MIN}}$ = {m_ht['cp_min_sum']:.2f} s\n",
          "| Task | $\\overline{w_i}$ | $rank_u$ | VM HEFT | EST teori | EFT teori | AST aktual | AFT aktual |",
          "| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: |"]
    for t in heft_theo["priority_order"]:
        th, ac = heft_theo["task_schedule"][t], heft_actual["actual_results"][t]
        L.append(f"| **{t}** | {heft_theo['w_bar'][t]:.3f} | {th['rank_u']:.3f} | `{th['vm_id']}` | "
                 f"{th['ast']:.2f} | {th['aft']:.2f} | {ac['actual_ast']:.2f} | {ac['actual_aft']:.2f} |")

    vms = [v["id"] for v in dag_data["vms"]]
    L += ["\n**Tabel EFT kandidat per VM (dasar pemilihan VM):**\n",
          "| Task | " + " | ".join(f"EFT `{v}`" for v in vms) + " | Terpilih |",
          "| :--- | " + " | ".join(":---:" for _ in vms) + " | :--- |"]
    for t in heft_theo["priority_order"]:
        row = heft_theo["eft_table"][t]
        chosen = heft_theo["task_schedule"][t]["vm_id"]
        cells = [f"**{row[v]['eft']:.2f}**" if v == chosen else f"{row[v]['eft']:.2f}" for v in vms]
        L.append(f"| {t} | " + " | ".join(cells) + f" | `{chosen}` |")

    L += ["\n## 4. Penempatan Tugas: HEFT vs Round-Robin\n",
          "| Task | VM HEFT | VM Round-Robin |", "| :--- | :--- | :--- |"]
    for t in [x["id"] for x in dag_data["tasks"]]:
        L.append(f"| {t} | `{heft_theo['task_schedule'][t]['vm_id']}` | `{rr_theo['task_schedule'][t]['vm_id']}` |")

    L += ["\n## 5. Transfer Data Antar-VM Riil (Run Representatif)\n",
          "| Skema | Edge | Sumber → Tujuan | Link | Payload | Transfer riil (s) | Biaya model (s) |",
          "| :--- | :--- | :--- | :--- | ---: | :---: | :---: |"]
    for label, res in (("HEFT", heft_actual), ("RR", rr_actual)):
        for tr in res["transfers"]:
            L.append(f"| {label} | {tr['edge']} | `{tr['src_vm']}` → `{tr['dst_vm']}` | {tr['link']} | "
                     f"{tr['payload_kb']} KB | {tr['real_transfer_sec']:.4f} | {tr['model_comm_sec']:.2f} |")

    L += [f"\n## 6. Hasil Pengujian Berulang ({len(runs)} run)\n",
          "| Run | Makespan HEFT (s) | Makespan RR (s) | Reduksi |", "| :---: | :---: | :---: | :---: |"]
    for i, r in enumerate(runs, start=1):
        red = (r["rr_makespan"] - r["heft_makespan"]) / r["rr_makespan"] * 100
        mark = " ⭐" if i - 1 == rep_idx else ""
        L.append(f"| {i}{mark} | {r['heft_makespan']:.3f} | {r['rr_makespan']:.3f} | {red:.2f}% |")
    L.append("\n⭐ = run representatif (median HEFT) yang digambar pada Gantt Chart.\n")

    L += ["## 7. Perbandingan Metrik Performa Utama\n",
          "| Skema Penjadwalan | Makespan $C_{max}$ (s) | SLR | Speedup |",
          "| :--- | :---: | :---: | :---: |",
          f"| HEFT (Teoritis) | {m_ht['makespan']:.3f} | {m_ht['slr']:.3f} | {m_ht['speedup']:.3f}x |",
          f"| Round-Robin (Teoritis) | {m_rt['makespan']:.3f} | {m_rt['slr']:.3f} | {m_rt['speedup']:.3f}x |",
          f"| **HEFT (Aktual Kubernetes, mean ± std)** | **{_mean_std(heft_ms)}** | "
          f"**{_mean_std([m['slr'] for m in heft_m])}** | **{_mean_std([m['speedup'] for m in heft_m])}** |",
          f"| Round-Robin (Aktual Kubernetes, mean ± std) | {_mean_std(rr_ms)} | "
          f"{_mean_std([m['slr'] for m in rr_m])} | {_mean_std([m['speedup'] for m in rr_m])} |",
          f"\n* $SLR = C_{{max}} / \\sum_{{n_i \\in CP_{{MIN}}}} \\min_{{p_j}} w_{{i,j}}$, dengan $CP_{{MIN}}$ = {m_ht['cp_min_sum']:.2f} s",
          f"* $Speedup = \\min_{{p_j}} \\sum_{{n_i}} w_{{i,j}} / C_{{max}}$, dengan waktu sekuensial minimum = {m_ht['min_seq_time']:.2f} s",
          f"\n> **Kesimpulan:** HEFT menghasilkan makespan lebih rendah daripada Round-Robin pada **{wins}/{len(runs)}** run, "
          f"dengan reduksi makespan rata-rata **{improvement:.2f}%** pada klaster Kubernetes heterogen nyata "
          f"(1 Datacenter, 2 Host, 4 VM).\n",
          "## 8. Artefak\n",
          "* `results/gantt_comparison.png` — Gantt: HEFT teoritis, HEFT aktual, RR aktual",
          "* `results/makespan_runs.png` — Makespan tiap run",
          "* `results/execution_log.json` — Data mentah seluruh eksekusi"]

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
