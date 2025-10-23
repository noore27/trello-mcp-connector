#!/usr/bin/env python3
"""
Trello MCP-Compatible Connector Server - ChatGPT Final MCP Spec ✅
Author: Nuri Muhammet Birlik
Version: 4.0 (Spec-Compliant SSE + MCP Discovery)
Purpose: Fully MCP-compatible FastAPI server for ChatGPT connectors
"""

import os
import json
import asyncio
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
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
    version="4.0.0"
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
# MCP Discovery Endpoint
# -------------------------------------------------------
@app.get("/.well-known/mcp")
def mcp_info_get():
    """MCP discovery info (required by ChatGPT)"""
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
                "description": "Fetch detailed information about a specific Trello card",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "card_id": {
                            "type": "string",
                            "description": "Trello card ID"
                        }
                    },
                    "required": ["card_id"]
                },
            },
        ],
    }

@app.options("/.well-known/mcp")
def mcp_options():
    return Response(status_code=204)

# -------------------------------------------------------
# MCP Tools
# -------------------------------------------------------
@app.post("/tools/search")
async def mcp_search(request: Request):
    try:
        body = await request.json()
        query = body.get("arguments", {}).get("query", "")
        print(f"🔍 Search query: {query}")

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
        print(f"✅ Found {len(results)} results")
        return {"content": [{"type": "text", "text": json.dumps({"results": results}, ensure_ascii=False)}]}
    except Exception as e:
        print(f"❌ Search error: {e}")
        return JSONResponse(status_code=500, content={
            "content": [{"type": "text", "text": json.dumps({"error": str(e)})}]
        })

@app.post("/tools/fetch")
async def mcp_fetch(request: Request):
    try:
        body = await request.json()
        card_id = body.get("arguments", {}).get("card_id", "")
        print(f"📥 Fetch card: {card_id}")

        if not card_id:
            return JSONResponse(status_code=400, content={
                "content": [{"type": "text", "text": json.dumps({"error": "Missing card_id"})}]
            })

        card = trello_get(f"cards/{card_id}", {
            "fields": "name,desc,url,dateLastActivity,idList",
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
                "list": list_info.get("name", "")
            }
        }
        print(f"✅ Fetched card {result['title']}")
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return JSONResponse(status_code=500, content={
            "content": [{"type": "text", "text": json.dumps({"error": str(e)})}]
        })

# -------------------------------------------------------
# SSE Endpoint (MCP Handshake Ping)
# -------------------------------------------------------
@app.get("/sse/")
async def sse_get():
    """Compliant SSE ping endpoint for ChatGPT handshake"""
    print("📡 GET /sse/ -> sending MCP-compliant SSE ping ✅")

    async def event_stream():
        yield "event: ping\ndata: ok\n\n"
        await asyncio.sleep(0.2)
        yield "event: close\ndata: bye\n\n"

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked"
    }

    return StreamingResponse(event_stream(), headers=headers)

@app.post("/sse/")
async def sse_post():
    """Fallback for POST-based ping clients"""
    print("📡 POST /sse/ -> returning JSON ping ✅")
    return JSONResponse({"ping": "ok", "source": "sse-fallback"})

@app.options("/sse/")
def sse_options():
    return Response(status_code=204)

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
    response = await call_next(request)
    print(f"✅ {request.method} {request.url.path} -> {response.status_code}")
    return response

# -------------------------------------------------------
# Run Server
# -------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))  # Render assigns dynamic port
    print(f"🚀 Starting Trello MCP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
