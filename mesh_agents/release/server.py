"""Release Manager agent - built with Google ADK (LlmAgent + session state), served over A2A on :9205."""
import json
import re
import uuid

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from a2a_kit import llm_spec
from a2a_kit.a2a import serve
from a2a_kit.assessment import normalize

PORT = 9205
INSTRUCTION = """You are the Release Manager making the final go/no-go call for repository {repo_path}.
Four specialist agents (built in different frameworks) reported:
{assessments}

Rules: any 'fail' verdict or any 'critical' finding means NO-GO. Two or more 'warn' verdicts, or any 'high' finding,
means CONDITIONAL-GO (list the conditions). Otherwise GO. Reply with ONLY a JSON object:
{"verdict": "pass|warn|fail", "score": 0-100, "summary": "2-3 sentences that justify the decision",
 "decision": "GO|CONDITIONAL-GO|NO-GO", "must_fix_before_release": ["..."], "can_fix_after_release": ["..."]}"""


async def handle(data: dict) -> dict:
    agent = LlmAgent(name="release_manager", model=llm_spec.adk_model(), instruction=INSTRUCTION, output_key="decision")
    runner = InMemoryRunner(agent=agent, app_name="release_manager")
    session = await runner.session_service.create_session(
        app_name="release_manager", user_id="orchestrator", session_id=str(uuid.uuid4()),
        state={"repo_path": data["repo_path"], "assessments": json.dumps(data["assessments"], indent=1)})
    async for _ in runner.run_async(user_id="orchestrator", session_id=session.id,
                                    new_message=types.Content(role="user", parts=[types.Part(text="Decide.")])):
        pass
    session = await runner.session_service.get_session(app_name="release_manager", user_id="orchestrator", session_id=session.id)
    text = str(session.state.get("decision", ""))
    m = re.search(r"\{.*\}", text, re.S)
    raw = json.loads(m.group(0)) if m else {"summary": text}
    out = normalize(raw, "Release Manager", "Google ADK")
    out["decision"] = raw.get("decision", "NO-GO")
    out["must_fix_before_release"] = raw.get("must_fix_before_release", [])
    out["can_fix_after_release"] = raw.get("can_fix_after_release", [])
    return out


if __name__ == "__main__":
    serve("Release Manager Agent (Google ADK)", "Combines specialist assessments into a go/no-go decision.",
          [{"id": "release", "name": "Go/no-go decision", "description": "input {repo_path, assessments}", "tags": ["release"]}],
          PORT, handle)
