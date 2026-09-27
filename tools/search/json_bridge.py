#!/usr/bin/env python3
"""
json_bridge.py — High-speed JSON bridge between Python providers and the Rust Ratatui TUI.
"""

import sys
import os
import json
import dataclasses

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools.search.orchestrator import multi_search


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No query provided", "results": []}))
        sys.exit(1)

    query = " ".join(sys.argv[1:]).strip()
    try:
        results = multi_search(query)
        dict_results = [dataclasses.asdict(r) for r in results]
        print(json.dumps({"status": "success", "query": query, "count": len(dict_results), "results": dict_results}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e), "results": []}))
        sys.exit(1)


if __name__ == "__main__":
    main()
