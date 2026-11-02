"""Code Quality agent - built with smolagents (ToolCallingAgent + LiteLLM), served over A2A on :9201."""
from smolagents import LiteLLMModel, ToolCallingAgent, tool

from a2a_kit import llm_spec, repo_tools
from a2a_kit.a2a import serve
from a2a_kit.assessment import SCHEMA_HINT, parse_assessment

PORT = 9201


@tool
def code_quality_report(repo_path: str) -> str:
    """Static code-quality metrics: lines by language, TODO count, very long or branch-heavy functions, test ratio.

    Args:
        repo_path: Absolute path of the repository to inspect.
    """
    return repo_tools.as_json(repo_tools.quality_report, repo_path)


def handle(data: dict) -> dict:
    agent = ToolCallingAgent(tools=[code_quality_report], model=LiteLLMModel(model_id=llm_spec.litellm_id()),
                             max_steps=5, name="quality_agent")
    reply = agent.run(
        f"You are the Code Quality reviewer in a release-readiness check. Call code_quality_report for the repository "
        f"at '{data['repo_path']}', judge maintainability and test health for shipping a release, then call "
        f"final_answer with ONLY a JSON object of this shape: {SCHEMA_HINT}. Base every finding on the tool output.")
    return parse_assessment(reply, "Code Quality", "smolagents")


if __name__ == "__main__":
    serve("Code Quality Agent (smolagents)", "Maintainability and test-health review of a repository.",
          [{"id": "quality", "name": "Code quality review", "description": "input {repo_path}", "tags": ["quality"]}],
          PORT, handle)
