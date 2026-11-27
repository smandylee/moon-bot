"""스팀: 친구 게임 감시, 스팀아이디, 스팀가격."""
import discord
from discord.ext import commands
import os
import re
import asyncio
import difflib
import aiohttp
from urllib.parse import urlparse

from moonbot.ai import ai_generate, gemini_model
from moonbot.net import http_session


# =============================================================================
# 스팀 설정
# =============================================================================
STEAM_API_KEY = os.getenv('STEAM_API_KEY', 'your_steam_api_key_here')
STEAM_ALERT_CHANNEL_ID = int(os.getenv('STEAM_ALERT_CHANNEL_ID', '0') or 0)
STEAM_POLL_INTERVAL_SECONDS = max(15, int(os.getenv('STEAM_POLL_INTERVAL_SECONDS', '300') or 300))
STEAM_WATCH_STEAM_IDS = [
    steam_id.strip()
    for steam_id in os.getenv('STEAM_WATCH_STEAM_IDS', '').split(',')
    if steam_id.strip()
]

steam_previous_game_state = {}
steam_watch_initialized = False


def _steam_api_key_ok() -> bool:
    return STEAM_API_KEY and STEAM_API_KEY != 'your_steam_api_key_here'


def _steam_monitor_enabled() -> bool:
    return _steam_api_key_ok() and STEAM_ALERT_CHANNEL_ID > 0 and bool(STEAM_WATCH_STEAM_IDS)


async def _fetch_steam_player_summaries(session):
    """Steam Web API에서 감시 대상 유저 요약 정보를 가져온다."""
    url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
    params = {
        "key": STEAM_API_KEY,
        "steamids": ",".join(STEAM_WATCH_STEAM_IDS),
    }
    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
        if response.status != 200:
            raise RuntimeError(f"Steam API 응답 오류: HTTP {response.status}")
        payload = await response.json(content_type=None)
        return payload.get("response", {}).get("players", [])


def _extract_steam_vanity_or_id(profile_input: str):
    text = profile_input.strip()
    if text.isdigit() and len(text) == 17:
        return text, None

    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "profiles" and parts[1].isdigit():
            return parts[1], None
        if len(parts) >= 2 and parts[0] == "id":
            return None, parts[1]

    return None, text


async def steam_game_watch_loop(bot: commands.Bot):
    """Steam 게임 실행 감시 루프 (시작/게임 변경 시 디스코드 알림)."""
    global steam_watch_initialized, steam_previous_game_state

    await bot.wait_until_ready()

    if not _steam_monitor_enabled():
        print("ℹ️ Steam 감시 비활성화: STEAM_API_KEY / STEAM_ALERT_CHANNEL_ID / STEAM_WATCH_STEAM_IDS 확인 필요")
        return

    print(f"🎮 Steam 감시 시작: {len(STEAM_WATCH_STEAM_IDS)}명, {STEAM_POLL_INTERVAL_SECONDS}초 주기")

    while not bot.is_closed():
        try:
            channel = bot.get_channel(STEAM_ALERT_CHANNEL_ID)
            if channel is None:
                channel = await bot.fetch_channel(STEAM_ALERT_CHANNEL_ID)

            async with http_session() as session:
                players = await _fetch_steam_player_summaries(session)

            latest_state = {}
            for player in players:
                steam_id = str(player.get("steamid", ""))
                if not steam_id:
                    continue
                latest_state[steam_id] = player.get("gameid")

            # 첫 순회에서는 기준 상태만 저장하고 알림은 보내지 않는다.
            if not steam_watch_initialized:
                steam_previous_game_state = latest_state
                steam_watch_initialized = True
                await asyncio.sleep(STEAM_POLL_INTERVAL_SECONDS)
                continue

            for player in players:
                steam_id = str(player.get("steamid", ""))
                if not steam_id:
                    continue

                previous_game_id = steam_previous_game_state.get(steam_id)
                current_game_id = player.get("gameid")
                current_game_name = player.get("gameextrainfo", "알 수 없는 게임")

                # "게임을 켰을 때"만 알림: 미실행->실행 또는 게임 변경
                if current_game_id and current_game_id != previous_game_id:
                    persona_name = player.get("personaname", steam_id)
                    profile_url = f"https://steamcommunity.com/profiles/{steam_id}"
                    await channel.send(
                        f"🎮 **{persona_name}** 님이 **{current_game_name}** 실행함\n{profile_url}"
                    )

            steam_previous_game_state = latest_state

        except Exception as steam_error:
            print(f"❌ Steam 감시 오류: {steam_error}")

        await asyncio.sleep(STEAM_POLL_INTERVAL_SECONDS)


# -----------------------------------------------------------------------------
# Steam 상점 가격 조회
# 공식 Web API에는 가격이 없어서 상점 프론트엔드 API를 쓴다. 비공식이라
# 응답이 바뀔 수 있으므로 값은 전부 있는지 확인하고 꺼낸다.
# -----------------------------------------------------------------------------
STEAM_STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
STEAM_STORE_DETAIL_URL = "https://store.steampowered.com/api/appdetails"
STEAM_STORE_COUNTRY = os.getenv('STEAM_STORE_COUNTRY', 'kr')
STEAM_STORE_LANGUAGE = os.getenv('STEAM_STORE_LANGUAGE', 'koreana')


def _extract_steam_appid(text: str):
    """입력에서 앱ID를 뽑는다. 숫자이거나 상점 URL이면 앱ID, 아니면 None."""
    value = text.strip()
    if value.isdigit():
        return value

    if value.startswith("http://") or value.startswith("https://"):
        parts = [part for part in urlparse(value).path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "app" and parts[1].isdigit():
            return parts[1]

    return None


# 한국 게이머들이 쓰는 줄임말 -> 스팀 검색어 (스팀 검색은 줄임말을 거의 못 알아듣는다)
STEAM_GAME_ALIASES = {
    "사펑": "Cyberpunk 2077",
    "사이버펑크": "Cyberpunk 2077",
    "발더스": "Baldur's Gate 3",
    "발더스게이트": "Baldur's Gate 3",
    "발게3": "Baldur's Gate 3",
    "헬다": "Helldivers 2",
    "헬다2": "Helldivers 2",
    "헬다이버즈": "Helldivers 2",
    "배그": "PUBG: BATTLEGROUNDS",
    "배틀그라운드": "PUBG: BATTLEGROUNDS",
    "옵치": "Overwatch 2",
    "오버워치": "Overwatch 2",
    "엘든링": "ELDEN RING",
    "엘든": "ELDEN RING",
    "몬헌": "Monster Hunter Wilds",
    "몬헌와일즈": "Monster Hunter Wilds",
    "몬헌월드": "Monster Hunter World",
    "테라리아": "Terraria",
    "스타듀": "Stardew Valley",
    "스듀": "Stardew Valley",
    "팰월드": "Palworld",
    "데바데": "Dead by Daylight",
    "카스": "Counter-Strike 2",
    "옛카스": "Counter-Strike: Source",
    "도타": "Dota 2",
    "위쳐": "더 위쳐 3: 와일드 헌트",
    "위쳐3": "더 위쳐 3: 와일드 헌트",
    "다크소울": "DARK SOULS III",
    "다소3": "DARK SOULS III",
    "세키로": "Sekiro: Shadows Die Twice",
    "아머드코어": "ARMORED CORE VI",
    "갓오브워": "God of War",
    "라오어": "The Last of Us Part I",
    "레데리": "Red Dead Redemption 2",
    "레데리2": "Red Dead Redemption 2",
    "gta": "Grand Theft Auto V",
    "지티에이": "Grand Theft Auto V",
    "러스트": "Rust",
    "아크": "ARK: Survival Evolved",
    "워쉽": "World of Warships",
    "월탱": "World of Tanks Blitz",
    "워썬더": "War Thunder",
    "시티즈": "Cities: Skylines II",
    "심즈": "The Sims 4",
    "문명": "Sid Meier's Civilization VI",
    "문명6": "Sid Meier's Civilization VI",
    "할로우나이트": "Hollow Knight",
    "언더테일": "Undertale",
    "에펙": "Apex Legends",
    "에이펙스": "Apex Legends",
    "피파": "EA SPORTS FC 25",
    "포이": "Path of Exile 2",
    "패스오브엑자일": "Path of Exile 2",
    "보더랜드": "Borderlands 4",
    "리썰컴퍼니": "Lethal Company",
    "리썰": "Lethal Company",
    "구스구스덕": "Goose Goose Duck",
    "발헤임": "Valheim",
    "노맨즈스카이": "No Man's Sky",
    "스타필드": "Starfield",
    "호라이즌": "Horizon Zero Dawn",
    "데스스트랜딩": "DEATH STRANDING",
    "니어": "NieR:Automata",
    "P의거짓": "Lies of P",
    "피의거짓": "Lies of P",
}

# 본편 대신 잡히기 쉬운 부가 상품 표시어 (점수를 깎는다)
_STEAM_ADDON_HINTS = (
    "soundtrack", "사운드트랙", "ost", "dlc", "pack", "팩", "세트", "스킨", "skin",
    "bundle", "번들", "demo", "데모", "toolkit", "redkit", "sdk", "artbook", "아트북",
    "wallpaper", "beta", "server", "editor", "upgrade", "업그레이드", "코스튬",
    "battle pass", "배틀 패스", "묶음", "스타터", "starter", "cosmetics", "코스메틱",
)


def _normalize_steam_term(text: str) -> str:
    """비교용으로 공백/기호/상표기호를 떼고 소문자로 만든다."""
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


# 조회는 정규화된 키로 한다 (대소문자/공백이 섞인 키도 걸리도록)
_STEAM_ALIAS_LOOKUP = {
    _normalize_steam_term(alias): title
    for alias, title in STEAM_GAME_ALIASES.items()
}


def _steam_match_score(term: str, name: str, position: int = 0) -> float:
    """검색어와 상점 이름의 유사도 점수. 높을수록 잘 맞는 결과.

    position은 스팀이 매긴 관련도 순서로, 앞쪽일수록 가산점을 준다.
    """
    normalized_term = _normalize_steam_term(term)
    normalized_name = _normalize_steam_term(name)
    if not normalized_term or not normalized_name:
        return 0.0

    score = difflib.SequenceMatcher(None, normalized_term, normalized_name).ratio()

    # 검색어로 시작하면 본편일 확률이 높다
    if normalized_name.startswith(normalized_term):
        score += 0.35
    elif normalized_term in normalized_name:
        score += 0.2

    lowered_name = (name or "").lower()
    if any(hint in lowered_name for hint in _STEAM_ADDON_HINTS):
        score -= 0.3

    # 스팀 자체 관련도 순서도 꽤 정확해서 상위 결과에 약간 힘을 실어준다
    score += (0.15, 0.1, 0.05)[position] if position < 3 else 0

    return score


def _steam_search_variants(query: str):
    """검색에 시도해볼 후보 검색어들을 순서대로 만든다."""
    variants = []

    alias = _STEAM_ALIAS_LOOKUP.get(_normalize_steam_term(query))
    if alias:
        variants.append(alias)

    variants.append(query)

    compact = query.replace(" ", "")
    variants.append(compact)

    # "위쳐3" 처럼 붙은 숫자를 띄어준다
    variants.append(re.sub(r"([^\d\s])(\d)", r"\1 \2", query))

    # 중복 제거 (순서 유지)
    seen = set()
    unique_variants = []
    for variant in variants:
        cleaned = (variant or "").strip()
        if cleaned and cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            unique_variants.append(cleaned)
    return unique_variants


async def _guess_steam_title_with_ai(query: str):
    """별칭/검색으로 못 찾으면 AI에게 정식 제목을 물어본다."""
    if gemini_model is None:
        return None

    prompt = f"""'{query}'는 한국 게이머들이 쓰는 게임 줄임말이거나 오타일 수 있어.
어떤 게임인지 추측해서 Steam 상점에 등록된 정식 제목만 한 줄로 알려줘.

규칙:
- 영문 원제를 우선해
- 제목만 출력하고 설명, 따옴표, 다른 말은 절대 붙이지 마
- 무슨 게임인지 모르겠으면 "없음"이라고만 답해"""

    try:
        response = await ai_generate(gemini_model, prompt)
        title = (response.text or "").strip().splitlines()[0].strip().strip('"').strip("'")
    except Exception as ai_error:
        print(f"스팀 제목 AI 추측 실패: {ai_error}")
        return None

    if not title or title == "없음" or len(title) > 60:
        return None
    return title


async def _search_steam_items(session, term: str):
    """상점 검색 결과 목록을 반환."""
    params = {"term": term, "cc": STEAM_STORE_COUNTRY, "l": STEAM_STORE_LANGUAGE}
    try:
        async with session.get(
            STEAM_STORE_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
        ) as response:
            if response.status != 200:
                return []
            payload = await response.json(content_type=None)
    except Exception as search_error:
        print(f"스팀 상점 검색 실패 ({term}): {search_error}")
        return []

    return (payload or {}).get("items") or []


async def _resolve_steam_game(session, query: str):
    """별칭 -> 원문 -> 변형 -> AI 순서로 게임을 찾는다.

    검색 결과 상위 후보의 상세 정보를 확인해서 DLC/사운드트랙 대신 본편을 고른다.
    찾으면 {'appid', 'name', 'data', 'term', 'others'} 를, 못 찾으면 None을 반환.
    """
    detail_cache = {}

    async def _details(appid: str):
        if appid not in detail_cache:
            detail_cache[appid] = await _fetch_steam_app_details(session, appid)
        return detail_cache[appid]

    async def _pick(term, items):
        ranked = sorted(
            enumerate(items),
            key=lambda pair: _steam_match_score(term, pair[1].get("name", ""), pair[0]),
            reverse=True,
        )
        ranked = [item for _, item in ranked]

        # 상위 후보 중 '본편(type=game)'을 우선한다. DLC/사운드트랙이 먼저 잡히는 걸 막는다.
        chosen = None
        for item in ranked[:3]:
            data = await _details(str(item.get("id")))
            if data and data.get("type") == "game":
                chosen = (item, data)
                break

        if chosen is None:
            # 본편이 없으면 점수가 가장 높은 후보라도 쓴다
            top = ranked[0]
            data = await _details(str(top.get("id")))
            if not data:
                return None
            chosen = (top, data)

        item, data = chosen
        return {
            "appid": str(item.get("id")),
            "name": data.get("name") or item.get("name"),
            "data": data,
            "term": term,
            "others": [
                other.get("name") for other in ranked
                if other.get("id") != item.get("id") and other.get("name")
            ][:3],
        }

    for term in _steam_search_variants(query):
        items = await _search_steam_items(session, term)
        if items:
            picked = await _pick(term, items)
            if picked:
                return picked

    guessed_title = await _guess_steam_title_with_ai(query)
    if guessed_title:
        items = await _search_steam_items(session, guessed_title)
        if items:
            return await _pick(guessed_title, items)

    return None


async def _fetch_steam_app_details(session, appid: str):
    """appdetails로 앱 상세 정보를 가져온다. 실패하면 None."""
    params = {"appids": appid, "cc": STEAM_STORE_COUNTRY, "l": STEAM_STORE_LANGUAGE}
    async with session.get(
        STEAM_STORE_DETAIL_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)
    ) as response:
        if response.status != 200:
            return None
        payload = await response.json(content_type=None)

    entry = (payload or {}).get(str(appid)) or {}
    if not entry.get("success"):
        return None
    return entry.get("data")


def _format_steam_price(data: dict):
    """(가격 텍스트 줄 목록, 할인율) 반환."""
    release = data.get("release_date") or {}
    price = data.get("price_overview") or {}

    if data.get("is_free"):
        return ["가격: 무료"], 0

    if not price:
        if release.get("coming_soon"):
            return [f"가격: 미정 (출시 예정 {release.get('date') or '날짜 미정'})"], 0
        return ["가격: 정보 없음 (지역 미판매이거나 상점에서 내려간 게임)"], 0

    discount = int(price.get("discount_percent", 0) or 0)
    lines = [f"현재가: {price.get('final_formatted') or '?'}"]

    if discount > 0:
        # 할인 중일 때만 initial_formatted가 채워져서 온다
        currency = price.get("currency") or ""
        unit = "원" if currency == "KRW" else f" {currency}"
        saved = ((price.get("initial") or 0) - (price.get("final") or 0)) / 100
        lines.append(f"정가: {price.get('initial_formatted') or '?'}")
        lines.append(f"할인: -{discount}% ({saved:,.0f}{unit} 절약)")

    return lines, discount


class Steam(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.watch_task = None

    async def cog_load(self):
        self.watch_task = asyncio.create_task(steam_game_watch_loop(self.bot))

    async def cog_unload(self):
        if self.watch_task is not None:
            self.watch_task.cancel()

    @commands.command(name='스팀아이디')
    async def steam_id_lookup(self, ctx, *, profile_input: str = None):
        """Steam 프로필 URL/바니티ID/SteamID64를 받아 SteamID64를 알려주는 명령어"""
        if not profile_input:
            await ctx.send(
                "❌ 사용법: `.스팀아이디 [프로필URL|바니티ID|SteamID64]`\n"
                "예시: `.스팀아이디 https://steamcommunity.com/id/gaben/`"
            )
            return

        steam_id64, vanity = _extract_steam_vanity_or_id(profile_input)
        if steam_id64:
            await ctx.send(
                f"✅ SteamID64: `{steam_id64}`\n"
                f"프로필: https://steamcommunity.com/profiles/{steam_id64}"
            )
            return

        if not _steam_api_key_ok():
            await ctx.send(
                "❌ 바니티ID 변환에는 STEAM_API_KEY가 필요합니다.\n"
                "숫자형 프로필 URL(`.../profiles/7656...`)은 API 없이 바로 확인할 수 있어요."
            )
            return

        try:
            async with http_session() as session:
                resolve_url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v0001/"
                params = {"key": STEAM_API_KEY, "vanityurl": vanity}
                async with session.get(resolve_url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        await ctx.send(f"❌ Steam API 요청 실패 (HTTP {response.status})")
                        return
                    payload = await response.json(content_type=None)

            info = payload.get("response", {})
            if info.get("success") == 1 and info.get("steamid"):
                resolved_id = info["steamid"]
                await ctx.send(
                    f"✅ SteamID64: `{resolved_id}`\n"
                    f"프로필: https://steamcommunity.com/profiles/{resolved_id}"
                )
                return

            await ctx.send(
                "❌ 해당 입력으로 SteamID를 찾지 못했습니다.\n"
                "프로필 공개 상태인지, URL/아이디 오타가 없는지 확인해주세요."
            )
        except Exception as e:
            await ctx.send(f"❌ SteamID 조회 중 오류: {e}")

    @commands.command(name='스팀가격')
    async def steam_price(self, ctx, *, game_name: str = None):
        """Steam 상점에서 게임 가격/할인 정보를 조회하는 명령어"""
        if not game_name:
            await ctx.send(
                "❌ 사용법: `.스팀가격 [게임명|상점URL|앱ID]`\n"
                "예시: `.스팀가격 Helldivers 2` / `.스팀가격 553850`"
            )
            return

        loading_msg = await ctx.send(f"🔍 '{game_name}' 가격 조회 중...")

        try:
            async with http_session() as session:
                # URL이나 앱ID를 그대로 준 경우엔 검색을 건너뛴다
                appid = _extract_steam_appid(game_name)
                matched = None
                if not appid:
                    matched = await _resolve_steam_game(session, game_name)
                    if not matched:
                        await loading_msg.edit(
                            content=f"❌ '{game_name}' 게임을 상점에서 찾지 못했습니다.\n"
                                    f"💡 영문 원제로 검색하거나 상점 URL/앱ID를 넣어보세요."
                        )
                        return
                    appid = matched["appid"]

                # 검색 경로에선 이미 상세 정보를 받아왔으므로 다시 부르지 않는다
                data = matched["data"] if matched else await _fetch_steam_app_details(session, appid)

            if not data:
                await loading_msg.edit(content=f"❌ 상점 정보를 가져오지 못했습니다. (앱ID: {appid})")
                return

            price_lines, discount = _format_steam_price(data)

            # 할인 중이면 초록, 아니면 스팀 남색
            embed = discord.Embed(
                title=data.get("name") or game_name,
                url=f"https://store.steampowered.com/app/{appid}/",
                color=0x2ECC71 if discount > 0 else 0x1B2838
            )

            if data.get("header_image"):
                embed.set_image(url=data["header_image"])

            price_body = "\n".join(price_lines)
            embed.add_field(
                name="💰 가격" + (f" (🔥 -{discount}%)" if discount > 0 else ""),
                value=f"```\n{price_body}\n```",
                inline=False
            )

            # 입력과 다른 이름으로 찾았으면 무엇으로 찾았는지 알려준다
            notice = ""
            if matched and _normalize_steam_term(game_name) != _normalize_steam_term(matched["name"]):
                notice = f"🔎 `{game_name}` → **{matched['name']}** 으로 찾았어"

            if matched and matched["others"]:
                others = "\n".join([f"• {name}" for name in matched["others"]])
                embed.add_field(
                    name="🔀 이게 아니면 이 중에 있을지도",
                    value=others,
                    inline=False
                )

            embed.set_footer(text=f"App ID: {appid} | 기준 지역: {STEAM_STORE_COUNTRY.upper()}")
            await loading_msg.edit(content=notice, embed=embed)

        except asyncio.TimeoutError:
            await loading_msg.edit(content="❌ 상점 응답 시간 초과! 잠시 후 다시 시도해주세요.")
        except Exception as e:
            await loading_msg.edit(content=f"❌ 가격 조회 중 오류: {e}")
            print(f"스팀 가격 조회 오류: {e}")

    @commands.command(name='스팀감시상태')
    async def steam_watch_status(self, ctx):
        """Steam 감시 설정 상태를 출력한다."""
        watching_ids = ", ".join(STEAM_WATCH_STEAM_IDS) if STEAM_WATCH_STEAM_IDS else "없음"
        await ctx.send(
            "🎮 Steam 감시 설정 상태\n"
            f"- API 키 설정: {'예' if _steam_api_key_ok() else '아니오'}\n"
            f"- 알림 채널 ID: `{STEAM_ALERT_CHANNEL_ID}`\n"
            f"- 감시 대상 SteamID: {watching_ids}\n"
            f"- 폴링 주기: {STEAM_POLL_INTERVAL_SECONDS}초"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Steam(bot))
