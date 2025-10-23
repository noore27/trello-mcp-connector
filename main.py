#!/usr/bin/env python3
"""
Trello MCP-Compatible Connector Server - Final Stable (v6.3)
Author: Nuri Muhammet Birlik
Compatible with ChatGPT MCP (protocol 2024-11-05)
"""

import os
import json
import asyncio
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Configuration
TRELLO_API_KEY = os.getenv("TRELLO_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")
TRELLO_BASE = "https://api.trello.com/1"

if not TRELLO_API_KEY or not TRELLO_TOKEN:
    raise ValueError("❌ Missing TRELLO_KEY or TRELLO_TOKEN in .env")

# App
app = FastAPI(
    title="Trello MCP Connector",
    description="MCP-compatible connector to access Trello boards and cards",
    version="6.3.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trello helper
def trello_get(endpoint: str, params: dict = None):
    base = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    if params:
        base.update(params)
    r = requests.get(f"{TRELLO_BASE}/{endpoint}", params=base, timeout=15)
    r.raise_for_status()
    return r.json()

# Root
@app.get("/")
def root():
    return {"status": "ok", "message": "✅ Trello MCP Connector is running"}

# ---------- MCP Discovery (GET/POST/OPTIONS) ----------
def _mcp_discovery_payload():
    return {
        "name": "trello",
        "version": "1.0.0",
        "description": "Access Trello boards and cards",
        "protocolVersion": "2024-11-05",
        # En kritik kısım: SSE capability ve path
        "capabilities": {
            "sse": {"path": "/sse"},
            "resources": {},
            "tools": {}
        },
        "tools": [
            {
                "name": "search",
                "description": "Search Trello cards by keyword",
                "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"],
                },
            },
            {
                "name": "fetch",
                "description": "Fetch detailed info about a Trello card",
                "inputSchema": {
                "type": "object",
                "properties": {
                    "card_id": {"type": "string", "description": "Trello card ID"}
                },
                "required": ["card_id"],
                },
            },
        ],
    }

def _json_ok(data: dict) -> JSONResponse:
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
    }
    return JSONResponse(content=data, headers=headers)

@app.get("/.well-known/mcp")
def mcp_info_get():
    return _json_ok(_mcp_discovery_payload())

@app.post("/.well-known/mcp")
def mcp_info_post():
    # Bazı istemciler discovery'e POST atıyor; 405 yerine aynı payload'ı dön.
    return _json_ok(_mcp_discovery_payload())

@app.options("/.well-known/mcp")
def mcp_options():
    return Response(status_code=204, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    })

# ---------- SSE (GET + POST) ----------
@app.api_route("/sse", methods=["GET", "POST"])
@app.api_route("/sse/", methods=["GET", "POST"])
async def sse_endpoint(request: Request):
    """MCP-compatible SSE endpoint for ChatGPT"""
    print(f"🔌 MCP SSE connection via {request.method}")

    async def generate_events():
        try:
            # Handshake
            hello = {
                "protocol": "mcp",
                "version": "2024-11-05",
                "capabilities": {},
                "serverInfo": {"name": "trello", "version": "1.0.0"},
            }
            yield f"event: hello\ndata: {json.dumps(hello)}\n\n"

            # Ping loop
            count = 0
            while True:
                await asyncio.sleep(2)
                count += 1
                ping = {"event": "ping", "count": count}
                yield f"event: ping\ndata: {json.dumps(ping)}\n\n"
        except Exception as e:
            err = {"error": str(e)}
            yield f"event: error\ndata: {json.dumps(err)}\n\n"

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "*",
        "Transfer-Encoding": "chunked",
        "X-Accel-Buffering": "no",
    }

    return StreamingResponse(generate_events(), media_type="text/event-stream", headers=headers)

# ---------- Tools ----------
@app.post("/tools/search")
async def mcp_search(request: Request):
    try:
        body = await request.json()
        query = body.get("arguments", {}).get("query", "")
        print(f"🔍 Search query: {query}")

        if not query:
            return {"role": "assistant", "content": [{"type": "text", "text": json.dumps({"results": []})}]}

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
                "description": (c.get("desc")[:120] + "...") if c.get("desc") else "",
            }
            for c in data.get("cards", [])
        ]

        print(f"✅ Found {len(results)} results")
        return {
            "role": "assistant",
            "content": [
                {"type": "text", "text": json.dumps({"results": results}, ensure_ascii=False)}
            ]
        }

    except Exception as e:
        print(f"❌ Search error: {e}")
        return JSONResponse(
            status_code=500,
            content={"role": "assistant", "content": [{"type": "text", "text": json.dumps({"error": str(e)})}]},
        )

@app.post("/tools/fetch")
async def mcp_fetch(request: Request):
    try:
        body = await request.json()
        card_id = body.get("arguments", {}).get("card_id", "")
        print(f"📥 Fetch card: {card_id}")

        if not card_id:
            return JSONResponse(status_code=400, content={
                "role": "assistant",
                "content": [{"type": "text", "text": json.dumps({"error": "Missing card_id"})}],
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
            },
        }

        print(f"✅ Fetched card {result['title']}")
        return {"role": "assistant", "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}

    except Exception as e:
        print(f"❌ Fetch error: {e}")
        return JSONResponse(
            status_code=500,
            content={"role": "assistant", "content": [{"type": "text", "text": json.dumps({"error": str(e)})}]},
        )

# ---------- Health ----------
@app.get("/health")
def health_check():
    try:
        trello_get("members/me")
        return {"status": "healthy", "trello_connected": True}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# ---------- Logging ----------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"📡 {request.method} {request.url.path}")
    response = await call_next(request)
    print(f"✅ {request.method} {request.url.path} -> {response.status_code}")
    return response

# ---------- Run ----------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Starting Trello MCP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, timeout_keep_alive=300)
