# OSS Remediation ADK

This project runs an automated OSS vulnerability remediation workflow for Java Spring Boot Maven repositories. It scans Critical and High vulnerabilities, analyzes Maven dependency ownership, plans dependency-only fixes, validates the changes, and creates a Draft GitHub Pull Request when validation succeeds.

> These instructions