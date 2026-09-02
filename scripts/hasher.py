import hashlib
from pathlib import Path

def hash_file(rel_path):
    p = Path("/Users/kaileanhard/research/omniagi-world-model") / rel_path
    if not p.exists(): return "Error: File not found"
    return hashlib.sha256(p.read_bytes()).hexdigest()

if __name__ == "__main__":
    import sys
    print(hash_file(sys.argv[1]))
