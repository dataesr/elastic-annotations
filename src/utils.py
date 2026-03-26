from pathlib import Path
from fnmatch import fnmatch
import yaml
import json


def load_schema(path: str, missing_ok: bool = False) -> dict:
    """Load JSON schema from a file."""
    if not Path(path).exists():
        if missing_ok:
            return {}
        raise FileNotFoundError(f"Schema file not found: {path}")
    with open(path) as f:
        return json.load(f)


def load_annotations(path: str, missing_ok: bool = False) -> dict:
    """Load annotations from a YAML file."""
    if not Path(path).exists():
        if missing_ok:
            return {}
        raise FileNotFoundError(f"Annotations file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f) or {}


def save_annotations(data: dict, path: str):
    """Save annotations to a YAML file."""
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def match_patterns(path: str, patterns: list[str] | str) -> bool:
    """Check if a path matches any wildcard in patterns."""
    if isinstance(patterns, str):
        patterns = [patterns]
    return any(fnmatch(path, pattern) for pattern in patterns)


def get_config(index: str) -> dict:
    """Load and return the configuration for a given index from the configs/ directory."""
    config_path = Path("configs") / f"{index}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)
        if index not in data:
            raise ValueError(f"Index '{index}' not found in configuration file: {config_path}")
        return data[index]
