# Repository context — Maven Gate-2 evaluation workspace

The workspace under remediation is a Java 21 multi-module Maven application: `task-common`, `task-domain`, `task-service`, and `task-web`. Inspect the actual working POMs rather than assuming this description establishes current dependency versions or module relationships.

The root parent and `dependencyManagement` may affect dependencies across modules; local declarations and transitive paths can alter actual resolution. The existing Maven build and tests are the project's normal verification entry points.

This file supplies repository facts only. The task prompt defines goals and constraints, `dependency-remediation-decision` owns the remediation decision process, and `maven-dependency-evidence` supplies Maven evidence methods. `validate-remediation` is provided by the harness for whole-project self-validation.
