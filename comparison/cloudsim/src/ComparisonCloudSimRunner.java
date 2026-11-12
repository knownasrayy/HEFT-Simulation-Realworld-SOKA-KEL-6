import org.cloudbus.cloudsim.Cloudlet;
import org.cloudbus.cloudsim.CloudletSchedulerSpaceShared;
import org.cloudbus.cloudsim.Datacenter;
import org.cloudbus.cloudsim.DatacenterCharacteristics;
import org.cloudbus.cloudsim.Host;
import org.cloudbus.cloudsim.Log;
import org.cloudbus.cloudsim.Pe;
import org.cloudbus.cloudsim.Storage;
import org.cloudbus.cloudsim.UtilizationModel;
import org.cloudbus.cloudsim.UtilizationModelFull;
import org.cloudbus.cloudsim.Vm;
import org.cloudbus.cloudsim.core.CloudSim;
import org.cloudbus.cloudsim.provisioners.BwProvisionerSimple;
import org.cloudbus.cloudsim.provisioners.PeProvisionerSimple;
import org.cloudbus.cloudsim.provisioners.RamProvisionerSimple;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ComparisonCloudSimRunner {

    private static final long DAG_SEED = 2026L;
    private static final double HOST_IDLE_POWER_WATT = 100.0;
    private static final double HOST_MAX_POWER_WATT = 250.0;
    private static final long HOST_STORAGE = 1_000_000L;
    private static final long VM_STORAGE = 10_000L;

    private static class VmSpec {
        String label;
        String host;
        int mips;
    }

    private static class ParsedDag {
        double interHostPenalty = 1.5;
        double intraHostFactor = 1.0;
        List<VmSpec> vms = new ArrayList<>();
        WorkflowDAG dag = new WorkflowDAG();
        Map<String, Integer> taskIndexMap = new LinkedHashMap<>();
    }

    private static ParsedDag parseDagJson(Path jsonPath) throws Exception {
        String text = Files.readString(jsonPath, StandardCharsets.UTF_8);
        ParsedDag parsed = new ParsedDag();

        Matcher mPenalty = Pattern.compile("\"inter_host_comm_penalty\"\\s*:\\s*([0-9.]+)").matcher(text);
        if (mPenalty.find()) {
            parsed.interHostPenalty = Double.parseDouble(mPenalty.group(1));
        }
        Matcher mIntra = Pattern.compile("\"intra_host_comm_factor\"\\s*:\\s*([0-9.]+)").matcher(text);
        if (mIntra.find()) {
            parsed.intraHostFactor = Double.parseDouble(mIntra.group(1));
        }

        Matcher mVmsBlock = Pattern.compile("\"vms\"\\s*:\\s*\\[(.*?)\\]", Pattern.DOTALL).matcher(text);
        if (mVmsBlock.find()) {
            String block = mVmsBlock.group(1);
            Matcher mVm = Pattern.compile(
                "\"id\"\\s*:\\s*\"([^\"]+)\".*?\"host\"\\s*:\\s*\"([^\"]+)\".*?\"speed_factor\"\\s*:\\s*([0-9.]+)",
                Pattern.DOTALL
            ).matcher(block);
            while (mVm.find()) {
                VmSpec spec = new VmSpec();
                spec.label = mVm.group(1);
                spec.host = mVm.group(2);
                double speed = Double.parseDouble(mVm.group(3));
                spec.mips = (int) Math.round(speed * 1000.0);
                parsed.vms.add(spec);
            }
        }

        Matcher mTasksBlock = Pattern.compile("\"tasks\"\\s*:\\s*\\[(.*?)\\]\\s*,\\s*\"edges\"", Pattern.DOTALL).matcher(text);
        if (mTasksBlock.find()) {
            String block = mTasksBlock.group(1);
            Matcher mTask = Pattern.compile(
                "\"id\"\\s*:\\s*\"([^\"]+)\".*?\"base_seconds_on_p1\"\\s*:\\s*([0-9.]+)",
                Pattern.DOTALL
            ).matcher(block);
            int idx = 0;
            while (mTask.find()) {
                String label = mTask.group(1);
                double baseSec = Double.parseDouble(mTask.group(2));
                long mi = Math.round(baseSec * 1000.0);
                parsed.taskIndexMap.put(label, idx);
                parsed.dag.addTask(new WorkflowTask(idx, label, mi));
                idx++;
            }
        }

        Matcher mEdgesBlock = Pattern.compile("\"edges\"\\s*:\\s*\\[(.*?)\\]\\s*\\}", Pattern.DOTALL).matcher(text);
        if (mEdgesBlock.find()) {
            String block = mEdgesBlock.group(1);
            Matcher mEdge = Pattern.compile(
                "\"from\"\\s*:\\s*\"([^\"]+)\".*?\"to\"\\s*:\\s*\"([^\"]+)\".*?\"comm_cost\"\\s*:\\s*([0-9.]+)",
                Pattern.DOTALL
            ).matcher(block);
            while (mEdge.find()) {
                String from = mEdge.group(1);
                String to = mEdge.group(2);
                double commCostSec = Double.parseDouble(mEdge.group(3));
                double dataSizeMb = commCostSec * HEFTScheduler.NETWORK_BANDWIDTH_MBPS;
                WorkflowTask src = parsed.dag.getTask(parsed.taskIndexMap.get(from));
                WorkflowTask dst = parsed.dag.getTask(parsed.taskIndexMap.get(to));
                src.addSuccessor(dst, dataSizeMb);
            }
        }

        return parsed;
    }

    private static Host createHost(int id, int pes, int mips, int ram, long bw) {
        List<Pe> peList = new ArrayList<>();
        for (int i = 0; i < pes; i++) {
            peList.add(new Pe(i, new PeProvisionerSimple(mips)));
        }
        return new Host(
            id,
            new RamProvisionerSimple(ram),
            new BwProvisionerSimple(bw),
            HOST_STORAGE,
            peList,
            new org.cloudbus.cloudsim.VmSchedulerTimeShared(peList)
        );
    }

    private static Datacenter createSmallDatacenter(String name, int hostCount, int maxVmsPerHost) throws Exception {
        List<Host> hostList = new ArrayList<>();
        for (int i = 0; i < hostCount; i++) {
            hostList.add(createHost(i, 8, 4000, 32768, 100000));
        }
        DatacenterCharacteristics ch = new DatacenterCharacteristics(
            "x86", "Linux", "Xen", hostList, 7.0, 0.10, 0.01, 0.001, 0.01
        );
        return new Datacenter(name, ch, new VmAllocationPolicyUniform(hostList, maxVmsPerHost), new ArrayList<Storage>(), 0);
    }

    private static Datacenter createOriginalDatacenter(String name, int dcIndex, int maxVmsPerHost) throws Exception {
        List<Host> hostList = new ArrayList<>();
        if (dcIndex == 0) {
            hostList.add(createHost(0, 24, 3500, 65536, 100000));
            hostList.add(createHost(1, 24, 3800, 65536, 100000));
            hostList.add(createHost(2, 24, 4200, 65536, 120000));
            hostList.add(createHost(3, 24, 4500, 65536, 120000));
        } else {
            hostList.add(createHost(4, 24, 3600, 98304, 100000));
            hostList.add(createHost(5, 24, 4000, 98304, 100000));
            hostList.add(createHost(6, 24, 4400, 98304, 120000));
            hostList.add(createHost(7, 24, 5000, 98304, 160000));
        }
        DatacenterCharacteristics ch = new DatacenterCharacteristics(
            "x86", "Linux", "Xen", hostList, 7.0, 0.10, 0.01, 0.001, 0.01
        );
        return new Datacenter(name, ch, new VmAllocationPolicyUniform(hostList, maxVmsPerHost), new ArrayList<Storage>(), 0);
    }

    private static List<Vm> createOriginalVmList(int brokerId, int vmCount) {
        int[] mips = {1000, 1200, 1500, 1800, 2000, 2200, 2500, 2800, 3000, 3500};
        int[] pes = {1, 1, 1, 1, 2, 2, 2, 2, 2, 4};
        int[] ram = {2048, 2048, 2048, 2048, 4096, 4096, 4096, 8192, 8192, 8192};
        List<Vm> list = new ArrayList<>();
        for (int i = 0; i < vmCount; i++) {
            int p = i % mips.length;
            list.add(new Vm(i, brokerId, mips[p], pes[p], ram[p], 10000, VM_STORAGE, "Xen", new CloudletSchedulerSpaceShared()));
        }
        return list;
    }

    private static double calculateCpuUtilization(WorkflowDAG dag, List<Vm> vms, double makespan) {
        if (makespan <= 0) {
            return 0.0;
        }
        double totalBusyTime = 0.0;
        for (WorkflowTask task : dag.getTasks()) {
            totalBusyTime += Math.max(0.0, task.getFinishTime() - task.getStartTime());
        }
        double totalCapacity = 0.0;
        for (Vm vm : vms) {
            totalCapacity += vm.getNumberOfPes() * makespan;
        }
        return totalCapacity > 0 ? (totalBusyTime / totalCapacity) * 100.0 : 0.0;
    }

    private static double calculateEnergy(WorkflowDAG dag, List<Vm> vms, List<Datacenter> datacenters, double makespan) {
        double totalEnergy = 0.0;
        for (Datacenter dc : datacenters) {
            for (Host host : dc.<Host>getHostList()) {
                double hostBusyPeSeconds = 0.0;
                for (Vm vm : host.<Vm>getVmList()) {
                    for (WorkflowTask task : dag.getTasks()) {
                        if (task.getAssignedVmId() == vm.getId()) {
                            hostBusyPeSeconds += Math.max(0.0, task.getFinishTime() - task.getStartTime());
                        }
                    }
                }
                double hostCapacity = host.getNumberOfPes() * Math.max(makespan, 1e-9);
                double util = Math.min(1.0, hostBusyPeSeconds / hostCapacity);
                double avgPower = HOST_IDLE_POWER_WATT + (HOST_MAX_POWER_WATT - HOST_IDLE_POWER_WATT) * util;
                totalEnergy += avgPower * makespan;
            }
        }
        return totalEnergy;
    }

    private static double calculateCommOverhead(
        WorkflowDAG dag,
        Map<Integer, String> vmHostMap,
        boolean topologyAware,
        double intraFactor,
        double interPenalty
    ) {
        double total = 0.0;
        for (WorkflowTask task : dag.getTasks()) {
            for (WorkflowTask succ : task.getSuccessors()) {
                if (task.getAssignedVmId() != succ.getAssignedVmId()) {
                    double factor = 1.0;
                    if (topologyAware && vmHostMap != null) {
                        String h1 = vmHostMap.getOrDefault(task.getAssignedVmId(), "host-0");
                        String h2 = vmHostMap.getOrDefault(succ.getAssignedVmId(), "host-0");
                        factor = h1.equals(h2) ? intraFactor : interPenalty;
                    }
                    total += (task.getCommunicationCostTo(succ) / HEFTScheduler.NETWORK_BANDWIDTH_MBPS) * factor;
                }
            }
        }
        return total;
    }

    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.US);
        if (args.length < 3) {
            System.err.println("Usage: ComparisonCloudSimRunner <dag10-flat|dag10-topo|dag10-rr|synthetic-100> <dag_json_path> <output_json_path>");
            System.exit(1);
        }

        String mode = args[0].toLowerCase(Locale.ROOT);
        Path dagJsonPath = Path.of(args[1]);
        Path outJsonPath = Path.of(args[2]);
        Files.createDirectories(outJsonPath.getParent());

        Log.disable();
        CloudSim.init(1, Calendar.getInstance(), false);

        boolean isSynthetic = mode.equals("synthetic-100");
        boolean topologyAware = mode.equals("dag10-topo") || mode.equals("dag10-rr");
        boolean isRoundRobin = mode.equals("dag10-rr");

        WorkflowDAG dag;
        List<Datacenter> datacenters = new ArrayList<>();
        List<Vm> vmList = new ArrayList<>();
        Map<Integer, String> vmLabelMap = new LinkedHashMap<>();
        Map<Integer, String> vmHostMap = new LinkedHashMap<>();
        double intraFactor = 1.0;
        double interPenalty = 1.5;

        if (isSynthetic) {
            dag = WorkflowDAG.generateSynthetic(100, DAG_SEED);
            int vmCount = 10;
            int maxVmsPerHost = Math.max(1, (int) Math.ceil((double) vmCount / 8.0));
            datacenters.add(createOriginalDatacenter("Datacenter_0", 0, maxVmsPerHost));
            datacenters.add(createOriginalDatacenter("Datacenter_1", 1, maxVmsPerHost));
            WorkflowBroker broker = new WorkflowBroker("CloudSim_Broker", dag, null, false, 1.0, 1.0);
            vmList = createOriginalVmList(broker.getId(), vmCount);
            for (Vm vm : vmList) {
                vmLabelMap.put(vm.getId(), "vm-" + vm.getId());
                vmHostMap.put(vm.getId(), "host-" + (vm.getId() % 8));
            }
            runSimulation(mode, "HEFT", false, intraFactor, interPenalty, dag, datacenters, broker, vmList, vmLabelMap, vmHostMap, outJsonPath);
            return;
        }

        ParsedDag parsed = parseDagJson(dagJsonPath);
        dag = parsed.dag;
        intraFactor = parsed.intraHostFactor;
        interPenalty = parsed.interHostPenalty;

        datacenters.add(createSmallDatacenter("Datacenter_0", 2, 2));
        WorkflowBroker broker = new WorkflowBroker(
            "CloudSim_Broker", dag, vmHostMap, topologyAware, intraFactor, interPenalty
        );
        int brokerId = broker.getId();

        for (int i = 0; i < parsed.vms.size(); i++) {
            VmSpec spec = parsed.vms.get(i);
            Vm vm = new Vm(i, brokerId, spec.mips, 1, 2048, 10000, VM_STORAGE, "Xen", new CloudletSchedulerSpaceShared());
            vmList.add(vm);
            vmLabelMap.put(i, spec.label);
            vmHostMap.put(i, spec.host);
        }

        String algo = isRoundRobin ? "Round-Robin" : "HEFT";
        runSimulation(mode, algo, topologyAware, intraFactor, interPenalty, dag, datacenters, broker, vmList, vmLabelMap, vmHostMap, outJsonPath);
    }

    private static void runSimulation(
        String mode,
        String algorithm,
        boolean topologyAware,
        double intraFactor,
        double interPenalty,
        WorkflowDAG dag,
        List<Datacenter> datacenters,
        WorkflowBroker broker,
        List<Vm> vmList,
        Map<Integer, String> vmLabelMap,
        Map<Integer, String> vmHostMap,
        Path outJsonPath
    ) throws Exception {
        long schedStart = System.nanoTime();
        double estimatedMakespan = 0.0;
        double avgCommMultiplier = 0.0;
        List<WorkflowTask> priorityOrder;

        Map<Integer, Double> estMap = new HashMap<>();
        Map<Integer, Double> eftMap = new HashMap<>();

        if (algorithm.equals("Round-Robin")) {
            priorityOrder = dag.topologicalOrder();
            for (int i = 0; i < priorityOrder.size(); i++) {
                WorkflowTask t = priorityOrder.get(i);
                Vm vm = vmList.get(i % vmList.size());
                t.setAssignedVmId(vm.getId());
                t.setRankUpward(0.0);
                estMap.put(t.getId(), 0.0);
                eftMap.put(t.getId(), 0.0);
            }
        } else {
            HEFTScheduler scheduler = new HEFTScheduler(
                dag, vmList, vmHostMap, topologyAware, intraFactor, interPenalty
            );
            scheduler.schedule();
            estimatedMakespan = scheduler.getMakespan();
            avgCommMultiplier = scheduler.getAvgCommMultiplier();
            priorityOrder = scheduler.getPriorityOrder();
            for (WorkflowTask t : dag.getTasks()) {
                estMap.put(t.getId(), t.getStartTime());
                eftMap.put(t.getId(), t.getFinishTime());
            }
        }
        long schedEnd = System.nanoTime();
        double schedRuntimeMs = (schedEnd - schedStart) / 1_000_000.0;

        broker.submitGuestList(vmList);
        List<Cloudlet> cloudletList = new ArrayList<>();
        UtilizationModel utilization = new UtilizationModelFull();
        for (WorkflowTask task : dag.getTasks()) {
            Cloudlet cloudlet = new Cloudlet(
                task.getId(), task.getInstructionLength(), 1, 300, 300, utilization, utilization, utilization
            );
            cloudlet.setUserId(broker.getId());
            cloudlet.setGuestId(task.getAssignedVmId());
            cloudletList.add(cloudlet);
            broker.registerCloudlet(task, cloudlet);
        }
        broker.submitCloudletList(cloudletList);

        CloudSim.startSimulation();
        CloudSim.stopSimulation();

        double actualMakespan = broker.getActualMakespan();
        double cpuUtil = calculateCpuUtilization(dag, vmList, actualMakespan);
        double energy = calculateEnergy(dag, vmList, datacenters, actualMakespan);
        double commOverhead = calculateCommOverhead(dag, vmHostMap, topologyAware, intraFactor, interPenalty);

        StringBuilder sb = new StringBuilder();
        sb.append("{\n");
        sb.append(String.format("  \"mode\": \"%s\",\n", mode));
        sb.append(String.format("  \"algorithm\": \"%s\",\n", algorithm));
        sb.append(String.format("  \"topology_aware\": %s,\n", topologyAware));
        sb.append(String.format("  \"task_count\": %d,\n", dag.size()));
        sb.append(String.format("  \"edge_count\": %d,\n", dag.getEdgeCount()));
        sb.append(String.format("  \"vm_count\": %d,\n", vmList.size()));
        sb.append(String.format("  \"completed_tasks\": %d,\n", broker.getCompletedTaskCount()));
        sb.append(String.format("  \"avg_comm_multiplier\": %.6f,\n", avgCommMultiplier));
        sb.append(String.format("  \"estimated_makespan\": %.6f,\n", estimatedMakespan));
        sb.append(String.format("  \"actual_makespan\": %.6f,\n", actualMakespan));
        sb.append(String.format("  \"comm_overhead_sec\": %.6f,\n", commOverhead));
        sb.append(String.format("  \"cpu_utilization_pct\": %.4f,\n", cpuUtil));
        sb.append(String.format("  \"energy_joule\": %.4f,\n", energy));
        sb.append(String.format("  \"scheduling_runtime_ms\": %.4f,\n", schedRuntimeMs));

        sb.append("  \"priority_order\": [");
        for (int i = 0; i < priorityOrder.size(); i++) {
            sb.append("\"").append(priorityOrder.get(i).getLabel()).append("\"");
            if (i < priorityOrder.size() - 1) sb.append(", ");
        }
        sb.append("],\n");

        sb.append("  \"tasks\": [\n");
        List<WorkflowTask> allTasks = dag.getTasks();
        for (int i = 0; i < allTasks.size(); i++) {
            WorkflowTask t = allTasks.get(i);
            int vmId = t.getAssignedVmId();
            sb.append(String.format(
                "    {\"id\": %d, \"label\": \"%s\", \"mi\": %d, \"rank_u\": %.6f, \"vm_id\": %d, \"vm_label\": \"%s\", \"host_id\": \"%s\", \"est\": %.6f, \"eft\": %.6f, \"ast\": %.6f, \"aft\": %.6f}",
                t.getId(),
                t.getLabel(),
                t.getInstructionLength(),
                t.getRankUpward(),
                vmId,
                vmLabelMap.getOrDefault(vmId, "vm-" + vmId),
                vmHostMap.getOrDefault(vmId, "host-0"),
                estMap.getOrDefault(t.getId(), 0.0),
                eftMap.getOrDefault(t.getId(), 0.0),
                t.getStartTime(),
                t.getFinishTime()
            ));
            if (i < allTasks.size() - 1) sb.append(",");
            sb.append("\n");
        }
        sb.append("  ]\n");
        sb.append("}\n");

        Files.writeString(outJsonPath, sb.toString(), StandardCharsets.UTF_8);
        System.out.printf("[%s] %s | Makespan: est=%.4fs, actual=%.4fs | CPU=%.2f%% | Comm=%.4fs | SchedTime=%.3fms%n",
            mode, algorithm, estimatedMakespan, actualMakespan, cpuUtil, commOverhead, schedRuntimeMs);
    }
}

