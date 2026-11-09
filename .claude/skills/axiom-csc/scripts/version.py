"""Version is sourced only from the project metadata shipped by the installer."""
from pathlib import Path
import re

def project_version():
    for parent in Path(__file__).resolve().parents:
        metadata = parent / "pyproject.toml"
        if metadata.is_file():
            match = re.search(r'^version = "([0-9]+\.[0-9]+\.[0-9]+)"$', metadata.read_text(), re.M)
            if match:
                return match.group(1)
    raise RuntimeError("Missing project version metadata")
