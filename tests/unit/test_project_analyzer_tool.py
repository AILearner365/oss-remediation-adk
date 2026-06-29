from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from oss_remediation_agent.tools.maven_project_tool import collect_maven_facts


class ProjectAnalyzerToolTests(unittest.TestCase):
    def test_project_analyzer_basic_maven_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = _repo(root)

            def fake_run(command, cwd=None, timeout=1800):
                if "dependency:tree" in command:
                    return {"exitCode": 0, "stdout": "+- org.yaml:snakeyaml:jar:1.33:compile", "stderr": ""}
                return {"exitCode": 0, "stdout": "", "stderr": ""}

            with patch("oss_remediation_agent.tools.maven_project_tool.run_command", side_effect=fake_run):
                result = collect_maven_facts(str(repo), str(root / "analysis.json"), str(root / "baseline"), workflow_id="wf")

            self.assertEqual(result["status"], "SUCCESS")
            analysis = json.loads((root / "analysis.json").read_text(encoding="utf-8"))
            self.assertTrue(analysis["projectFacts"]["springBoot"]["detected"])
            self.assertTrue(analysis["projectFacts"]["dependencyManagementPresent"])
            self.assertEqual(analysis["dependencyResolutionEvidence"][0]["dependency"], "org.yaml:snakeyaml")

    def test_project_analyzer_returns_partial_when_maven_evidence_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = _repo(root)

            def fake_run(command, cwd=None, timeout=1800):
                return {"exitCode": 1, "stdout": "", "stderr": "command unavailable"}

            with patch("oss_remediation_agent.tools.maven_project_tool.run_command", side_effect=fake_run):
                result = collect_maven_facts(str(repo), str(root / "analysis.json"), str(root / "baseline"), workflow_id="wf")

            self.assertEqual(result["status"], "PARTIAL")
            self.assertTrue(result["warnings"])
            analysis = json.loads((root / "analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(analysis["status"], "PARTIAL")
            self.assertTrue(analysis["warnings"])


def _repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    (repo / "pom.xml").write_text(
        """
<project>
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.4</version>
  </parent>
  <properties><java.version>17</java.version></properties>
  <modules><module>service-a</module></modules>
  <dependencyManagement></dependencyManagement>
</project>
""".strip(),
        encoding="utf-8",
    )
    (repo / "service-a").mkdir()
    (repo / "service-a" / "pom.xml").write_text("<project></project>", encoding="utf-8")
    return repo


if __name__ == "__main__":
    unittest.main()
