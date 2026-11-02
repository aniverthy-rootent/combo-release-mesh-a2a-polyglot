"""Security agent - built with Pydantic AI (typed output + tool), served over A2A on :9202."""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from a2a_kit import llm_spec, repo_tools
from a2a_kit.a2a import serve
from a2a_kit.assessment import normalize

PORT = 9202


class Finding(BaseModel):
    severity: Literal["info", "low", "medium", "high", "critical"]
    title: str
    detail: str


class Assessment(BaseModel):
    verdict: Literal["pass", "warn", "fail"]
    score: int = Field(ge=0, le=100)
    summary: str
    findings: list[Finding]


@dataclass
class Deps:
    repo_path: str


def build() -> Agent:
    agent = Agent(llm_spec.pydantic_ai_id(), output_type=Assessment, deps_type=Deps, instructions=(
        "You are the Security reviewer in a release-readiness check. Call run_security_scan, then judge whether the "
        "repository is safe to release. Any possible secret or committed .env is at least 'high'; eval/exec/"
        "pickle/shell=True are 'medium' or higher depending on context. Never print secret values."))

    @agent.tool
    def run_security_scan(ctx: RunContext[Deps]) -> str:
        """Secrets, dangerous calls (eval/exec/pickle/shell=True/md5), committed .env files and unpinned requirements."""
        return repo_tools.as_json(repo_tools.security_scan, ctx.deps.repo_path)

    return agent


async def handle(data: dict) -> dict:
    result = await build().run("Assess the repository.", deps=Deps(repo_path=data["repo_path"]))
    return normalize(result.output.model_dump(), "Security", "Pydantic AI")


if __name__ == "__main__":
    serve("Security Agent (Pydantic AI)", "Secrets and dangerous-code review with typed output.",
          [{"id": "security", "name": "Security review", "description": "input {repo_path}", "tags": ["security"]}],
          PORT, handle)
