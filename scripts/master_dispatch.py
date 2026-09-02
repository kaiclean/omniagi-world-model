import json
import sys
from pathlib import Path

# Harness definitions
HARNESS_ROOT = Path("/Users/kaileanhard/research/omniagi-world-model/")

def route_task(task_description):
    """Analyzes a task and recommends a specialist + engine seat."""
    task = task_description.lower()
    
    # Simple routing heuristic (to be expanded by the self-extension workflow)
    if any(k in task for k in ["code", "build", "implement", "fix"]):
        specialist = "coder"
        engine = "Qwen3-Coder-480B-A35B"
    elif any(k in task for k in ["analyze", "plan", "design", "think"]):
        specialist = "reasoner"
        engine = "Qwen3.5-397B-A17B"
    elif any(k in task for k in ["check", "verify", "audit", "test"]):
        specialist = "critic"
        engine = "DeepSeek-R1"
    elif any(k in task for k in ["search", "scan", "retrieve"]):
        specialist = "scout"
        engine = "Qwen3.6-35B-A3B"
    else:
        # Default fallback
        specialist = "router"
        engine = "Qwen3.5-9B-HauhauCS (Local)"

    return {
        "specialist": specialist,
        "engine": engine,
        "rationale": f"Task '{task_description}' mapped to {specialist} using engine {engine}"
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No task provided"}))
        sys.exit(1)
        
    task = " ".join(sys.argv[1:])
    decision = route_task(task)
    print(json.dumps(decision))
