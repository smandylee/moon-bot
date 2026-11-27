"""공용 HTTP 세션과 채널 병렬 스캔."""
import asyncio
import contextlib
import aiohttp


# =============================================================================
# 공용 HTTP 세션
# 명령어마다 ClientSession을 새로 만들면 커넥션 풀과 TLS 핸드셰이크를 매번
# 다시 하게 된다. 하나를 만들어 재사용한다.
# =============================================================================
_http_session = None


async def get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=50, ttl_dns_cache=300),
        )
    return _http_session


@contextlib.asynccontextmanager
async def http_session():
    """`async with` 형태를 유지하되 공용 세션을 빌려주고 닫지 않는다."""
    yield await get_http_session()


# =============================================================================
# 채널 히스토리 병렬 스캔
# 채널을 하나씩 순회하면 채널 수 x 페이지 수만큼 왕복이 직렬로 쌓인다.
# 동시 실행 수만 제한해서 병렬로 훑는다.
# =============================================================================
CHANNEL_SCAN_CONCURRENCY = 5


async def scan_channels(guild, me, scan_one):
    """읽기 권한이 있는 텍스트 채널을 병렬로 훑고 scan_one의 결과 목록을 반환."""
    semaphore = asyncio.Semaphore(CHANNEL_SCAN_CONCURRENCY)

    async def _guarded(channel):
        try:
            if not channel.permissions_for(me).read_message_history:
                return None
            async with semaphore:
                return await scan_one(channel)
        except Exception as scan_error:
            print(f"채널 스캔 실패 ({channel.name}): {scan_error}")
            return None

    results = await asyncio.gather(*[_guarded(ch) for ch in guild.text_channels])
    return [result for result in results if result is not None]


async def close_http_session():
    global _http_session
    if _http_session is not None and not _http_session.closed:
        await _http_session.close()
