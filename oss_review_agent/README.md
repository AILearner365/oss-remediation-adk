# OSS Review Agent POC

This is a separate, read-only ADK agent for reviewing an existing OSS remediation workspace.

## What it does

- Reads persisted JSON, Markdown, text, log, XML, diff, and patch files from a completed remediation workspace.
- Prioritizes the attempt manifest, vulnerability assessment, project analysis, patch plan, patch proof, validation result, outcome analysis, PR summary, and `pom.xml` files.
- Performs one lightweight review pass.
- Asks practical reviewer questions and answers them from the stored evidence.
- Returns one decision: `APPROVED`, `CHANGES_REQUESTED`, or `NEEDS_HUMAN_REVIEW`.

It does not rerun remediation, change files, or create a pull request.

## Run in ADK Web

Start ADK Web from the repository root as usual. Select `oss_review_agent` from the agent list.

Provide an existing workspace path in this format:

```text
Review the completed OSS remediation workspace.
workspace_root: C:\path\to\oss-remediation-workspaces\oss-remediation-20260713-210000
```

On Linux or macOS:

```text
Review the completed OSS remediation workspace.
workspace_root: /path/to/oss-remediation-workspaces/oss-remediation-20260713-210000
```

The workspace must already exist on the same machine where ADK Web is running.

## POC limitations

- One review round only.
- Reads at most 40 reviewable files.
- Includes at most 12,000 characters per text file.
- Uses only available workspace evidence; undocumented reasoning is reported as missing rather than inferred.
