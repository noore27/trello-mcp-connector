#!/usr/bin/env python3
"""
Trello MCP Connector - Full Version
Author: Nuri Muhammet Birlik
Version: 6.0 (Production Ready - Full Trello API Coverage)
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
# Helper Functions
# -------------------------------------------------------
def trello_get(endpoint: str, params: dict = None) -> Any:
    """Generic Trello GET request helper with error handling."""
    base_params = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    if params:
        base_params.update(params)
    try:
        r = requests.get(f"{BASE_URL}/{endpoint}", params=base_params, timeout=20)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        return {"error": f"HTTP {r.status_code} - {r.text}"}
    except Exception as e:
        return {"error": str(e)}

def paginate_search(query: str, limit_per_page: int = 50, max_pages: int = 5) -> List[Dict[str, Any]]:
    """
    Manually handle Trello search pagination (since API caps results).
    """
    all_cards = []
    for page in range(max_pages):
        data = trello_get("search", {
            "query": query,
            "modelTypes": "cards",
            "cards_limit": limit_per_page,
            "card_fields": "name,url,id,desc,closed",
            "cards_page": page,
            "filter": "all"  # includes archived
        })
        if "error" in data:
            print(f"⚠️ Error while searching: {data['error']}")
            break

        cards = data.get("cards", [])
        if not cards:
            break
        all_cards.extend(cards)
        if len(cards) < limit_per_page:
            break
    return all_cards

# -------------------------------------------------------
# Initialize MCP server
# -------------------------------------------------------
server = FastMCP(
    name="Trello MCP Connector",
    instructions="Access Trello workspaces, boards, lists, and cards (with comments, attachments, etc.) via MCP tools."
)

# -------------------------------------------------------
# Tool: Overview (Workspaces, Boards, Lists)
# -------------------------------------------------------
@server.tool()
async def overview() -> Dict[str, Any]:
    """
    Fetch user's workspaces, boards, and lists.
    """
    workspaces = trello_get("members/me/organizations", {"fields": "displayName,name,id"})
    boards = trello_get("members/me/boards", {"fields": "name,id,closed,idOrganization,url"})
    lists_data = []

    for b in boards:
        if isinstance(b, dict) and "id" in b:
            try:
                lists = trello_get(f"boards/{b['id']}/lists", {"fields": "name,id,closed"})
                for l in lists:
                    lists_data.append({
                        "workspaceId": b.get("idOrganization"),
                        "board": b["name"],
                        "boardId": b["id"],
                        "listId": l.get("id"),
                        "list": l.get("name"),
                        "closed": l.get("closed", False)
                    })
            except Exception as e:
                print(f"⚠️ Could not get lists for board {b.get('id')}: {e}")

    return {
        "workspaces": workspaces,
        "boards": boards,
        "lists": lists_data
    }

# -------------------------------------------------------
# Tool: Search Cards (Keyword)
# -------------------------------------------------------
@server.tool()
async def search(query: str) -> Dict[str, Any]:
    """
    Search Trello cards by keyword across all boards (supports archived cards, pagination).
    """
    if not query.strip():
        return {"results": []}

    cards = paginate_search(query)
    results = [
        {
            "id": c["id"],
            "title": c.get("name", "No Title"),
            "text": (c.get("desc")[:200] + "...") if c.get("desc") else "",
            "url": c.get("url", ""),
            "closed": c.get("closed", False)
        }
        for c in cards
    ]

    return {"results": results}

# -------------------------------------------------------
# Tool: Fetch Card Details
# -------------------------------------------------------
@server.tool()
async def fetch(card_id: str) -> Dict[str, Any]:
    """
    Get detailed info about a Trello card, including comments, attachments, and checklists.
    """
    if not card_id.strip():
        return {"error": "Missing card_id"}

    # Get main card details
    card = trello_get(f"cards/{card_id}", {
        "fields": "name,desc,url,dateLastActivity,idList,idBoard,due,closed",
        "checklists": "all",
        "attachments": "true",
        "members": "true",
        "member_fields": "fullName,username,avatarUrl"
    })

    if "error" in card:
        return {"error": card["error"]}

    # Related info
    list_info = trello_get(f"lists/{card.get('idList')}", {"fields": "name,idBoard"})
    board_info = trello_get(f"boards/{card.get('idBoard')}", {"fields": "name,url,idOrganization"})
    org_info = {}
    if board_info.get("idOrganization"):
        org_info = trello_get(f"organizations/{board_info['idOrganization']}", {"fields": "displayName,name"})

    # Comments
    comments = trello_get(f"cards/{card_id}/actions", {"filter": "commentCard", "limit": 100})
    if isinstance(comments, dict) and "error" in comments:
        comments = []

    # Build response
    return {
        "id": card.get("id"),
        "title": card.get("name", "No Title"),
        "text": card.get("desc", "No description"),
        "url": card.get("url", ""),
        "due": card.get("due"),
        "closed": card.get("closed", False),
        "members": card.get("members", []),
        "checklists": card.get("checklists", []),
        "attachments": card.get("attachments", []),
        "comments": [
            {
                "id": c.get("id"),
                "date": c.get("date"),
                "memberCreator": c.get("memberCreator", {}).get("fullName"),
                "text": c.get("data", {}).get("text", "")
            } for c in comments if isinstance(c, dict)
        ],
        "metadata": {
            "source": "trello",
            "lastActivity": card.get("dateLastActivity"),
            "list": list_info.get("name", ""),
            "board": board_info.get("name", ""),
            "boardUrl": board_info.get("url", ""),
            "workspace": org_info.get("displayName", "") if org_info else None
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
