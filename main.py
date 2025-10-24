#!/usr/bin/env python3
"""
Trello MCP Connector - Full Version
Author: Nuri Muhammet Birlik
Version: 6.3 (Extended Tools + Logging Fix)
"""

import os
import requests
import logging
from typing import Dict, List, Any
from fastmcp import FastMCP
from dotenv import load_dotenv

# -------------------------------------------------------
# Logging Setup
# -------------------------------------------------------
LOG_FILE = "trello_mcp.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TrelloMCP")

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
        logger.error(f"HTTP error {r.status_code}: {r.text}")
        return {"error": f"HTTP {r.status_code} - {r.text}"}
    except Exception as e:
        logger.error(str(e))
        return {"error": str(e)}


def trello_post(endpoint: str, data: dict) -> Any:
    """Generic POST helper."""
    base_data = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    base_data.update(data)
    try:
        r = requests.post(f"{BASE_URL}/{endpoint}", data=base_data, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"POST {endpoint} failed: {e}")
        return {"error": str(e)}


def trello_put(endpoint: str, data: dict) -> Any:
    """Generic PUT helper."""
    base_data = {"key": TRELLO_KEY, "token": TRELLO_TOKEN}
    base_data.update(data)
    try:
        r = requests.put(f"{BASE_URL}/{endpoint}", data=base_data, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"PUT {endpoint} failed: {e}")
        return {"error": str(e)}

# -------------------------------------------------------
# Pagination Helper
# -------------------------------------------------------
def paginate_search(query: str, limit_per_page: int = 50, max_pages: int = 5) -> List[Dict[str, Any]]:
    """Handle Trello search pagination."""
    all_cards = []
    for page in range(max_pages):
        data = trello_get("search", {
            "query": query,
            "modelTypes": "cards",
            "cards_limit": limit_per_page,
            "card_fields": "name,url,id,desc,closed",
            "cards_page": page,
            "filter": "all"
        })
        if "error" in data:
            logger.warning(f"⚠️ Error while searching: {data['error']}")
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
# Tool: Overview
# -------------------------------------------------------
@server.tool()
async def overview() -> Dict[str, Any]:
    """Fetch user's workspaces, boards, and lists."""
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
                logger.warning(f"Could not get lists for board {b.get('id')}: {e}")

    return {"workspaces": workspaces, "boards": boards, "lists": lists_data}

# -------------------------------------------------------
# Tool: Search Cards
# -------------------------------------------------------
@server.tool()
async def search(query: str) -> Dict[str, Any]:
    """Search Trello cards by keyword (includes archived)."""
    if not query.strip():
        return {"results": []}
    cards = paginate_search(query)
    results = [{
        "id": c["id"],
        "title": c.get("name", "No Title"),
        "text": (c.get("desc")[:200] + "...") if c.get("desc") else "",
        "url": c.get("url", ""),
        "closed": c.get("closed", False)
    } for c in cards]
    return {"results": results}

# -------------------------------------------------------
# Tool: Fetch Card Details
# -------------------------------------------------------
@server.tool()
async def fetch(card_id: str) -> Dict[str, Any]:
    """Get full info about a Trello card."""
    if not card_id.strip():
        return {"error": "Missing card_id"}

    card = trello_get(f"cards/{card_id}", {
        "fields": "name,desc,url,dateLastActivity,idList,idBoard,due,closed",
        "checklists": "all",
        "attachments": "true",
        "members": "true",
        "member_fields": "fullName,username,avatarUrl"
    })

    if "error" in card:
        return {"error": card["error"]}

    list_info = trello_get(f"lists/{card.get('idList')}", {"fields": "name,idBoard"})
    board_info = trello_get(f"boards/{card.get('idBoard')}", {"fields": "name,url,idOrganization"})
    org_info = {}
    if board_info.get("idOrganization"):
        org_info = trello_get(f"organizations/{board_info['idOrganization']}", {"fields": "displayName,name"})

    comments = trello_get(f"cards/{card_id}/actions", {"filter": "commentCard", "limit": 100})
    if isinstance(comments, dict) and "error" in comments:
        comments = []

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
        "comments": [{
            "id": c.get("id"),
            "date": c.get("date"),
            "memberCreator": c.get("memberCreator", {}).get("fullName"),
            "text": c.get("data", {}).get("text", "")
        } for c in comments if isinstance(c, dict)],
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
# 🧩 New Tools
# -------------------------------------------------------
@server.tool()
async def create_card(list_id: str, name: str, desc: str = "") -> Dict[str, Any]:
    """Create a new Trello card."""
    data = {"idList": list_id, "name": name, "desc": desc}
    result = trello_post("cards", data)
    return result

@server.tool()
async def update_card(card_id: str, name: str = None, desc: str = None, due: str = None, closed: bool = None) -> Dict[str, Any]:
    """Update an existing Trello card."""
    update_data = {}
    if name: update_data["name"] = name
    if desc: update_data["desc"] = desc
    if due: update_data["due"] = due
    if closed is not None: update_data["closed"] = str(closed).lower()
    result = trello_put(f"cards/{card_id}", update_data)
    return result

@server.tool()
async def add_comment(card_id: str, text: str) -> Dict[str, Any]:
    """Add a comment to a card."""
    result = trello_post(f"cards/{card_id}/actions/comments", {"text": text})
    return result

@server.tool()
async def move_card(card_id: str, list_id: str) -> Dict[str, Any]:
    """Move a card to another list."""
    result = trello_put(f"cards/{card_id}", {"idList": list_id})
    return result

@server.tool()
async def archive_card(card_id: str) -> Dict[str, Any]:
    """Archive (close) a card."""
    result = trello_put(f"cards/{card_id}/closed", {"value": "true"})
    return result

# -------------------------------------------------------
# Run
# -------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Starting Trello MCP server on http://localhost:8000")
    print("🌐 MCP Discovery: http://localhost:8000/.well-known/mcp")
    print("🟢 SSE Handshake: /sse/")
    print("\n🔧 Registered Tools:")

    # ✅ Safe for all FastMCP versions
    try:
        loaded_tools = getattr(server, "_tools", getattr(server, "registry", {}))
        if loaded_tools:
            for tool_name, tool_data in loaded_tools.items():
                desc = getattr(tool_data, "description", "No description")
                print(f"   🛠️  {tool_name} → {desc}")
                logger.info(f"Tool loaded: {tool_name}")
            print(f"\n✅ Total Tools Loaded: {len(loaded_tools)}")
            logger.info(f"{len(loaded_tools)} tools loaded successfully.")
        else:
            print("⚠️ No tools found. Check your @server.tool() decorators.")
            logger.warning("No tools found.")
    except Exception as e:
        print(f"❌ Error listing tools: {e}")
        logger.error(f"Error listing tools: {e}")

    print("=" * 60)
    server.run(transport="sse", host="0.0.0.0", port=8000)
