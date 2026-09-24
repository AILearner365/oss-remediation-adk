package com.example.secureapp.common.api;

import java.time.Instant;
import java.util.List;

public record ApiErrorResponse(
        String code,
        String message,
        Instant timestamp,
        List<String> details
) {
    public static ApiErrorResponse of(String code, String message, List<String> details) {
        return new ApiErrorResponse(code, message, Instant.now(), details == null ? List.of() : List.copyOf(details));
    }
}
