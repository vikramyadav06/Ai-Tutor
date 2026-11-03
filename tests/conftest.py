import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_tool(name):
    """Import tools/<name>.py as a module (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location(f"tool_{name}", REPO / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def learner_tool():
    return load_tool("learner")


@pytest.fixture(scope="session")
def log_tool():
    return load_tool("log_session")


@pytest.fixture(scope="session")
def validate_tool():
    return load_tool("validate")


@pytest.fixture
def tutor_root(tmp_path):
    """A throwaway repo root: a copy of core/ plus the fixture subjects (as if a tutor had
    generated them), and no learner/ or .tutor/ yet."""
    root = tmp_path / "repo"
    shutil.copytree(REPO / "core", root / "core")
    index_path = root / "core" / "subjects" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for folder in sorted((FIXTURES / "subjects").iterdir()):
        shutil.copytree(folder, root / "core" / "subjects" / folder.name)
        catalog = json.loads((folder / "catalog.json").read_text(encoding="utf-8"))
        index["subjects"].append({"id": folder.name, "title": catalog["title"],
                                  "levels": catalog["levels"], "path": f"core/subjects/{folder.name}"})
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return root


@pytest.fixture
def run_tool(tutor_root):
    """Run a tool as the agent would, from the command line, against tutor_root."""
    def run(name, *args, check=True):
        env = {**os.environ, "TUTOR_ROOT": str(tutor_root)}
        result = subprocess.run([sys.executable, str(REPO / "tools" / f"{name}.py"), *args],
                                capture_output=True, text=True, env=env, cwd=tutor_root)
        if check and result.returncode != 0:
            raise AssertionError(f"{name} {args} failed ({result.returncode}): {result.stderr}")
        return result
    return run
