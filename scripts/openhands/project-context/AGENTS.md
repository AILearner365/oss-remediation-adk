# Repository guidance for the Maven Gate-2 evaluation workspace

This is a Java 21, multi-module Maven project with modules `task-common`, `task-domain`, `task-service`, and `task-web`. Inspect the actual POMs for authoritative relationships and current configuration; do not assume versions from this document.

The root parent and `dependencyManagement` influence effective dependency versions across modules. Distinguish managed versions from direct declarations and transitive resolution. For material changes, inspect relevant module dependencies and runtime/test impact.

Use the project's existing Maven build/test entry points and scanner when evidence is needed. The current task contract, not this repository guide, owns remediation goals, version restrictions and acceptance criteria. Do not introduce project changes merely to follow this guide.
