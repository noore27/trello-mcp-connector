#!/usr/bin/env python3
"""
Trello MCP-Compatible Connector Server - ChatGPT Handshake Final Fix ✅
Author: Nuri Muhammet Birlik
Version: 3.8 (SSE Ping - Text Stream, Immediate Close)
Purpose: Full compatibility with ChatGPT MCP handshake (even behind Cloudflare)
"""

import os
import json
import requests
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# -------------------------------------------------------
# Load environment
# -------------------------------------------------------
load_dotenv()

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------
TRELLO_API_KEY = os.getenv("TRELLO_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BASE = "https://api.trello.com/1"

if not TRELLO_API_KEY or not TRELLO_TOKEN:
    raise ValueError("❌ Missing TRELLO_KEY or TRELLO_TOKEN in .env file")

app = FastAPI(
    title="Trello MCP Connector",
    description="MCP-compatible connector to access Trello boards and cards",
    version="3.8.0"
)

# -------------------------------------------------------
# Models
# -------------------------------------------------------
class SearchRequest(BaseModel):
    query: str

class FetchRequest(BaseModel):
    card_id: str

# -------------------------------------------------------
# Helper: Trello GET
# -------------------------------------------------------
def trello_get(endpoint: str, params: dict = None):
    base = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    if params:
        base.update(params)
    r = requests.get(f"{TRELLO_BASE}/{endpoint}", params=base, timeout=15)
    r.raise_for_status()
    return r.json()

# -------------------------------------------------------
# Root
# -------------------------------------------------------
@app.get("/")
def root():
    return {"status": "ok", "message": "✅ Trello MCP Connector is running"}

# -------------------------------------------------------
# MCP Metadata
# -------------------------------------------------------
@app.get("/.well-known/mcp")
def mcp_info_get():
    """Discovery endpoint for MCP"""
    return {
        "name": "Trello MCP Connector",
        "version": "1.0",
        "description": "Access Trello boards and cards",
        "capabilities": {"resources": {}, "tools": ["search", "fetch"]},
        "tools": [
            {
                "name": "search",
                "description": "Search Trello cards by keyword",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for Trello cards"
                        }
                    },
                    "required": ["query"]
                },
            },
            {
                "name": "fetch",
                "description": "Get detailed information about a specific Trello card",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "card_id": {
                            "type": "string",
                            "description": "ID of the Trello card to fetch"
                        }
                    },
                    "required": ["card_id"]
                },
            },
        ],
    }

@app.post("/.well-known/mcp")
def mcp_info_post():
    return mcp_info_get()

# -------------------------------------------------------
# MCP Tools
# -------------------------------------------------------
@app.post("/tools/search")
async def mcp_search(request: Request):
    try:
        body = await request.json()
        print(f"🔍 Search request received: {body}")
        query = body.get("arguments", {}).get("query", "")

        if not query:
            return {"content": [{"type": "text", "text": json.dumps({"results": []})}]}

        data = trello_get("search", {
            "query": query,
            "modelTypes": "cards",
            "cards_limit": 10,
            "card_fields": "name,url,id,desc",
        })

        results = [
            {
                "id": c["id"],
                "title": c.get("name", "No Title"),
                "url": c.get("url", ""),
                "description": (c.get("desc")[:100] + "...") if c.get("desc") else "",
            }
            for c in data.get("cards", [])
        ]

        print(f"✅ Search found {len(results)} results")
        return {"content": [{"type": "text", "text": json.dumps({"results": results}, ensure_ascii=False)}]}
    except Exception as e:
        print(f"❌ Search error: {e}")
        return JSONResponse(status_code=500, content={
            "content": [{"type": "text", "text": json.dumps({"error": str(e)}, ensure_ascii=False)}]
        })

@app.post("/tools/fetch")
async def mcp_fetch(request: Request):
    try:
        body = await request.json()
        print(f"📥 Fetch request received: {body}")
        card_id = body.get("arguments", {}).get("card_id", "")

        if not card_id:
            return JSONResponse(status_code=400, content={
                "content": [{"type": "text", "text": json.dumps({"error": "Missing card_id"}, ensure_ascii=False)}]
            })

        card = trello_get(f"cards/{card_id}", {
            "fields": "name,desc,url,dateLastActivity,idList",
            "members": "true",
            "member_fields": "fullName,username",
        })
        list_info = trello_get(f"lists/{card.get('idList')}")

        result = {
            "id": card.get("id"),
            "title": card.get("name", "No Title"),
            "text": card.get("desc", "No description"),
            "url": card.get("url", ""),
            "metadata": {
                "source": "trello",
                "lastActivity": card.get("dateLastActivity", ""),
                "list": list_info.get("name", ""),
                "listId": card.get("idList", ""),
            },
        }

        print(f"✅ Fetch completed for card: {result['title']}")
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return JSONResponse(status_code=500, content={
            "content": [{"type": "text", "text": json.dumps({"error": str(e)}, ensure_ascii=False)}]
        })

# -------------------------------------------------------
# SSE Endpoints (Real ping - text/event-stream)
# -------------------------------------------------------
@app.options("/sse/")
def sse_options():
    return Response(status_code=204)

@app.get("/sse/")
async def sse_get():
    """Send one real SSE ping then close (forces ChatGPT handshake)"""
    print("📡 GET /sse/ -> sending SSE ping event and closing ✅")

    async def event_stream():
        yield "event: ping\ndata: ok\n\n"
        await asyncio.sleep(0.1)
        return

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Connection": "close"})
@app.options("/.well-known/mcp")
def mcp_options():
    return Response(status_code=204)
@app.post("/sse/")
async def sse_post(request: Request):
    """Some clients (like ChatGPT) POST to /sse/ for handshake ping"""
    print("📡 POST /sse/ -> sending SSE ping event and closing ✅")

    async def event_stream():
        yield "event: ping\ndata: ok\n\n"
        await asyncio.sleep(0.5)
        return

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Connection": "close"})

# -------------------------------------------------------
# Health
# -------------------------------------------------------
@app.get("/health")
def health_check():
    try:
        trello_get("members/me")
        return {"status": "healthy", "trello_connected": True}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# -------------------------------------------------------
# Logging middleware
# -------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"📡 {request.method} {request.url.path}")
    if request.method == "POST" and "/tools/" in str(request.url):
        try:
            body = await request.body()
            if body:
                print(f"📦 Request body: {body.decode()}")
        except:
            pass
    response = await call_next(request)
    print(f"✅ {request.method} {request.url.path} -> {response.status_code}")
    return response

# -------------------------------------------------------
# Run server
# -------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Trello MCP server at http://localhost:8000")
    print("🔧 Ensure .env has TRELLO_KEY and TRELLO_TOKEN")
    print("🌐 MCP Info: http://localhost:8000/.well-known/mcp")
    print("🟢 Handshake SSE Ping: http://localhost:8000/mcp/")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info", access_log=True)
