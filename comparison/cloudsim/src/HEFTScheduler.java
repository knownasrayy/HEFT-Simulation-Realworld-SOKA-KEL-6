import org.cloudbus.cloudsim.Vm;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class HEFTScheduler {

    public static final double NETWORK_BANDWIDTH_MBPS = 100.0;

    private final WorkflowDAG dag;
    private final List<Vm> vms;
    private final Map<Integer, String> vmHostMap;
    private final boolean topologyAware;
    private final double intraHostFactor;
    private final double interHostPenalty;
    private final Map<Integer, List<TaskInterval>> vmSchedules;

    private static class TaskInterval {
        private final WorkflowTask task;
        private final double start;
        private final double finish;

        public TaskInterval(WorkflowTask task, double start, double finish) {
            this.task = task;
            this.start = start;
            this.finish = finish;
        }

        public WorkflowTask getTask() { return task; }
        public double getStart() { return start; }
        public double getFinish() { return finish; }
    }

    public HEFTScheduler(
        WorkflowDAG dag,
        List<Vm> vms,
        Map<Integer, String> vmHostMap,
        boolean topologyAware,
        double intraHostFactor,
        double interHostPenalty
    ) {
        this.dag = dag;
        this.vms = vms;
        this.vmHostMap = vmHostMap;
        this.topologyAware = topologyAware;
        this.intraHostFactor = intraHostFactor;
        this.interHostPenalty = interHostPenalty;
        this.vmSchedules = new HashMap<>();
        for (Vm vm : vms) {
            vmSchedules.put(vm.getId(), new ArrayList<>());
        }
    }

    private double computationCost(WorkflowTask task, Vm vm) {
        return (double) task.getInstructionLength() / vm.getMips();
    }

    private double averageComputationCost(WorkflowTask task) {
        double total = 0.0;
        for (Vm vm : vms) {
            total += computationCost(task, vm);
        }
        return total / vms.size();
    }

    private double commFactor(Vm sourceVm, Vm destinationVm) {
        if (sourceVm.getId() == destinationVm.getId()) {
            return 0.0;
        }
        if (!topologyAware || vmHostMap == null) {
            return 1.0;
        }
        String srcHost = vmHostMap.getOrDefault(sourceVm.getId(), "host-0");
        String dstHost = vmHostMap.getOrDefault(destinationVm.getId(), "host-0");
        return srcHost.equals(dstHost) ? intraHostFactor : interHostPenalty;
    }

    private double communicationCost(WorkflowTask from, WorkflowTask to, Vm sourceVm, Vm destinationVm) {
        double factor = commFactor(sourceVm, destinationVm);
        if (factor == 0.0) {
            return 0.0;
        }
        return (from.getCommunicationCostTo(to) / NETWORK_BANDWIDTH_MBPS) * factor;
    }

    public double getAvgCommMultiplier() {
        int p = vms.size();
        if (p <= 1) {
            return 0.0;
        }
        if (!topologyAware) {
            return (double) (p - 1) / p;
        }
        double sum = 0.0;
        int count = 0;
        for (Vm v1 : vms) {
            for (Vm v2 : vms) {
                if (v1.getId() != v2.getId()) {
                    sum += commFactor(v1, v2);
                    count++;
                }
            }
        }
        return count > 0 ? sum / count : 0.0;
    }

    private double averageCommunicationCost(WorkflowTask from, WorkflowTask to) {
        double networkCost = from.getCommunicationCostTo(to) / NETWORK_BANDWIDTH_MBPS;
        return networkCost * getAvgCommMultiplier();
    }

    private double calculateRankUpward(WorkflowTask task, Map<Integer, Double> memo) {
        if (memo.containsKey(task.getId())) {
            return memo.get(task.getId());
        }
        double averageComputation = averageComputationCost(task);
        double maxSuccessorCost = 0.0;
        for (WorkflowTask successor : task.getSuccessors()) {
            double successorRank = calculateRankUpward(successor, memo);
            double communication = averageCommunicationCost(task, successor);
            maxSuccessorCost = Math.max(maxSuccessorCost, communication + successorRank);
        }
        double rank = averageComputation + maxSuccessorCost;
        task.setRankUpward(rank);
        memo.put(task.getId(), rank);
        return rank;
    }

    public void calculateRanks() {
        Map<Integer, Double> memo = new HashMap<>();
        for (WorkflowTask task : dag.getTasks()) {
            calculateRankUpward(task, memo);
        }
    }

    public List<WorkflowTask> getPriorityOrder() {
        List<WorkflowTask> ordered = new ArrayList<>(dag.getTasks());
        ordered.sort(
            Comparator.comparingDouble(WorkflowTask::getRankUpward)
                .reversed()
                .thenComparingInt(WorkflowTask::getId)
        );
        return ordered;
    }

    private Vm getVmById(int id) {
        for (Vm vm : vms) {
            if (vm.getId() == id) {
                return vm;
            }
        }
        throw new IllegalArgumentException("VM #" + id + " tidak ditemukan.");
    }

    private double calculateReadyTime(WorkflowTask task, Vm candidateVm) {
        double readyTime = 0.0;
        for (WorkflowTask predecessor : task.getPredecessors()) {
            if (predecessor.getAssignedVmId() < 0) {
                throw new IllegalStateException("Predecessor Task #" + predecessor.getId() + " belum dijadwalkan.");
            }
            Vm predecessorVm = getVmById(predecessor.getAssignedVmId());
            double communication = communicationCost(predecessor, task, predecessorVm, candidateVm);
            double arrival = predecessor.getFinishTime() + communication;
            readyTime = Math.max(readyTime, arrival);
        }
        return readyTime;
    }

    private double findEarliestStart(WorkflowTask task, Vm vm) {
        double readyTime = calculateReadyTime(task, vm);
        double executionTime = computationCost(task, vm);
        List<TaskInterval> schedule = vmSchedules.get(vm.getId());
        schedule.sort(Comparator.comparingDouble(TaskInterval::getStart));

        double candidate = readyTime;
        for (TaskInterval interval : schedule) {
            double candidateFinish = candidate + executionTime;
            if (candidateFinish <= interval.getStart() + 1e-9) {
                return candidate;
            }
            candidate = Math.max(candidate, interval.getFinish());
        }
        return candidate;
    }

    private void insertTask(WorkflowTask task, Vm vm, double start, double finish) {
        List<TaskInterval> schedule = vmSchedules.get(vm.getId());
        schedule.add(new TaskInterval(task, start, finish));
        schedule.sort(Comparator.comparingDouble(TaskInterval::getStart));
    }

    public void schedule() {
        calculateRanks();
        List<WorkflowTask> ordered = getPriorityOrder();

        for (WorkflowTask task : ordered) {
            Vm selectedVm = null;
            double selectedStart = Double.MAX_VALUE;
            double selectedEft = Double.MAX_VALUE;

            for (Vm vm : vms) {
                double start = findEarliestStart(task, vm);
                double executionTime = computationCost(task, vm);
                double eft = start + executionTime;
                if (eft < selectedEft - 1e-9) {
                    selectedVm = vm;
                    selectedStart = start;
                    selectedEft = eft;
                }
            }

            if (selectedVm == null) {
                throw new IllegalStateException("Tidak ada VM untuk Task #" + task.getId());
            }

            task.setAssignedVmId(selectedVm.getId());
            task.setStartTime(selectedStart);
            task.setFinishTime(selectedEft);
            insertTask(task, selectedVm, selectedStart, selectedEft);
        }
    }

    public double getMakespan() {
        double makespan = 0.0;
        for (WorkflowTask task : dag.getTasks()) {
            makespan = Math.max(makespan, task.getFinishTime());
        }
        return makespan;
    }
}

