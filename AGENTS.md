# Repository guidance

- Product: Autonomous OSS Vulnerability Remediation, using standalone OpenHands SDK/Tools 1.55.1.
- Product branch: `autonomous-oss-remediation`. Preserve existing work and Git history.
- Approved Google Cloud project: `deutschebank-aipocs`.
- Approved Vertex AI location: `us-central1`.
- The existing `scripts/openhands/sdk-cloudshell-setup.sh` supplies these approved
  defaults for live execution when environment values are absent. Explicit
  `VERTEXAI_PROJECT` takes precedence over `GOOGLE_CLOUD_PROJECT`, then the approved
  project default; explicit `VERTEXAI_LOCATION` takes precedence over the approved
  location default. Do not silently select another model or discover an unrelated
  active gcloud project as a replacement.
- Project/location are configuration, not credentials. Reuse existing ADC;
  never store credential contents, tokens or service-account keys in the repository.
- A successful ADC refresh does not prove inference availability. Preserve all
  preparation, validation, evidence, authorization and delivery checks.
- Live/model execution requires explicit operator authorization. Do not initiate
  a live run merely to verify configuration changes.
