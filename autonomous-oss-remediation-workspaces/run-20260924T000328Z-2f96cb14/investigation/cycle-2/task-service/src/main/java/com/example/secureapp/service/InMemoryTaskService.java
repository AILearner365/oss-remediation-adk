package com.example.secureapp.service;

import com.example.secureapp.domain.Task;
import com.example.secureapp.domain.TaskStatus;
import org.springframework.stereotype.Service;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class InMemoryTaskService implements TaskService {
    private final Map<UUID, Task> tasks = new ConcurrentHashMap<>();

    public InMemoryTaskService() {
        create("Review dependency tree", "Run mvn dependency:tree before adding a new starter.");
        updateStatus(create("Generate SBOM", "Run mvn verify -Psbom before release.").id(), TaskStatus.IN_PROGRESS);
    }

    @Override
    public List<Task> findAll() {
        return tasks.values().stream()
                .sorted(Comparator.comparing(Task::createdAt))
                .toList();
    }

    @Override
    public Optional<Task> findById(UUID id) {
        return Optional.ofNullable(tasks.get(id));
    }

    @Override
    public Task create(String title, String description) {
        validateTitle(title);
        Task task = Task.newTask(title, description);
        tasks.put(task.id(), task);
        return task;
    }

    @Override
    public Task updateDetails(UUID id, String title, String description) {
        validateTitle(title);
        return tasks.compute(id, (taskId, existingTask) -> {
            if (existingTask == null) {
                throw new TaskNotFoundException(taskId);
            }
            return existingTask.withDetails(title, description);
        });
    }

    @Override
    public Task updateStatus(UUID id, TaskStatus status) {
        if (status == null) {
            throw new IllegalArgumentException("Task status is required.");
        }
        return tasks.compute(id, (taskId, existingTask) -> {
            if (existingTask == null) {
                throw new TaskNotFoundException(taskId);
            }
            return existingTask.withStatus(status);
        });
    }

    @Override
    public void delete(UUID id) {
        Task removed = tasks.remove(id);
        if (removed == null) {
            throw new TaskNotFoundException(id);
        }
    }

    private void validateTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Task title is required.");
        }
        if (title.length() > 120) {
            throw new IllegalArgumentException("Task title must be 120 characters or fewer.");
        }
    }
}
