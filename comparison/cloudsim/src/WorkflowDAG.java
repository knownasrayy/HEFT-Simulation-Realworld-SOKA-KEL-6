import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;

public class WorkflowDAG {

    private final List<WorkflowTask> tasks;

    public WorkflowDAG() {
        tasks = new ArrayList<>();
    }

    public List<WorkflowTask> getTasks() {
        return tasks;
    }

    public void addTask(WorkflowTask task) {
        tasks.add(task);
    }

    public WorkflowTask getTask(int id) {
        return tasks.get(id);
    }

    public int size() {
        return tasks.size();
    }

    public static WorkflowDAG generateSynthetic(int numberOfTasks, long seed) {
        if (numberOfTasks < 2) {
            throw new IllegalArgumentException("Jumlah task minimal 2.");
        }

        WorkflowDAG dag = new WorkflowDAG();
        Random random = new Random(seed);

        for (int i = 0; i < numberOfTasks; i++) {
            long instructionLength = 5_000L + random.nextInt(45_001);
            dag.addTask(new WorkflowTask(i, instructionLength));
        }

        for (int i = 1; i < numberOfTasks; i++) {
            WorkflowTask child = dag.getTask(i);
            int maxParents = Math.min(i, 3);
            int parentCount = random.nextInt(maxParents + 1);
            Set<Integer> selectedParents = new HashSet<>();

            for (int p = 0; p < parentCount; p++) {
                int parentId = random.nextInt(i);
                if (!selectedParents.add(parentId)) {
                    continue;
                }
                WorkflowTask parent = dag.getTask(parentId);
                double dataSizeMB = 10.0 + random.nextInt(91);
                parent.addSuccessor(child, dataSizeMB);
            }
        }

        for (int i = 1; i < numberOfTasks; i++) {
            WorkflowTask task = dag.getTask(i);
            if (task.getPredecessors().isEmpty()) {
                WorkflowTask parent = dag.getTask(i - 1);
                double dataSizeMB = 10.0 + random.nextInt(91);
                parent.addSuccessor(task, dataSizeMB);
            }
        }

        return dag;
    }

    public List<WorkflowTask> topologicalOrder() {
        List<WorkflowTask> result = new ArrayList<>(tasks);
        result.sort(Comparator.comparingInt(WorkflowTask::getId));
        return result;
    }

    public List<WorkflowTask> getEntryTasks() {
        List<WorkflowTask> result = new ArrayList<>();
        for (WorkflowTask task : tasks) {
            if (task.getPredecessors().isEmpty()) {
                result.add(task);
            }
        }
        return result;
    }

    public List<WorkflowTask> getExitTasks() {
        List<WorkflowTask> result = new ArrayList<>();
        for (WorkflowTask task : tasks) {
            if (task.getSuccessors().isEmpty()) {
                result.add(task);
            }
        }
        return result;
    }

    public int getEdgeCount() {
        int count = 0;
        for (WorkflowTask task : tasks) {
            count += task.getSuccessors().size();
        }
        return count;
    }
}

