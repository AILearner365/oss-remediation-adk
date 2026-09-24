package com.example.secureapp.service;

import com.example.secureapp.domain.Task;
import com.example.secureapp.domain.TaskStatus;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface TaskService {
    List<Task> findAll();

    Optional<Task> findById(UUID id);

    Task create(String title, String description);

    Task updateDetails(UUID id, String title, String description);

    Task updateStatus(UUID id, TaskStatus status);

    void delete(UUID id);
}
