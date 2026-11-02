"""The common result contract every agent returns, whatever framework produced it."""
from __future__ import annotations

import json
import re

SCHEMA_HINT = ('{"verdict": "pass|warn|fail", "score": 0-100, "summary": "2-3 sentences", '
               '"findings": [{"severity": "info|low|medium|high|critical", "title": "...", "detail": "..."}]}')


def normalize(raw: dict, agent: str, framework: str) -> dict:
    findings = []
    for f in raw.get("findings", []) or []:
        if isinstance(f, dict):
            findings.append({"severity": str(f.get("severity", "info")).lower(), "title": str(f.get("title", ""))[:200],
                             "detail": str(f.get("detail", ""))[:600]})
    verdict = str(raw.get("verdict", "warn")).lower()
    return {"agent": agent, "framework": framework, "verdict": verdict if verdict in {"pass", "warn", "fail"} else "warn",
            "score": max(0, min(100, int(raw.get("score", 50)))), "summary": str(raw.get("summary", ""))[:800],
            "findings": findings[:20]}


def parse_assessment(text: str, agent: str, framework: str) -> dict:
    """Extract the first JSON object from an LLM reply; degrade gracefully if there is none."""
    m = re.search(r"\{.*\}", str(text), re.S)
    try:
        return normalize(json.loads(m.group(0)), agent, framework) if m else _fallback(text, agent, framework)
    except (json.JSONDecodeError, ValueError, TypeError):
        return _fallback(text, agent, framework)


def _fallback(text, agent: str, framework: str) -> dict:
    return normalize({"verdict": "warn", "score": 50, "summary": f"Unstructured reply: {str(text)[:500]}",
                      "findings": []}, agent, framework)
