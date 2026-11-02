"""Create one virtualenv per agent (their frameworks have conflicting dependencies - that is the point of A2A:
each agent is an independent service), then start all five A2A servers.

    python launch.py --setup      # create .venvs/<agent> and pip install each agent's requirements (once)
    python launch.py              # start the five agents (Ctrl+C stops them)
"""
import argparse
import os
import subprocess
import sys
import time
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENTS = {"quality": 9201, "security": 9202, "docs": 9203, "licenses": 9204, "release": 9205}


def venv_python(name: str) -> Path:
    base = ROOT / ".venvs" / name
    return base / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def setup() -> None:
    for name in AGENTS:
        py = venv_python(name)
        if not py.exists():
            print(f"[{name}] creating virtualenv ...")
            venv.EnvBuilder(with_pip=True).create(ROOT / ".venvs" / name)
        print(f"[{name}] installing requirements ...")
        subprocess.check_call([str(py), "-m", "pip", "install", "-q", "-r", str(ROOT / "mesh_agents" / name / "requirements.txt")])
    print("setup complete")


def start() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")  # LLM_SPEC and API keys are inherited by every agent process
    except ImportError:
        pass
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    procs = []
    for name, port in AGENTS.items():
        py = venv_python(name)
        if not py.exists():
            raise SystemExit(f"{py} not found - run: python launch.py --setup")
        procs.append((name, subprocess.Popen([str(py), "-m", f"mesh_agents.{name}.server"], cwd=ROOT, env=env)))
        print(f"started {name:<9} on http://127.0.0.1:{port}")
    try:
        while True:
            time.sleep(2)
            for name, p in procs:
                if p.poll() is not None:
                    print(f"agent '{name}' exited with code {p.returncode}")
                    raise SystemExit(1)
    except KeyboardInterrupt:
        pass
    finally:
        for _, p in procs:
            p.terminate()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true")
    if ap.parse_args().setup:
        setup()
    else:
        start()
