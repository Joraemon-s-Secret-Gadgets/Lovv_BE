# @file tests/test_agentcore_pipeline_config.py
# @description Configuration contract tests for the AgentCore deployment pipeline and SAM template.
# @author JJonyeok2
# @lastModified 2026-07-15

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RUNTIME_ARN = (
    "arn:aws:bedrock-agentcore:us-east-1:925273580929:"
    "runtime/LovvAgentCore_LovvAgentV2-cy3tYk7nV4"
)
EXPECTED_KAKAO_MOBILITY_SSM_PATHS = {
    "poc": "/lovv/poc/kakao_mobility/rest_api_key",
    "prod": "/lovv/prod/kakao_mobility/rest_api_key",
}


def _yaml_parameter_value(path, parameter_key):
    content = path.read_text(encoding="utf-8")
    match = re.search(
        rf"^- ParameterKey: {re.escape(parameter_key)}\s*$"
        rf"\n\s+ParameterValue: [\"']?([^\"'\n]+)[\"']?\s*$",
        content,
        flags=re.MULTILINE,
    )
    if not match:
        raise AssertionError(f"{parameter_key} is missing from {path}")
    return match.group(1).strip()


class AgentCorePipelineConfigTest(unittest.TestCase):
    def test_all_deployment_profiles_use_the_v2_runtime(self):
        for profile in ("dev", "poc", "prod"):
            with self.subTest(profile=profile):
                value = _yaml_parameter_value(
                    ROOT / "parameters" / f"{profile}.yaml",
                    "AgentCoreRuntimeArn",
                )
                self.assertEqual(value, EXPECTED_RUNTIME_ARN)

        dev_parameters = json.loads((ROOT / "parameters" / "dev.json").read_text(encoding="utf-8"))
        dev_runtime_arn = next(
            item["ParameterValue"]
            for item in dev_parameters
            if item.get("ParameterKey") == "AgentCoreRuntimeArn"
        )
        self.assertEqual(dev_runtime_arn, EXPECTED_RUNTIME_ARN)

    def test_deployed_profiles_use_environment_specific_kakao_mobility_ssm_paths(self):
        for profile, expected_path in EXPECTED_KAKAO_MOBILITY_SSM_PATHS.items():
            with self.subTest(profile=profile):
                value = _yaml_parameter_value(
                    ROOT / "parameters" / f"{profile}.yaml",
                    "KakaoMobilityRestApiKeySsmName",
                )
                self.assertEqual(value, expected_path)

    def test_sam_pipeline_injects_and_authorizes_only_the_selected_runtime(self):
        template = (ROOT / "template.yaml").read_text(encoding="utf-8")
        runtime_parameter = re.search(
            r"^  AgentCoreRuntimeArn:\n"
            r"(?:    .*\n)*?"
            r"    Default: ([^\n]+)$",
            template,
            flags=re.MULTILINE,
        )
        self.assertIsNotNone(runtime_parameter)
        self.assertEqual(runtime_parameter.group(1).strip(), EXPECTED_RUNTIME_ARN)

        agentcore_start = template.index("  AgentCoreFunction:")
        agentcore_end = template.index("\n  RecommendationFeedFunction:", agentcore_start)
        agentcore_block = template[agentcore_start:agentcore_end]

        self.assertIn("BEDROCK_AGENT_ARN: !Ref AgentCoreRuntimeArn", agentcore_block)
        self.assertEqual(agentcore_block.count("bedrock-agentcore:InvokeAgentRuntime"), 1)
        self.assertIn("Resource:\n                - !Ref AgentCoreRuntimeArn", agentcore_block)
        self.assertIn(
            '- !Sub "${AgentCoreRuntimeArn}/runtime-endpoint/DEFAULT"',
            agentcore_block,
        )
        self.assertNotIn('${AgentCoreRuntimeArn}*', agentcore_block)
        self.assertNotIn("FunctionUrlConfig:", agentcore_block)
        self.assertIn("Authorizer: LovvTokenAuthorizer", agentcore_block)
        self.assertNotIn("myagent_MyAgent", template)

    def test_recommendation_route_has_bounded_throttling(self):
        template = (ROOT / "template.yaml").read_text(encoding="utf-8")
        self.assertIn("'POST /api/v1/recommendations':", template)
        self.assertIn("ThrottlingBurstLimit: 5", template)
        self.assertIn("ThrottlingRateLimit: 2", template)


if __name__ == "__main__":
    unittest.main()

# EOF: tests/test_agentcore_pipeline_config.py
