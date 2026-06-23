def scan_repository(repo_url: str, reference_branch: str = "main") -> dict:
    return {
        "status": "success",
        "repo_url": repo_url,
        "reference_branch": reference_branch,
        "findings": [
            {
                "ecosystem": "maven",
                "dependency": "org.apache.commons:commons-text",
                "current_version": "1.9",
                "recommended_version": "1.10.0",
                "severity": "HIGH",
                "source": "mock-scanner",
            }
        ],
    }