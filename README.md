# Polyglot Release-Readiness Mesh (5 frameworks over A2A)

**Framework:** smolagents + Pydantic AI + LangGraph + OpenAI Agents SDK + Google ADK, linked by A2A  
**Agents:** 6

Five agents, each built in a DIFFERENT framework and running as its own A2A service (in its own virtualenv, so their conflicting dependencies never meet), assess a repository for release. A plain-Python orchestrator discovers them and combines the results into a go/no-go report.

> **Status:** this project was written as complete, runnable code but has **not been executed end to end against live LLM APIs** yet. It needs your own API key; expect to fix small issues from provider or library version changes. Issues and PRs welcome.

## Agents

| # | Agent | Role |
|---|---|---|
| 1 | Code Quality | smolagents ToolCallingAgent |
| 2 | Security | Pydantic AI, typed output |
| 3 | Documentation | LangGraph (collect -> judge -> suggest) |
| 4 | Licenses | OpenAI Agents SDK, live PyPI lookups |
| 5 | Release Manager | Google ADK, go/no-go decision |
| 6 | Release Orchestrator | A2A client in plain Python |

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env
python launch.py --setup   # one venv per agent
python launch.py            # terminal 1
python orchestrator.py /path/to/repo   # terminal 2
```

## How it works

Demonstrates interoperability: the orchestrator neither knows nor cares which framework is behind each Agent Card.

## Configuration

See `.env.example`. Models are chosen with one `LLM_SPEC` variable so you can switch provider without touching code.

## License

MIT
