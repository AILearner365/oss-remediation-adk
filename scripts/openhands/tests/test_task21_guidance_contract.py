"""Offline Task-21 regression contracts; no OpenHands SDK or Vertex credentials required.

Run: python -m unittest discover -s scripts/openhands/tests -p 'test_task21_guidance_contract.py' -v
These tests inspect integration contracts; they do NOT establish live Skill activation
or validator execution.
"""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
RUNNER = ROOT / "scripts/openhands/openhands-gate2-stop-hook-run.py"
SKILLS = ROOT / "scripts/openhands/skills"


class Task21GuidanceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = RUNNER.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {
            n.name: n for n in cls.tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def function_source(self, name):
        self.assertIn(name, self.functions)
        return ast.get_source_segment(self.source, self.functions[name])

    def test_new_and_existing_cli_options(self):
        body = self.function_source("parse_args")
        for flag in ("--decision-guidance", "--structured-guidance",
                     "--task-skill", "--engineering-judgment-guidance",
                     "--max-denials", "--max-iterations"):
            with self.subTest(flag=flag):
                self.assertIn(flag, body)

    def test_mutually_exclusive_guidance_and_both_skills(self):
        body = self.function_source("build_agent")
        self.assertIn("sum((engineering_guidance, task_skill, structured_guidance, decision_guidance)) > 1", body)
        self.assertIn("skills[DECISION_SKILL_NAME]", body)
        self.assertIn("skills[MAVEN_SKILL_NAME]", body)
        self.assertIn("if structured_guidance or decision_guidance:", body)
        self.assertIn("if task_skill:", body)
        self.assertIn("if engineering_guidance:", body)

    def test_guidance_evidence_does_not_claim_observed_use(self):
        body = self.function_source("guidance_delivery_evidence")
        self.assertIn('"decisionSkill"', body)
        self.assertIn('"mavenSkill"', body)
        self.assertIn('"triggeredSkills"', body)
        self.assertIn('"observedUsed": "NOT_PROVEN"', body)

    def test_self_validation_launcher_and_stop_hook_remain_separate(self):
        main = self.function_source("main")
        hook = self.function_source("build_hook_config")
        self.assertIn('launcher_dir / "validate-remediation"', main)
        self.assertIn('scripts/openhands/validate-remediation', main)
        self.assertIn("hook_config=hook_config", main)
        self.assertIn("conversation.run()", main)
        self.assertIn("HookExecutionEvent", main)
        self.assertIn("HookConfig(", hook)
        self.assertIn("HookDefinition(", hook)
        self.assertIn("DEFAULT_HOOK", hook)
        validation = (ROOT / "scripts/openhands/validate-remediation").read_text(encoding="utf-8")
        self.assertIn("did not request final acceptance or consume a Stop Hook attempt", validation)

    def test_original_structured_scanner_mode_not_rewired(self):
        main = self.function_source("main")
        self.assertIn("if args.structured_guidance:", main)
        self.assertIn("openhands-osv-scanner.sh", main)
        self.assertIn("if args.decision_guidance:", main)
        self.assertIn("configure_scanner_terminal(", main)

    def test_skill_files_exist_and_contain_evidence_and_validation(self):
        for name in ("dependency-remediation-decision", "maven-dependency-evidence"):
            with self.subTest(skill=name):
                path = SKILLS / name / "SKILL.md"
                text = path.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("---\n"))
                self.assertIn("name: " + name, text)
                self.assertIn("validate-remediation", text)
                self.assertIn("advisory", text.lower())


if __name__ == "__main__":
    unittest.main()
