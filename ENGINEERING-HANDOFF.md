# Codex engineering handoff — execute without another design loop

Read [PRODUCT-CONTRACT.md](PRODUCT-CONTRACT.md) fully. It is the product behavior and boundary contract; follow it over experimental code. Product branch is `openhands-native-product` and its HEAD tree intentionally excludes legacy sources. Experiments remain accessible by commit/other branches; no blanket merge.

Verified starting point: `f72e5308704960ee911f382f96bf0b7948435216` on `openhands-service-integration`, including:
- `scripts/openhands_native_wiring_submit.py`: one-shot native submission with effective Stop Hook verification.
- `scripts/openhands_native_wiring_hook.py`: independent exact-file validation, Git tree/base identity, claim and draft PR delivery.
- `scripts/openhands_native_poc.py` or equivalent native helper used in actual code (verify exact path).
- `docs/experiments/openhands/OPENHANDS-NATIVE-WIRING-SMOKE.md` and sanitized evidence.
- Existing Maven/OSV baseline/validator, existing tests, SBRI experiment on relevant branches (locate actual files; do not invent APIs).
- Existing technology-neutral operating model and decision/outcome artifacts (locate and extract behavioral requirements; do not import old orchestration).

**Next engineering work (not authorized in this Stage A commit):** inspect actual native 1.55.1 extension points and available experimental source; create product code in this clean tree. You have authority to choose minimal package layout and copy/refactor needed code. Prefer native conversation handling, tools and hook registration. Hook must call task-specific independent validation (never weaken smoke validator's one-file checks to accept all changes), provide deny feedback and only deliver the exact validated tree after PASS. Maven/OSV scanner and dependency coverage must be real; optional SBRI must remain optional. Separate agent tool use from trusted validator execution. Work from approved base, not mutable branch HEAD.

Keep iterations bounded and explain only true blockers. Work in functional vertical slices: first offline unit/integration checks of submission/validation/delivery boundaries, then report readiness for one explicitly authorized live remediation. Do not launch Gemini or create target PR without that authorization. Do not recreate the product service, UI or SQLite.

Deliver: files/entry commands, concise requirement-to-code mapping, offline test results, unsupported/open risks, commit SHA and next *one* actionable step. Avoid returning another generic design proposal or list of optional architectures.
