from pathlib import Path
from fnmatch import fnmatch
import yaml


def load_annotations(path: str, missing_ok: bool = False) -> dict:
    if not Path(path).exists():
        if missing_ok:
            return {}
        raise FileNotFoundError(f"Annotations file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


def save_annotations(data: dict, path: str):
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def match_patterns(path: str, patterns: list[str] | str) -> bool:
    """Check if a path matches any wildcard in patterns."""
    if isinstance(patterns, str):
        patterns = [patterns]
    return any(fnmatch(path, pattern) for pattern in patterns)
