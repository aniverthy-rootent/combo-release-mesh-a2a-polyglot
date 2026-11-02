"""License agent - built with the OpenAI Agents SDK (function tool + typed output), served over A2A on :9204."""
import os
from typing import Literal

from agents import Agent, Runner, function_tool
from pydantic import BaseModel

from a2a_kit import llm_spec, repo_tools
from a2a_kit.a2a import serve
from a2a_kit.assessment import normalize

os.environ.setdefault("OPENAI_AGENTS_DISABLE_TRACING", "1")
PORT = 9204


class Finding(BaseModel):
    severity: Literal["info", "low", "medium", "high", "critical"]
    title: str
    detail: str


class Assessment(BaseModel):
    verdict: Literal["pass", "warn", "fail"]
    score: int
    summary: str
    findings: list[Finding]


@function_tool
def run_license_check(repo_path: str) -> str:
    """Project license file and the licenses of its Python dependencies (looked up live on PyPI)."""
    return repo_tools.as_json(repo_tools.license_check, repo_path)


async def handle(data: dict) -> dict:
    agent = Agent(
        name="License reviewer", model=llm_spec.openai_agents_model(), tools=[run_license_check], output_type=Assessment,
        instructions=("You are the License reviewer in a release-readiness check. Call run_license_check. A missing "
                      "project license is 'high'. Strong-copyleft dependencies (GPL/AGPL) in a permissively licensed "
                      "project are 'high'; weak copyleft (LGPL/MPL) 'medium'; unknown licenses 'low'. Score 0-100."))
    result = await Runner.run(agent, f"Check the repository at {data['repo_path']}.", max_turns=6)
    return normalize(result.final_output.model_dump(), "Licenses", "OpenAI Agents SDK")


if __name__ == "__main__":
    serve("License Agent (OpenAI Agents SDK)", "Project and dependency license compliance review.",
          [{"id": "licenses", "name": "License review", "description": "input {repo_path}", "tags": ["licenses"]}],
          PORT, handle)
