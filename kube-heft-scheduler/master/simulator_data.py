"""Data Baseline Simulator CloudSim 7.0.1 untuk Workflow 10-Task DAG pada 4 VM Heterogen.

Data ini merepresentasikan hasil simulasi discrete-event CloudSim (tanpa OS jitter,
jaringan ideal tanpa packet loss/contention, dan alokasi celah insertion deterministik).
Sesuai temuan Tugas 3 & Tugas 4 Kelompok 6: deviasi CloudSim vs Teori adalah 0.000%
pada kondisi ideal.
"""
from typing import Any, Dict


def get_cloudsim_baseline(dag_data: Dict[str, Any]) -> Dict[str, Any]:
    """Mengembalikan data metrik dan profil jadwal CloudSim 7.0.1 untuk HEFT dan Round-Robin."""
    return {
        "simulator_name": "CloudSim 7.0.1 Discrete-Event Simulator",
        "workload": "Topcuoglu 2002 10-Task Synthetic DAG",
        "datacenter_count": 1,
        "host_count": 2,
        "vm_count": 4,
        "heft": {
            "makespan": 6.900,
            "slr": 1.725,
            "speedup": 1.304,
            "parallel_efficiency_pct": 32.61,
            "efficiency_pct": 32.61,
            "cpu_utilization_pct": 37.57,
            "comm_overhead_sec": 7.150,
            "task_assignments": {
                "T1": "vm-worker-1",
                "T2": "vm-worker-1",
                "T3": "vm-worker-1",
                "T4": "vm-worker-1",
                "T5": "vm-worker-2",
                "T6": "vm-worker-3",
                "T7": "vm-worker-1",
                "T8": "vm-worker-3",
                "T9": "vm-worker-1",
                "T10": "vm-worker-1",
            },
        },
        "round_robin": {
            "makespan": 12.700,
            "slr": 3.175,
            "speedup": 0.709,
            "parallel_efficiency_pct": 17.72,
            "efficiency_pct": 17.72,
            "cpu_utilization_pct": 34.39,
            "comm_overhead_sec": 10.550,
            "task_assignments": {
                "T1": "vm-worker-1",
                "T2": "vm-worker-2",
                "T3": "vm-worker-3",
                "T4": "vm-worker-4",
                "T5": "vm-worker-1",
                "T6": "vm-worker-2",
                "T7": "vm-worker-3",
                "T8": "vm-worker-4",
                "T9": "vm-worker-1",
                "T10": "vm-worker-2",
            },
        },
    }
