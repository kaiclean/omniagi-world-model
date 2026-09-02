import json
import sys
from pathlib import Path

# Harness root — resolve relative to this script so it's portable across machines
HARNESS_ROOT = Path(__file__).resolve().parent.parent

# Routing table: keyword groups -> (specialist, engine seat)
ROUTES = [
    (["code", "build", "implement", "fix", "refactor", "debug", "tool"],
     "coder", "Qwen3-Coder-480B-A35B"),
    (["analyze", "plan", "design", "think", "reason", "strategy", "architecture"],
     "reasoner", "Qwen3.5-397B-A17B"),
    (["check", "verify", "audit", "test", "review", "critique"],
     "critic", "DeepSeek-R1"),
    (["search", "scan", "retrieve", "scout", "find", "lookup"],
     "scout", "Qwen3.6-35B-A3B"),
    (["memory", "remember", "consolidate", "recall", "summarize"],
     "memory_keeper", "Qwen3.5-122B-A10B"),
]

def route_task(task_description):
    """Analyze a task and recommend a specialist + engine seat."""
    task = task_description.lower()
    for keywords, specialist, engine in ROUTES:
        if any(k in task for k in keywords):
            return {
                "specialist": specialist,
                "engine": engine,
                "rationale": (
                    f"Task '{task_description}' mapped to {specialist} "
                    f"using engine {engine}"
                ),
            }
    # Default fallback: router with local always-on executor
    return {
        "specialist": "router",
        "engine": "Qwen3.5-9B-HauhauCS (Local)",
        "rationale": (
            f"Task '{task_description}' has no strong specialist signal; "
            "routed to router with local executor"
        ),
    }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No task provided"}))
        sys.exit(1)
    task = " ".join(sys.argv[1:])
    print(json.dumps(route_task(task)))
