"""Command-line bridge to the simulated company apps (Zapier AutomationBench, MIT).

The whole company (inbox, sheets, slack, crm...) lives in one JSON file.
Every call loads it, runs one API call against it, and saves it back.

    company search "gmail send message"
    company fetch GET  https://gmail.googleapis.com/gmail/v1/users/me/messages
    company fetch POST <url> --body '{"to": "...", "subject": "...", "body": "..."}'
"""

import argparse
import json
import os
import sys
from pathlib import Path

from automationbench.schema.world import WorldState
from automationbench.tools.api import api_fetch, api_search

WORLD = Path(os.environ.get("COMPANY_WORLD", "/var/company/world.json"))


def load() -> WorldState:
    return WorldState(**json.loads(WORLD.read_text()))


def save(world: WorldState) -> None:
    WORLD.write_text(world.model_dump_json(by_alias=True))


def main() -> None:
    p = argparse.ArgumentParser(prog="company", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="find API endpoints by keyword")
    s.add_argument("query")
    s.add_argument("--top-k", type=int, default=5)
    f = sub.add_parser("fetch", help="call an API endpoint")
    f.add_argument("method")
    f.add_argument("url")
    f.add_argument("--params", help="query parameters as JSON")
    f.add_argument("--body", help="request body as JSON")
    a = p.parse_args()

    if a.cmd == "search":
        print(api_search(a.query, a.top_k))
        return
    world = load()
    out = api_fetch(world, a.method.upper(), a.url, a.params, a.body)
    save(world)
    print(out)


if __name__ == "__main__":
    sys.exit(main())
