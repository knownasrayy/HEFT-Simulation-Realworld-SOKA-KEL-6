import org.cloudbus.cloudsim.Cloudlet;
import org.cloudbus.cloudsim.DatacenterBroker;
import org.cloudbus.cloudsim.Vm;
import org.cloudbus.cloudsim.core.CloudActionTags;
import org.cloudbus.cloudsim.core.SimEvent;

import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class WorkflowBroker extends DatacenterBroker {

    private final WorkflowDAG dag;
    private final Map<Integer, String> vmHostMap;
    private final boolean topologyAware;
    private final double intraHostFactor;
    private final double interHostPenalty;

    private final Map<Integer, Cloudlet> taskToCloudlet;
    private final Map<Integer, WorkflowTask> cloudletToTask;
    private final Set<Integer> completedTasks;
    private final Set<Integer> submittedTasks;

    private double actualMakespan = 0.0;
    private int completedTaskCount = 0;

    public WorkflowBroker(
        String name,
        WorkflowDAG dag,
        Map<Integer, String> vmHostMap,
        boolean topologyAware,
        double intraHostFactor,
        double interHostPenalty
    ) throws Exception {
        super(name);
        this.dag = dag;
        this.vmHostMap = vmHostMap;
        this.topologyAware = topologyAware;
        this.intraHostFactor = intraHostFactor;
        this.interHostPenalty = interHostPenalty;
        this.taskToCloudlet = new HashMap<>();
        this.cloudletToTask = new HashMap<>();
        this.completedTasks = new HashSet<>();
        this.submittedTasks = new HashSet<>();
    }

    public void registerCloudlet(WorkflowTask task, Cloudlet cloudlet) {
        taskToCloudlet.put(task.getId(), cloudlet);
        cloudletToTask.put(cloudlet.getCloudletId(), task);
    }

    @Override
    protected void submitCloudlets() {
        for (WorkflowTask task : dag.getEntryTasks()) {
            Cloudlet cloudlet = taskToCloudlet.get(task.getId());
            if (cloudlet != null) {
                submitReadyCloudlet(cloudlet);
            }
        }
    }

    private void submitReadyCloudlet(Cloudlet cloudlet) {
        WorkflowTask task = cloudletToTask.get(cloudlet.getCloudletId());
        if (task == null) {
            return;
        }
        int taskId = task.getId();
        if (submittedTasks.contains(taskId)) {
            return;
        }
        int vmId = task.getAssignedVmId();
        if (vmId < 0) {
            throw new IllegalStateException("Task #" + taskId + " belum memiliki VM.");
        }
        Integer datacenterId = getVmsToDatacentersMap().get(vmId);
        if (datacenterId == null) {
            throw new IllegalStateException("VM #" + vmId + " belum terdaftar pada Datacenter.");
        }

        cloudlet.setGuestId(vmId);
        submittedTasks.add(taskId);

        double communicationDelay = calculateCommunicationDelay(task);
        send(datacenterId, communicationDelay, CloudActionTags.CLOUDLET_SUBMIT, cloudlet);
    }

    private double commFactor(int srcVmId, int dstVmId) {
        if (srcVmId == dstVmId) {
            return 0.0;
        }
        if (!topologyAware || vmHostMap == null) {
            return 1.0;
        }
        String srcHost = vmHostMap.getOrDefault(srcVmId, "host-0");
        String dstHost = vmHostMap.getOrDefault(dstVmId, "host-0");
        return srcHost.equals(dstHost) ? intraHostFactor : interHostPenalty;
    }

    private double calculateCommunicationDelay(WorkflowTask task) {
        double delay = 0.0;
        Vm destinationVm = findVm(task.getAssignedVmId());
        for (WorkflowTask predecessor : task.getPredecessors()) {
            Vm sourceVm = findVm(predecessor.getAssignedVmId());
            double factor = commFactor(sourceVm.getId(), destinationVm.getId());
            if (factor > 0.0) {
                double edgeDelay = (predecessor.getCommunicationCostTo(task) / HEFTScheduler.NETWORK_BANDWIDTH_MBPS) * factor;
                delay = Math.max(delay, edgeDelay);
            }
        }
        return delay;
    }

    private Vm findVm(int vmId) {
        for (org.cloudbus.cloudsim.core.GuestEntity guest : getGuestList()) {
            if (guest instanceof Vm vm && vm.getId() == vmId) {
                return vm;
            }
        }
        throw new IllegalStateException("VM #" + vmId + " tidak ditemukan.");
    }

    @Override
    protected void processCloudletReturn(SimEvent ev) {
        Cloudlet cloudlet = (Cloudlet) ev.getData();
        WorkflowTask task = cloudletToTask.get(cloudlet.getCloudletId());
        if (task == null) {
            return;
        }

        int taskId = task.getId();
        completedTasks.add(taskId);
        completedTaskCount++;

        double finishTime = cloudlet.getFinishTime();
        if (finishTime > actualMakespan) {
            actualMakespan = finishTime;
        }

        task.setStartTime(cloudlet.getExecStartTime());
        task.setFinishTime(cloudlet.getFinishTime());

        for (WorkflowTask successor : task.getSuccessors()) {
            if (submittedTasks.contains(successor.getId())) {
                continue;
            }
            if (allPredecessorsCompleted(successor)) {
                Cloudlet successorCloudlet = taskToCloudlet.get(successor.getId());
                if (successorCloudlet != null) {
                    submitReadyCloudlet(successorCloudlet);
                }
            }
        }

        if (completedTaskCount == dag.size()) {
            actualMakespan = Math.max(actualMakespan, cloudlet.getFinishTime());
        }
    }

    private boolean allPredecessorsCompleted(WorkflowTask task) {
        for (WorkflowTask predecessor : task.getPredecessors()) {
            if (!completedTasks.contains(predecessor.getId())) {
                return false;
            }
        }
        return true;
    }

    public double getActualMakespan() {
        return actualMakespan;
    }

    public int getCompletedTaskCount() {
        return completedTaskCount;
    }
}

