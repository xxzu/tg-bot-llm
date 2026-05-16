"""
全局 aiohttp ClientSession，复用 TCP 连接以降低 API 延迟。
"""
import aiohttp

_session: aiohttp.ClientSession | None = None


async def get_http_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        timeout = aiohttp.ClientTimeout(total=90, connect=15)
        connector = aiohttp.TCPConnector(limit=30, ttl_dns_cache=300)
        _session = aiohttp.ClientSession(timeout=timeout, connector=connector)
    return _session


async def close_http_session() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()
    _session = None
