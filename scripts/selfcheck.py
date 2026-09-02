#!/usr/bin/env python3
"""
OmniAGI harness self-extension demo + harness integrity checker.

Demonstrates the full loop:
  1. Read TOOLS.md (existing tools)
  2. Detect a deliberately missing tool ("summarize_url")
  3. Create the tool spec under tools/
  4. Register it in TOOLS.md
  5. Verify by reading both files back and grepping for the new tool id
  6. Append changelog entry

Also prints a harness inventory + single-master enforcement check.
"""
from __future__ import annotations
import os
import re
import sys
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS_MD = ROOT / "TOOLS.md"
TOOLS_DIR = ROOT / "tools"
CHANGES = ROOT / "memory" / "CHANGELOG.md"
AGENTS = ROOT / "WORLD_AGENTS.md"
OMNI = ROOT / "OmniAGI.md"
MEMORY = ROOT / "MEMORY.md"

DEMO_TOOL_ID = "summarize_url"
DEMO_TOOL_SPEC = TOOLS_DIR / "summarize_url.md"

def log(msg):
    print(f"[omniagi-selfcheck] {msg}", flush=True)

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def step1_read_tools():
    log("Step 1: read TOOLS.md")
    txt = read(TOOLS_MD)
    assert txt, "TOOLS.md missing"
    ids = re.findall(r"^\| `([^`]+)`", txt, flags=re.M)
    log(f"  existing tool ids: {ids}")
    return ids

def step2_detect_gap(ids):
    log(f"Step 2: detect gap — looking for '{DEMO_TOOL_ID}'")
    present = DEMO_TOOL_ID in ids
    log(f"  present? {present}")
    return not present  # True = gap exists

def step3_create_spec():
    log("Step 3: create tool spec tools/summarize_url.md")
    spec = f"""# Tool: {DEMO_TOOL_ID}
Added by OmniAGI self-extension demo on {datetime.now().date()}.

## Purpose
Fetch a URL and return a compact summary.

## Inputs
- url (str): the page to summarize
- max_words (int, default 120)

## Outputs
- summary (str): condensed content
- source_url (str)

## How to invoke
- Hermes: fetch URL via browser_exec / web_search, then summarize with a model_route call
- Shell: `curl -sL <url> | python3 -c "import sys,summarizer; summarizer.go()"` (illustrative)

## Dependencies
- network access
- a model seat from workflows/model-routing.md

## Verification
- Dry-run: summarize a known small URL and confirm a <max_words non-empty summary is returned.
"""
    DEMO_TOOL_SPEC.write_text(spec, encoding="utf-8")
    log(f"  wrote {DEMO_TOOL_SPEC} ({len(spec)} bytes)")
    return spec

def step4_register_in_tools_md():
    log("Step 4: register in TOOLS.md")
    txt = read(TOOLS_MD)
    row = f"| `{DEMO_TOOL_ID}` | Summarize a URL | `tools/summarize_url.md` | active | Demo-added via self-extension |"
    # insert before the blank line that precedes "## Extension contract"
    marker = "\n## Extension contract"
    if marker not in txt:
        raise RuntimeError("TOOL.md structure changed; marker not found")
    new_txt = txt.replace(marker, "\n" + row + marker)
    TOOLS_MD.write_text(new_txt, encoding="utf-8")
    log(f"  inserted row: {row}")

def step5_verify():
    log("Step 5: verify")
    tools_txt = read(TOOLS_MD)
    spec_txt = read(DEMO_TOOL_SPEC)
    id_present = f"`{DEMO_TOOL_ID}`" in tools_txt
    spec_present = len(spec_txt) > 0 and DEMO_TOOL_ID in spec_txt
    log(f"  TOOLS.md has row: {id_present}")
    log(f"  spec file non-empty & contains id: {spec_present}")
    return id_present and spec_present

def step6_changelog():
    log("Step 6: append changelog")
    CHANGES.parent.mkdir(parents=True, exist_ok=True)
    entry = f"- {datetime.now().date()} tool_added: {DEMO_TOOL_ID} (self-extension demo) verified=True\n"
    with open(CHANGES, "a", encoding="utf-8") as f:
        f.write(entry)
    log(f"  appended: {entry.strip()}")

def inventory():
    log("=== Harness inventory ===")
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and ".git" not in p.parts:
            rel = p.relative_to(ROOT)
            print(f"  {rel}  ({p.stat().st_size} bytes)")
    # single-master enforcement check
    log("=== Single-master enforcement ===")
    agents_txt = read(AGENTS)
    omni_txt = read(OMNI)
    mem_txt = read(MEMORY)
    masters = re.findall(r"Count:\*?\*?\s*exactly\s*1", agents_txt)
    omni_single = "sole master" in omni_txt.lower() or "sole master" in mem_txt.lower()
    log(f"  WORLD_AGENTS.md 'Count: exactly 1': {bool(masters)}")
    log(f"  'sole master' language present: {omni_single}")
    return bool(masters) and omni_single

def main():
    print("OmniAGI self-extension + integrity check")
    print("=" * 50)
    ids = step1_read_tools()
    gap = step2_detect_gap(ids)
    if not gap:
        # Demo already ran before — re-run cleanly by removing the spec row first
        log("demo already ran; cleaning prior demo row for a fresh run")
        txt = read(TOOLS_MD)
        cleaned = re.sub(rf"\n\| `{DEMO_TOOL_ID}`.*\n", "\n", txt)
        TOOLS_MD.write_text(cleaned, encoding="utf-8")
        if DEMO_TOOL_SPEC.exists():
            DEMO_TOOL_SPEC.unlink()
        ids = step1_read_tools()
        gap = step2_detect_gap(ids)
    if gap:
        step3_create_spec()
        step4_register_in_tools_md()
    ok = step5_verify()
    if ok:
        step6_changelog()
    single_ok = inventory()
    log(f"self-extension verified: {ok}")
    log(f"single-master enforced: {single_ok}")
    print("=" * 50)
    if ok and single_ok:
        print("RESULT: PASS")
        return 0
    print("RESULT: FAIL")
    return 1

if __name__ == "__main__":
    sys.exit(main())