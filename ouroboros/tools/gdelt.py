from ouroboros.tools.registry import ToolContext, ToolEntry


def _gdelt_search(ctx: ToolContext, query: str, timespan: str = "last3months", coverage: int = 50) -> str:
    """Search GDELT Project news events.
    
    Args:
        query: Free-text search (e.g., "climate protest Russia")
        timespan: Time window (e.g., "last3months", "2025-01-01,2025-03-01")
        coverage: Minimum number of sources covering the event
    
    Returns:
        Human-readable Markdown with event summaries
    """
    import requests
    
    base_url = "https://api.gdeltproject.org/api/v2/doc/doc"
    
    params = {
        "query": query,
        "timespan": timespan,
        "coverage": coverage,
        "format": "json",
    }
    
    try:
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"Error fetching from GDELT: {e}"
    
    data = resp.json()
    
    if "documents" not in data or not data["documents"]:
        return f"No events found for \"{query}\" in {timespan}."
    
    docs = data["documents"][:10]
    
    output = f"**GDELT news search: \"{query}\"**\n"
    output += f"Found {len(docs)} top events in {timespan}\n\n"
    
    for i, doc in enumerate(docs, 1):
        title = doc.get("title", "Untitled")[0] if doc.get("title") else "Untitled"
        date = doc.get("date", "Unknown date")
        sourceurl = doc.get("sourceurl", "")
        tone = doc.get("gentone", "N/A")
        output += f"{i}. [{title}]({sourceurl})\n"
        output += f"   Date: {date} | Tone: {tone}\n"
        output += f"   Source: {sourceurl}\n\n"
    
    return output


def get_tools() -> list[ToolEntry]:
    return [
        ToolEntry(
            name="gdelt_search",
            description="Search GDELT Project global news events",
            func=_gdelt_search,
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g., 'climate protest Russia')"},
                    "timespan": {"type": "string", "description": "Time window (e.g., 'last3months', '2025-01-01,2025-03-01')", "default": "last3months"},
                    "coverage": {"type": "integer", "description": "Minimum number of sources", "default": 50},
                },
                "required": ["query"],
            },
        ),
    ]
