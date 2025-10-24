#!/usr/bin/env python3
"""
Trello MCP Connector - FastMCP Version (ChatGPT Compatible)
Author: Nuri Muhammet Birlik
Version: 4.0
"""

import os
import requests
from typing import Dict, List, Any
from fastmcp import FastMCP
from dotenv import load_dotenv

# -------------------------------------------------------
# Load .env
# -------------------------------------------------------
load_dotenv()
TRELLO_KEY = os.getenv("TRELLO_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
BASE_URL = "https://api.trello.com/1"

if not TRELLO_KEY or not TRELLO_TOKEN:
    raise ValueError("❌ Missing TRELLO_KEY or TRELLO_TOKEN in .env file")

# -------------------------------------------------------
# Helper
# -------------------------------------------------------
def trello_get(endpoint: str, params: dict = None):
    base_params = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    if params:
        base_params.update(params)
    r = requests.get(f"{BASE_URL}/{endpoint}", params=base_params, timeout=15)
    r.raise_for_status()
    return r.json()

# -------------------------------------------------------
# Initialize MCP server
# -------------------------------------------------------
server = FastMCP(
    name="Trello MCP Connector",
    instructions="Access Trello boards and cards via MCP tools (search and fetch)."
)

# -------------------------------------------------------
# Tool: Search
# -------------------------------------------------------
@server.tool()
async def search(query: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Search Trello cards by keyword.
    """
    if not query.strip():
        return {"results": []}

    data = trello_get("search", {
        "query": query,
        "modelTypes": "cards",
        "cards_limit": 10,
        "card_fields": "name,url,id,desc"
    })

    results = [
        {
            "id": c["id"],
            "title": c.get("name", "No Title"),
            "text": (c.get("desc")[:200] + "...") if c.get("desc") else "",
            "url": c.get("url", "")
        }
        for c in data.get("cards", [])
    ]

    return {"results": results}

# -------------------------------------------------------
# Tool: Fetch
# -------------------------------------------------------
@server.tool()
async def fetch(card_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a Trello card.
    """
    if not card_id.strip():
        return {"error": "Missing card_id"}

    card = trello_get(f"cards/{card_id}", {
        "fields": "name,desc,url,dateLastActivity,idList",
        "members": "true",
        "member_fields": "fullName,username"
    })
    list_info = trello_get(f"lists/{card.get('idList')}")

    return {
        "id": card.get("id"),
        "title": card.get("name", "No Title"),
        "text": card.get("desc", "No description"),
        "url": card.get("url", ""),
        "metadata": {
            "source": "trello",
            "lastActivity": card.get("dateLastActivity", ""),
            "list": list_info.get("name", ""),
            "listId": card.get("idList", "")
        }
    }

# -------------------------------------------------------
# Run
# -------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Starting Trello MCP server on http://localhost:8000")
    print("🌐 MCP Discovery: http://localhost:8000/.well-known/mcp")
    print("🟢 SSE Handshake: /sse/ (handled automatically by FastMCP)")
    server.run(transport="sse", host="0.0.0.0", port=8000)
