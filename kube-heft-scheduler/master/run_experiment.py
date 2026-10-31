"""Entrypoint utama eksperimen KubeHEFT.

Jalankan dari root proyek:
    python -m master.run_experiment --runs 5
"""
import argparse
import asyncio
import json
import os
import statistics
import subprocess

from master.baseline_scheduler import schedule_round_robin
from master.dispatcher import execute_schedule_on_cloud, verify_and_calibrate_cluster
from master.heft_algorithm import schedule_heft
from master.visualize import generate_gantt_chart, generate_markdown_report, generate_runs_chart


def capture_topology(context: str) -> str:
    out = []
    for cmd in (["kubectl", "--context", context, "get", "nodes", "-L", "topology.host"],
                ["kubectl", "--context", context, "get", "pods", "-o", "wide"]):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            out.append("$ " + " ".join(cmd[3:] if cmd[1] == "--context" else cmd[1:]))
            out.append((res.stdout or res.stderr).rstrip())
        except Exception as exc:  # noqa: BLE001
            out.append(f"$ {' '.join(cmd)}\n<gagal: {exc}>")
    return "\n".join("kubectl " + l[2:] if l.startswith("$ ") else l for l in out)


async def main(runs: int, context: str, cooldown: float):
    os.makedirs("results", exist_ok=True)
    with open("master/dag_sample.json", "r", encoding="utf-8") as f:
        dag_data = json.load(f)

    print("[1/6] Menghitung jadwal teoritis HEFT dan Round-Robin...")
    heft_theo = schedule_heft(dag_data)
    rr_theo = schedule_round_robin(dag_data)
    print(f"      -> Urutan Prioritas HEFT : {' -> '.join(heft_theo['priority_order'])}")
    print(f"      -> Makespan Teoritis HEFT: {heft_theo['theoretical_makespan']:.2f}s")
    print(f"      -> Makespan Teoritis RR  : {rr_theo['theoretical_makespan']:.2f}s")

    print("[2/6] Memverifikasi topologi klaster (kubectl)...")
    topology_text = capture_topology(context)
    print(topology_text)

    print("[3/6] Health-check & kalibrasi CPU keempat VM...")
    calibration = await verify_and_calibrate_cluster(dag_data)
    for vm_id, d in calibration["per_vm"].items():
        print(f"      -> {vm_id} ({d['cpu_limit']:>5}): {d['iterations_per_sec']:>12,.0f} it/s "
              f"| rasio {d['measured_speed_ratio']:.3f}x")

    print(f"[4/6] Mengeksekusi {runs} run HEFT & Round-Robin secara riil di Kubernetes...")
    all_runs = []
    for i in range(runs):
        # Urutan diselang-seling untuk menghindari bias (cache/thermal)
        order = ("HEFT", "RR") if i % 2 == 0 else ("RR", "HEFT")
        res = {}
        for algo in order:
            plan = heft_theo if algo == "HEFT" else rr_theo
            res[algo] = await execute_schedule_on_cloud(
                dag_data, plan, calibration["iterations_per_sec_on_p1"])
            await asyncio.sleep(cooldown)
        all_runs.append({
            "run": i + 1,
            "heft_makespan": res["HEFT"]["actual_makespan"],
            "rr_makespan": res["RR"]["actual_makespan"],
            "heft_actual": res["HEFT"],
            "rr_actual": res["RR"],
        })
        print(f"      Run {i + 1}: HEFT = {res['HEFT']['actual_makespan']:.3f}s | "
              f"RR = {res['RR']['actual_makespan']:.3f}s")

    heft_vals = [r["heft_makespan"] for r in all_runs]
    median = statistics.median(heft_vals)
    rep_idx = min(range(len(all_runs)), key=lambda k: abs(heft_vals[k] - median))

    print("[5/6] Menyimpan log eksekusi...")
    with open("results/execution_log.json", "w", encoding="utf-8") as f:
        json.dump({
            "topology": topology_text,
            "calibration": calibration,
            "heft_theoretical": heft_theo,
            "rr_theoretical": rr_theo,
            "runs": all_runs,
            "representative_run": rep_idx + 1,
        }, f, indent=2)

    print("[6/6] Membuat visualisasi komparasi 3 dimensi & laporan akademis...")
    rep = all_runs[rep_idx]
    generate_gantt_chart(dag_data, heft_theo, rep["heft_actual"], rep["rr_actual"])
    generate_runs_chart(all_runs, heft_theo["theoretical_makespan"], rr_theo["theoretical_makespan"])
    generate_markdown_report(dag_data, calibration, heft_theo, rr_theo, all_runs, rep_idx, topology_text)

    # Sinkronisasi laporan ke root jika dijalankan dari subfolder
    if os.path.exists("results/LAPORAN_AKHIR_SOKA_KELOMPOK_6.md") and os.path.isdir("../"):
        try:
            import shutil
            shutil.copy("results/LAPORAN_AKHIR_SOKA_KELOMPOK_6.md", "../LAPORAN_AKHIR_SOKA_KELOMPOK_6.md")
        except Exception:
            pass

    print(f"\nHEFT mean = {statistics.mean(heft_vals):.3f}s | "
          f"RR mean = {statistics.mean([r['rr_makespan'] for r in all_runs]):.3f}s")
    print("Selesai! Seluruh artefak revisi telah berhasil di-generate:")
    print("  -> results/three_dimensional_comparison.png")
    print("  -> results/differentiation_gap_analysis.png")
    print("  -> results/gantt_comparison.png")
    print("  -> results/makespan_runs.png")
    print("  -> results/LAPORAN_AKHIR_SOKA_KELOMPOK_6.md")
    print("  -> results/evaluation_report.md")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="KubeHEFT experiment runner")
    ap.add_argument("--runs", type=int, default=5, help="jumlah pengulangan eksperimen")
    ap.add_argument("--context", default="kind-heft-datacenter", help="kubectl context")
    ap.add_argument("--cooldown", type=float, default=1.0, help="jeda antar eksekusi (detik)")
    args = ap.parse_args()
    asyncio.run(main(args.runs, args.context, args.cooldown))
