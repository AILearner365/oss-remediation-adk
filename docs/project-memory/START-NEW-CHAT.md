# Start a new ChatGPT project conversation

## One-line commands

In a fresh conversation in the Autonomous OSS Remediation ChatGPT project, say:

> **Start project continuity.**

This means: follow the bootstrap instructions below.

At a meaningful checkpoint or before ending a working conversation, say:

> **Checkpoint project continuity.**

This means: follow [CHECKPOINT.md](CHECKPOINT.md), update the project-memory state for material changes, and push those documentation changes when repository write access is available.

## Bootstrap behavior

When the user says **"Start project continuity."**:

> Continue our Autonomous Agent development project from the current GitHub repository, not from scratch. Read `docs/project-memory/PROJECT-DIRECTION.md`, `WORK-STATE.md`, and `DECISION-LOG.md` on the active `AILearner365/oss-remediation-adk` branch. Reconcile their branch/commit bookmark with the latest repository and consult the authoritative package README, journal designs and experiment record linked there as needed. Tell me the main objective, current stage, active problem and parent stack, why we entered it, immediate action and return point; distinguish conversation intent, implemented code and runtime evidence. Keep settled decisions unless material new evidence warrants revisiting them. Continue our ChatGPT design → Codex implementation → GitHub review → Cloud Shell run → evidence → next-change loop. As material problems, decisions, tests and focus changes occur, update those project-memory files and their return points. These are development continuity documents, never Autonomous Agent runtime inputs. Now continue the active work.

If a repository branch has advanced, read its new commits and run evidence before treating [WORK-STATE](WORK-STATE.md) as current. ChatGPT maintains the bookmark on meaningful changes, rather than after every message. If project history or the separately maintained operating-model document is unavailable, identify the gap instead of inventing it.

During the conversation, treat [CHECKPOINT.md](CHECKPOINT.md) as the maintenance procedure whenever the user asks to checkpoint continuity.
