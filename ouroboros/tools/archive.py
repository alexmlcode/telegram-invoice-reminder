from ouroboros.tools.registry import ToolContext, ToolEntry


def _archive_search(ctx: ToolContext, query: str, media_type: str = "*", fields: str = "identifier,title,format,creator", rows: int = 10, page: int = 1) -> str:
    """Search Archive.org items by query.
    
    Args:
        query: Search query (e.g., "climate change" or "Python programming")
        media_type: Filter by media type (texts, movies, images, audio, software, web, collection)
        fields: Comma-separated fields to return (identifier, title, format, creator, etc.)
        rows: Number of results per page (max 100)
        page: Page number (1-indexed)
    
    Returns:
        Human-readable Markdown with search results and download links
    """
    import requests
    base_url = "https://archive.org/advancedsearch.php"
    params = {
        "q": query,
        "fl[]": fields.split(","),
        "rows": rows,
        "page": page,
        "output": "json",
    }
    if media_type != "*":
        params["query"] = f"mediatype:{media_type}"
    
    try:
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"Error fetching from Archive.org: {e}"
    
    data = resp.json()
    results = data.get("response", {}).get("docs", [])
    total = data.get("response", {}).get("numFound", 0)
    
    if not results:
        return f"No results found for '{query}' (media_type={media_type})."
    
    output = f"**Archive.org search: '{query}'**\n"
    output += f"Found {total} results, showing {len(results)} on page {page}\n\n"
    
    for item in results:
        identifier = item.get("identifier", "unknown")
        title = item.get("title", ["Untitled"])[0] if item.get("title") else "Untitled"
        creator = item.get("creator", [""])[0] if item.get("creator") else ""
        formats = item.get("format", [])
        
        output += f"### [{title}]({identifier})\n"
        if creator:
            output += f"**by {creator}**\n"
        output += f"**ID:** `{identifier}`\n"
        output += f"**Formats:** {', '.join(formats)}\n"
        output += f"**View:** https://archive.org/details/{identifier}\n"
        output += f"**Download:** https://archive.org/download/{identifier}/{identifier}_archive.torrent\n\n"
    
    return output


def _archive_wayback(ctx: ToolContext, url: str, timestamp: str = None) -> str:
    """Fetch an archived version of a webpage from the Wayback Machine.
    
    Args:
        url: Original URL to archive
        timestamp: Optional archive timestamp in YYYYMMDDHHMMSS format (e.g., 20231015120000)
    
    Returns:
        Markdown with archived page summary or error
    """
    import requests
    import re
    if timestamp:
        archive_url = f"https://web.archive.org/web/{timestamp}/{url}"
    else:
        archive_url = f"https://web.archive.org/web/{url}"
    
    try:
        resp = requests.get(archive_url, timeout=30)
        resp.raise_for_status()
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', resp.text[:5000], re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else "Archived page"
        
        return f"**Archived page:** [{title}]({archive_url})\n\n"
    except requests.RequestException as e:
        return f"Error fetching archive for {url}: {e}"


def _archive_download(ctx: ToolContext, identifier: str, file: str = None) -> str:
    """Download a specific file from an Archive.org item.
    
    Args:
        identifier: Archive item identifier (e.g., 'python-programming-handbook')
        file: Optional specific file name. If None, lists available files.
    
    Returns:
        File content (if file specified) or list of available files
    """
    import requests
    import xml.etree.ElementTree as ET
    base_url = f"https://archive.org/download/{identifier}"
    
    if file:
        file_url = f"{base_url}/{file}"
        try:
            resp = requests.get(file_url, timeout=30)
            resp.raise_for_status()
            content = resp.text[:2000]
            if len(resp.text) > 2000:
                content += "\n[... content truncated ...]"
            return f"**File: {file}**\n\n```text\n{content}\n```"
        except requests.RequestException as e:
            return f"Error downloading {file}: {e}"
    else:
        meta_url = f"{base_url}/{identifier}_meta.xml"
        try:
            resp = requests.get(meta_url, timeout=30)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            files_elem = root.find('files')
            if files_elem is None:
                return "No files found in metadata."
            output = f"**Available files for `{identifier}`:**\n"
            for file_elem in files_elem.findall('file'):
                fname = file_elem.get('name')
                size = file_elem.get('size')
                format_type = file_elem.get('format')
                output += f"- `{fname}` ({size or 'unknown size'}, {format_type or 'unknown format'})\n"
            return output
        except Exception as e:
            return f"Error listing files: {e}"


def get_tools() -> List["ToolEntry"]:
    return [
        ToolEntry("archive_search", {
            "name": "archive_search",
            "description": "Search Archive.org items by query with optional media type filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (required)"},
                    "media_type": {"type": "string", "description": "Filter by media type (texts, movies, images, audio, software, web, collection, or * for all)"},
                    "fields": {"type": "string", "description": "Comma-separated fields to return"},
                    "rows": {"type": "integer", "description": "Number of results per page (max 100)"},
                    "page": {"type": "integer", "description": "Page number (1-indexed)"},
                },
                "required": ["query"],
            },
        }, _archive_search),
        ToolEntry("archive_wayback", {
            "name": "archive_wayback",
            "description": "Fetch an archived version of a webpage from the Wayback Machine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Original URL to archive (required)"},
                    "timestamp": {"type": "string", "description": "Optional archive timestamp in YYYYMMDDHHMMSS format"},
                },
                "required": ["url"],
            },
        }, _archive_wayback),
        ToolEntry("archive_download", {
            "name": "archive_download",
            "description": "Download a specific file from an Archive.org item or list available files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string", "description": "Archive item identifier (required)"},
                    "file": {"type": "string", "description": "Optional specific file name. If omitted, lists available files."},
                },
                "required": ["identifier"],
            },
        }, _archive_download),
    ]
