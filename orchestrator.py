"""Release Orchestrator - the sixth agent (plain Python, A2A client).

Discovers the five framework-diverse agents through their Agent Cards, runs the four analysts in parallel,
passes their assessments to the Release Manager, and writes release_readiness.md.

    python launch.py --setup && python launch.py          # terminal 1
    python orchestrator.py /path/to/repo                  # terminal 2
"""
import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from a2a_kit.a2a import A2AClient

URLS = {"quality": "http://127.0.0.1:9201", "security": "http://127.0.0.1:9202", "docs": "http://127.0.0.1:9203",
        "licenses": "http://127.0.0.1:9204", "release": "http://127.0.0.1:9205"}
ICON = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}


async def main(repo: Path, out: Path) -> None:
    client = A2AClient()
    try:
        print("Discovering agents:")
        for name, url in URLS.items():
            card = await client.wait_ready(url, seconds=180)
            print(f"  {card['name']}")

        analysts = ["quality", "security", "docs", "licenses"]
        results = await asyncio.gather(*(client.send(URLS[a], {"repo_path": str(repo)}) for a in analysts),
                                       return_exceptions=True)
        assessments: dict[str, dict] = {}
        for name, res in zip(analysts, results):
            if isinstance(res, Exception):
                res = {"agent": name, "framework": "?", "verdict": "fail", "score": 0,
                       "summary": f"agent failed: {res}", "findings": []}
            assessments[name] = res
            print(f"  [{ICON[res['verdict']]}] {res['agent']:<14} ({res['framework']}) score {res['score']}: {res['summary'][:110]}")

        decision = await client.send(URLS["release"], {"repo_path": str(repo), "assessments": assessments})
    finally:
        await client.close()

    print(f"\nDECISION: {decision['decision']}\n{decision['summary']}")
    lines = [f"# Release readiness: {repo.name}\n", f"**Decision: {decision['decision']}**\n", decision["summary"], "",
             "## Must fix before release"] + [f"- {x}" for x in decision["must_fix_before_release"] or ["(none)"]]
    lines += ["", "## Can fix after release"] + [f"- {x}" for x in decision["can_fix_after_release"] or ["(none)"]]
    lines += ["", "## Specialist assessments", "| agent | framework | verdict | score |", "|---|---|---|---|"]
    lines += [f"| {a['agent']} | {a['framework']} | {a['verdict']} | {a['score']} |" for a in assessments.values()]
    for a in assessments.values():
        lines += ["", f"### {a['agent']} ({a['framework']})", a["summary"]]
        lines += [f"- **{f['severity']}** {f['title']}: {f['detail']}" for f in a["findings"]]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({"decision": decision, "assessments": assessments}, indent=2))
    print(f"\nReport: {out}")


if __name__ == "__main__":
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", type=Path)
    ap.add_argument("--out", type=Path, default=Path("release_readiness.md"))
    a = ap.parse_args()
    asyncio.run(main(a.repo.resolve(), a.out))
