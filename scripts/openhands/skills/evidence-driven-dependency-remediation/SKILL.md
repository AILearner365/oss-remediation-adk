---
name: evidence-driven-dependency-remediation
description: Use for autonomously investigating, implementing, and verifying vulnerable software-dependency remediations, including release-family compatibility and evidence-led changes of strategy.
triggers:
  - vulnerability
  - vulnerabilities
  - remediation
  - dependency
---

# Evidence-driven dependency remediation

Work within the task's objective, constraints, and acceptance criteria. Own the engineering decisions; this skill supplies investigative standards, not a fixed strategy or prescribed package versions.

1. **Establish the actual system.** Inspect the relevant repository state, dependency resolution and upstream/downstream relationships. Separate observed facts, uncertain assumptions, and acceptance criteria. Seek authoritative current sources for decision-critical release, coordinate, advisory and compatibility claims; do not treat remembered product versions as evidence.
2. **Choose a defensible strategy.** Before consequential edits, verify assumptions that could invalidate the approach. When materially different credible approaches exist, compare relevant evidence, compatibility, constraints, blast radius and maintainability. Do not invent alternatives merely to satisfy a template.
3. **Use failures as evidence.** Distinguish incorrect coordinates, unmanaged versions, incompatible dependency families and implementation errors from verified repository, tool or network failures. After evidence contradicts a strategy's foundation, investigate or revise that foundation before applying more variants of essentially the same idea. Normal focused debugging is legitimate when it tests a new hypothesis.
4. **Implement with continuity.** Keep changes proportional to the objective. Preserve previously validated working states and improvements unless contrary evidence warrants replacing them. Inspect upstream, downstream, runtime and security implications, including justified exclusions and overrides.
5. **Validate the whole goal.** Check the effective dependency graph, build, tests, relevant runtime behavior, scan findings and the entire task contract using available evidence. Passing one command is not proof of full remediation. Report remaining gaps and uncertainty accurately. Prefer information-gaining actions over repeated edits or scans that do not test a new hypothesis.

Use the OpenHands tools available in this environment and decide independently what evidence to collect. This skill neither requires fixed commands nor authorizes overriding explicit task constraints.
