def apply_remediation(repo_url: str, dependency: str, recommended_version: str) -> dict:
    return {
        "status": "success",
        "repo_url": repo_url,
        "dependency": dependency,
        "applied_version": recommended_version,
        "changed_files": ["pom.xml"],
        "message": "Mock remediation applied successfully.",
    }