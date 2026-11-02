"""Documentation agent - built with LangGraph (collect -> judge -> suggest), served over A2A on :9203."""
import json
from pathlib import Path
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from a2a_kit import llm_spec, repo_tools
from a2a_kit.a2a import serve
from a2a_kit.assessment import normalize

PORT = 9203


class Finding(BaseModel):
    severity: Literal["info", "low", "medium", "high", "critical"]
    title: str
    detail: str


class Judgement(BaseModel):
    verdict: Literal["pass", "warn", "fail"]
    score: int = Field(ge=0, le=100)
    summary: str
    findings: list[Finding]


class State(TypedDict, total=False):
    repo_path: str
    facts: dict
    judgement: dict


def collect(state: State) -> dict:
    return {"facts": repo_tools.docs_check(Path(state["repo_path"]))}


def judge(state: State) -> dict:
    j = llm_spec.langchain_model().with_structured_output(Judgement).invoke(
        "You are the Documentation reviewer in a release-readiness check. Judge whether the docs are good enough to "
        "release: README completeness (install/usage/license), broken links, changelog, docstring coverage. "
        f"Facts:\n{json.dumps(state['facts'], indent=1)}")
    return {"judgement": j.model_dump()}


def suggest(state: State) -> dict:
    """Runs only when the docs score is low: adds a concrete fix list as an extra finding."""
    text = llm_spec.langchain_model(0.3).invoke(
        "List the 5 highest-impact documentation fixes (one line each) for a repo with these facts:\n"
        f"{json.dumps(state['facts'])}").content
    j = state["judgement"]
    j["findings"].append({"severity": "info", "title": "Suggested documentation fixes",
                          "detail": text if isinstance(text, str) else str(text)})
    return {"judgement": j}


def route(state: State) -> Literal["suggest", "__end__"]:
    return "suggest" if state["judgement"]["score"] < 70 else END


def build():
    g = StateGraph(State)
    g.add_node("collect", collect)
    g.add_node("judge", judge)
    g.add_node("suggest", suggest)
    g.add_edge(START, "collect")
    g.add_edge("collect", "judge")
    g.add_conditional_edges("judge", route, {"suggest": "suggest", END: END})
    g.add_edge("suggest", END)
    return g.compile()


def handle(data: dict) -> dict:
    final = build().invoke({"repo_path": data["repo_path"]})
    return normalize(final["judgement"], "Documentation", "LangGraph")


if __name__ == "__main__":
    serve("Documentation Agent (LangGraph)", "README, changelog and docstring review.",
          [{"id": "docs", "name": "Documentation review", "description": "input {repo_path}", "tags": ["docs"]}],
          PORT, handle)
