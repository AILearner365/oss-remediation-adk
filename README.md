# Native OpenHands OSS Remediation Product

This is the **clean product working tree**, intentionally separated from historical experimental code. The product is **not yet implemented**. Start with [PRODUCT-CONTRACT.md](PRODUCT-CONTRACT.md) and [ENGINEERING-HANDOFF.md](ENGINEERING-HANDOFF.md).

The parent commit `f72e5308704960ee911f382f96bf0b7948435216` retains the verified native OpenHands smoke and historical experiment repository **for reference only**. The product branch's tree starts clean by design: do not merge the experimental tree back wholesale.

Goal: an autonomous, evidence-driven Java Maven OSS remediation workflow, executed by native OpenHands and gated by independent deterministic validation before GitHub draft-PR delivery. Preserve native API/SDK/Canvas and built-in hook semantics, not an invented service/API/UI/database.
