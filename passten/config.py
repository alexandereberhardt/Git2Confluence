# _system/passten/config.py
import yaml

def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

def get_solution(config: dict, name: str) -> dict:
    solutions = config.get('solutions', {})
    if name not in solutions:
        raise ValueError(f"Solution '{name}' not found. Available: {list(solutions.keys())}")
    return solutions[name]
