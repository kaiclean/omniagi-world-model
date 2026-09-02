# Tool: summarize_url
Added by OmniAGI self-extension demo on 2026-09-02.

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
