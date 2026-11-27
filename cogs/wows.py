"""월드 오브 워쉽 전적/함선/클랜 조회."""
import discord
from discord.ext import commands
import os
import datetime
import json
import asyncio
import time
import aiohttp

from moonbot.net import http_session


# PR Expected Values 로드
try:
    with open('pr.json', 'r', encoding='utf-8') as f:
        pr_data = json.load(f)
        PR_EXPECTED_VALUES = pr_data.get('data', {})
    print(f"✅ PR 기댓값 데이터 로드 완료: {len(PR_EXPECTED_VALUES)}개 함선")
except Exception as e:
    print(f"⚠️ PR 기댓값 데이터 로드 실패: {e}")
    PR_EXPECTED_VALUES = {}


WARGAMING_API_KEY = os.getenv('WARGAMING_API_KEY', 'your_wargaming_api_key_here')
WOWS_API_REGIONS = {
    'na': 'https://api.worldofwarships.com',
    'eu': 'https://api.worldofwarships.eu',
    'asia': 'https://api.worldofwarships.asia',
    'ru': 'https://api.worldofwarships.ru'
}
WOWS_API_BASE_URL = WOWS_API_REGIONS['na']  # 기본값: NA 서버

_WOWS_REGION_NAMES = {'na': 'NA (북미)', 'eu': 'EU (유럽)', 'asia': 'ASIA (아시아)', 'ru': 'RU (러시아)'}

# -----------------------------------------------------------------------------
# 함선 백과사전 캐시
# 함선 목록은 패치 때나 바뀌는 정적 데이터인데, 예전엔 명령어마다(그리고
# .워쉽함선정보는 호출마다 10페이지씩) 다시 받아왔다. 리전별로 한 번만 받아
# 캐시하고, 페이지는 병렬로 수집한다.
# -----------------------------------------------------------------------------
WOWS_SHIP_CACHE_TTL = 24 * 60 * 60  # 24시간

_wows_ship_cache = {}        # {region: {ship_id(int): {'name','tier','type','nation'}}}
_wows_ship_cache_time = {}   # {region: epoch}
_wows_ship_cache_locks = {}  # {region: asyncio.Lock}


def _wows_ship_cache_fresh(region_key: str) -> bool:
    return (
        region_key in _wows_ship_cache
        and time.time() - _wows_ship_cache_time.get(region_key, 0) < WOWS_SHIP_CACHE_TTL
    )


async def get_wows_ships(session, api_base_url: str, region_key: str = 'na') -> dict:
    """전체 함선 정보를 {ship_id: {name, tier, type, nation}} 형태로 반환 (캐시)."""
    if _wows_ship_cache_fresh(region_key):
        return _wows_ship_cache[region_key]

    lock = _wows_ship_cache_locks.setdefault(region_key, asyncio.Lock())
    async with lock:
        # 락을 기다리는 동안 다른 태스크가 이미 채웠을 수 있다
        if _wows_ship_cache_fresh(region_key):
            return _wows_ship_cache[region_key]

        url = f"{api_base_url}/wows/encyclopedia/ships/"
        base_params = {
            'application_id': WARGAMING_API_KEY,
            'fields': 'name,tier,type,nation',
            'limit': 100,
        }

        async def _fetch_page(page_no: int):
            try:
                params = dict(base_params, page_no=page_no)
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status != 200:
                        return None
                    payload = await resp.json()
                    if payload.get('status') != 'ok':
                        return None
                    return payload
            except Exception as page_error:
                print(f"함선 백과사전 {page_no}페이지 수집 실패: {page_error}")
                return None

        first = await _fetch_page(1)
        if not first:
            return _wows_ship_cache.get(region_key, {})

        ships = {}

        def _absorb(payload):
            for ship_id, info in (payload.get('data') or {}).items():
                if info:
                    ships[int(ship_id)] = info

        _absorb(first)

        page_total = (first.get('meta') or {}).get('page_total') or 1
        if page_total > 1:
            pages = await asyncio.gather(
                *[_fetch_page(page_no) for page_no in range(2, page_total + 1)]
            )
            for payload in pages:
                if payload:
                    _absorb(payload)

        if ships:
            _wows_ship_cache[region_key] = ships
            _wows_ship_cache_time[region_key] = time.time()
            print(f"🚢 함선 백과사전 캐시 갱신: {region_key} {len(ships)}척")
        return ships


def _wows_parse_args(region_arg: str, player_name_arg):
    """리전/플레이어명 인자를 파싱해서 (region_lower, api_base_url, region_display, player_name) 반환.
    첫 번째 인자가 리전이 아니면 player_name으로 간주하고 region은 'na'로 설정."""
    region_lower = region_arg.lower()
    if region_lower not in WOWS_API_REGIONS:
        player_name_arg = region_arg if player_name_arg is None else f"{region_arg} {player_name_arg}"
        region_lower = 'na'
    return (
        region_lower,
        WOWS_API_REGIONS[region_lower],
        _WOWS_REGION_NAMES.get(region_lower, region_lower.upper()),
        player_name_arg,
    )

def _wows_api_key_ok() -> bool:
    return WARGAMING_API_KEY != 'your_wargaming_api_key_here'

async def _wows_find_player(session, api_base_url: str, player_name: str):
    """Wargaming /account/list/ 로 플레이어를 검색해서 (account_id, nickname)를 반환.
    찾지 못하면 None 반환."""
    search_url = f"{api_base_url}/wows/account/list/"
    params = {'application_id': WARGAMING_API_KEY, 'search': player_name, 'type': 'startswith'}
    async with session.get(search_url, params=params) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        if data.get('status') != 'ok' or not data.get('data'):
            return None
        entry = data['data'][0]
        return entry['account_id'], entry['nickname']


# =============================================================================
# Personal Rating (WoWS Numbers 공식)
# =============================================================================
def _pr_from_ratios(r_dmg: float, r_frags: float, r_wins: float) -> int:
    n_dmg = max(0, (r_dmg - 0.4) / (1 - 0.4))
    n_frags = max(0, (r_frags - 0.1) / (1 - 0.1))
    n_wins = max(0, (r_wins - 0.7) / (1 - 0.7))
    return int(700 * n_dmg + 300 * n_frags + 150 * n_wins)


def _expected_for(ship_id):
    expected = PR_EXPECTED_VALUES.get(str(ship_id))
    return expected if isinstance(expected, dict) and expected else None


def calc_ship_pr(ship_id, avg_damage: float, avg_frags: float, win_rate_pct: float):
    """함선 하나의 PR. pr.json에 기댓값이 없으면 None."""
    expected = _expected_for(ship_id)
    if expected is None:
        return None
    exp_damage = expected.get('average_damage_dealt', 0)
    exp_frags = expected.get('average_frags', 0)
    exp_wins = expected.get('win_rate', 0) / 100
    return _pr_from_ratios(
        avg_damage / exp_damage if exp_damage > 0 else 0,
        avg_frags / exp_frags if exp_frags > 0 else 0,
        (win_rate_pct / 100) / exp_wins if exp_wins > 0 else 0,
    )


def calc_account_pr(player_ships: list):
    """ships/stats 결과로 계정 종합 PR을 계산. 계산할 수 없으면 None.

    실제값과 기댓값을 '기댓값이 있는 함선'만으로 똑같이 합산한다. 예전엔 실제값은
    계정 전체 합계를 써서, pr.json에 없는 신규 함선을 많이 탄 사람일수록 PR이 부풀었다.
    """
    actual = {'damage': 0, 'frags': 0, 'wins': 0}
    expected_sum = {'damage': 0.0, 'frags': 0.0, 'wins': 0.0}
    for ship in player_ships or []:
        pvp = ship.get('pvp') or {}
        ship_battles = pvp.get('battles', 0)
        expected = _expected_for(ship.get('ship_id'))
        if ship_battles == 0 or expected is None:
            continue
        actual['damage'] += pvp.get('damage_dealt', 0)
        actual['frags'] += pvp.get('frags', 0)
        actual['wins'] += pvp.get('wins', 0)
        expected_sum['damage'] += expected.get('average_damage_dealt', 0) * ship_battles
        expected_sum['frags'] += expected.get('average_frags', 0) * ship_battles
        expected_sum['wins'] += expected.get('win_rate', 0) / 100 * ship_battles

    if not all(value > 0 for value in expected_sum.values()):
        return None
    return _pr_from_ratios(
        actual['damage'] / expected_sum['damage'],
        actual['frags'] / expected_sum['frags'],
        actual['wins'] / expected_sum['wins'],
    )


class WoWS(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =============================================================================
    # WoWS 명령어
    # =============================================================================
    @commands.command(name='워쉽전적')
    async def wows_stats(self, ctx, region: str = 'na', *, player_name: str = None):
        """World of Warships 플레이어 전적을 검색하는 명령어
    
    사용법:
    .워쉽전적 플레이어명          (기본: NA 서버)
    .워쉽전적 na 플레이어명       (NA 서버)
    .워쉽전적 asia 플레이어명     (ASIA 서버)
    .워쉽전적 eu 플레이어명       (EU 서버)
    .워쉽전적 ru 플레이어명       (RU 서버)
    """
        try:
            region_lower, api_base_url, region_name, player_name = _wows_parse_args(region, player_name)

            if not player_name:
                await ctx.send("❌ 사용법: `.워쉽전적 [리전] 플레이어명`\n예시: `.워쉽전적 na Flamu` 또는 `.워쉽전적 Flamu`\n\n지원 리전: na, eu, asia, ru")
                return

            loading_msg = await ctx.send(f"🔍 '{player_name}' 플레이어 검색 중... ({region_name} 서버)")

            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!\n.env 파일에 WARGAMING_API_KEY를 추가해주세요.\nhttps://developers.wargaming.net/ 에서 발급받을 수 있습니다.")
                return

            async with http_session() as session:
                # 1단계: 플레이어 검색
                result = await _wows_find_player(session, api_base_url, player_name)
                if not result:
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.\n\n💡 팁:\n- 플레이어 이름을 정확히 입력했는지 확인하세요\n- 대소문자는 상관없습니다\n- 일부 이름만 입력해도 검색됩니다")
                    return
                account_id, found_nickname = result

                await loading_msg.edit(content=f"🔍 '{found_nickname}' 플레이어 정보 로딩 중...")
            
                # 2단계: 플레이어 통계 가져오기
                stats_url = f"{api_base_url}/wows/account/info/"
                stats_params = {
                    'application_id': WARGAMING_API_KEY,
                    'account_id': account_id
                }
            
                async with session.get(stats_url, params=stats_params) as response:
                    if response.status != 200:
                        await loading_msg.edit(content="❌ 통계 정보를 가져오는데 실패했습니다.")
                        return
                
                    stats_data = await response.json()
                
                    if stats_data['status'] != 'ok' or not stats_data['data']:
                        await loading_msg.edit(content="❌ 통계 정보를 찾을 수 없습니다.")
                        return
                
                    player_data = stats_data['data'][str(account_id)]
                
                    if not player_data:
                        await loading_msg.edit(content="❌ 플레이어 데이터를 불러올 수 없습니다.")
                        return
                
                    # 통계 추출
                    stats = player_data.get('statistics', {}).get('pvp', {})
                
                    if not stats:
                        await loading_msg.edit(content=f"❌ '{found_nickname}' 플레이어의 전투 기록이 없습니다.")
                        return
                
                    battles = stats.get('battles', 0)
                    wins = stats.get('wins', 0)
                    losses = stats.get('losses', 0)
                    draws = stats.get('draws', 0)
                    survived = stats.get('survived_battles', 0)
                    frags = stats.get('frags', 0)
                    damage = stats.get('damage_dealt', 0)
                    exp = stats.get('xp', 0)
                
                    # Hidden stats (Rating)
                    hidden_profile = player_data.get('hidden_profile', False)
                
                    # 승률 계산
                    win_rate = (wins / battles * 100) if battles > 0 else 0
                    survival_rate = (survived / battles * 100) if battles > 0 else 0
                    avg_damage = damage / battles if battles > 0 else 0
                    avg_frags = frags / battles if battles > 0 else 0
                    avg_exp = exp / battles if battles > 0 else 0
                
                    # 계정 생성일
                    created_at = datetime.datetime.fromtimestamp(player_data.get('created_at', 0))
                    last_battle = datetime.datetime.fromtimestamp(player_data.get('last_battle_time', 0))
                
                    # Personal Rating 계산 (WoWS Numbers 정확한 공식)
                    # 종합 PR은 함선별 통계를 합산해서 계산해야 함
                    personal_rating = None
                
                    try:
                        if battles > 0:
                            # 함선별 통계 가져오기
                            ships_url = f"{api_base_url}/wows/ships/stats/"
                            ships_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
                        
                            async with session.get(ships_url, params=ships_params) as ships_response:
                                ships_data = await ships_response.json()
                            
                                if ships_data.get('status') == 'ok' and ships_data.get('data'):
                                    player_ships = ships_data['data'].get(str(account_id), [])
                                
                                    if player_ships:
                                        personal_rating = calc_account_pr(player_ships)
                                    
                    except Exception as e:
                        print(f"종합 PR 계산 오류: {e}")
                        personal_rating = None
                
                    # PR 등급 판정
                    pr_rating = "알 수 없음"
                    pr_color = 0x808080
                    if personal_rating:
                        if personal_rating >= 2450:
                            pr_rating = "Super Unicum 🏆"
                            pr_color = 0x7B00B4
                        elif personal_rating >= 2100:
                            pr_rating = "Unicum 💎"
                            pr_color = 0xFF4500
                        elif personal_rating >= 1750:
                            pr_rating = "Great 🌟"
                            pr_color = 0xFF8C00
                        elif personal_rating >= 1550:
                            pr_rating = "Very Good ⭐"
                            pr_color = 0xFFD700
                        elif personal_rating >= 1350:
                            pr_rating = "Good ✓"
                            pr_color = 0x00FF00
                        elif personal_rating >= 1100:
                            pr_rating = "Above Average"
                            pr_color = 0x98FB98
                        elif personal_rating >= 750:
                            pr_rating = "Average"
                            pr_color = 0xFFFF00
                        else:
                            pr_rating = "Below Average"
                            pr_color = 0xFF0000
                
                    # 임베드 생성
                    embed = discord.Embed(
                        title=f"⚓ {found_nickname}의 전적",
                        description=f"World of Warships {region_name} 서버",
                        color=pr_color  # PR 등급에 따른 색상
                    )
                
                    # Personal Rating 표시
                    pr_display = f"{personal_rating:,}" if personal_rating else "계산 불가"
                
                    embed.add_field(
                        name="🏆 Personal Rating",
                        value=f"```\n"
                              f"PR: {pr_display}\n"
                              f"등급: {pr_rating}\n"
                              f"```",
                        inline=False
                    )
                
                    embed.add_field(
                        name="📊 전투 통계",
                        value=f"```\n"
                              f"총 전투: {battles:,}회\n"
                              f"승리: {wins:,}회 | 패배: {losses:,}회 | 무승부: {draws:,}회\n"
                              f"승률: {win_rate:.2f}%\n"
                              f"생존율: {survival_rate:.2f}%\n"
                              f"```",
                        inline=False
                    )
                
                    embed.add_field(
                        name="🎯 평균 성적 (전투당)",
                        value=f"```\n"
                              f"피해량: {avg_damage:,.0f}\n"
                              f"격침: {avg_frags:.2f}척\n"
                              f"경험치: {avg_exp:,.0f}\n"
                              f"```",
                        inline=False
                    )
                
                    embed.add_field(
                        name="🏆 누적 성적",
                        value=f"```\n"
                              f"총 격침: {frags:,}척\n"
                              f"총 피해량: {damage:,}\n"
                              f"총 경험치: {exp:,}\n"
                              f"```",
                        inline=False
                    )
                
                    embed.add_field(
                        name="📅 계정 정보",
                        value=f"```\n"
                              f"가입일: {created_at.strftime('%Y-%m-%d')}\n"
                              f"마지막 전투: {last_battle.strftime('%Y-%m-%d %H:%M')}\n"
                              f"```",
                        inline=False
                    )
                
                    embed.set_footer(text=f"Account ID: {account_id}")
                
                    # 특정 플레이어에 대한 특별 메시지
                    special_message = ""
                    if found_nickname.lower() == "cockamonster":
                        special_message = "\n\n**존나못하네** 🤣"
                
                    # 결과 전송
                    await loading_msg.edit(content=special_message, embed=embed)
                
        except Exception as e:
            await ctx.send(f"❌ 전적 검색 중 오류가 발생했습니다: {str(e)}")
            print(f"워쉽 전적 검색 오류: {e}")

    @commands.command(name='워쉽액터')
    async def wows_actor_stats(self, ctx, region: str = 'na', *, player_name: str = None):
        """플레이어의 판수(전투 수) 통계를 검색하는 명령어"""
        try:
            region_lower, api_base_url, region_name, player_name = _wows_parse_args(region, player_name)

            if not player_name:
                await ctx.send("❌ 사용법: `.워쉽액터 [리전] 플레이어명`")
                return

            loading_msg = await ctx.send(f"🔍 '{player_name}'의 판수 통계 검색 중... ({region_name} 서버)")

            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return

            async with http_session() as session:
                result = await _wows_find_player(session, api_base_url, player_name)
                if not result:
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                account_id, found_nickname = result
                
                # 플레이어 전적 가져오기
                stats_url = f"{api_base_url}/wows/account/info/"
                stats_params = {
                    'application_id': WARGAMING_API_KEY,
                    'account_id': account_id
                }
                
                async with session.get(stats_url, params=stats_params) as stats_response:
                    stats_data = await stats_response.json()
                    if stats_data.get('status') != 'ok' or not stats_data.get('data'):
                        await loading_msg.edit(content="❌ 전적 정보를 가져올 수 없습니다.")
                        return
                    
                    player_data = stats_data['data'][str(account_id)]
                    pvp_stats = player_data.get('statistics', {}).get('pvp', {})
                    
                    battles = pvp_stats.get('battles', 0)
                    
                    # Embed 생성
                    embed = discord.Embed(
                        title=f"📊 {found_nickname}의 판수 통계",
                        description=f"**{region_name} 서버**",
                        color=0x3498DB
                    )
                    
                    # 총 판수
                    embed.add_field(
                        name="🎯 액터 고용한 판수",
                        value=f"```\n{battles:,}전```",
                        inline=False
                    )
                    
                    embed.set_footer(text=f"Account ID: {account_id}")
                    await loading_msg.edit(content="", embed=embed)
        
        except Exception as e:
            await ctx.send(f"❌ 액터 통계 검색 중 오류: {str(e)}")
            print(f"워쉽 액터 통계 오류: {e}")

    @commands.command(name='워쉽함선')
    async def wows_ship_stats(self, ctx, region: str = 'na', *, player_name: str = None):
        """World of Warships 플레이어의 함선별 전적을 검색하는 명령어
    
    사용법:
    .워쉽함선 플레이어명          (기본: NA 서버, 상위 10개 함선)
    .워쉽함선 na 플레이어명       (NA 서버)
    .워쉽함선 asia 플레이어명     (ASIA 서버)
    """
        try:
            region_lower, api_base_url, region_name, player_name = _wows_parse_args(region, player_name)

            if not player_name:
                await ctx.send("❌ 사용법: `.워쉽함선 [리전] 플레이어명`\n예시: `.워쉽함선 Flamu`")
                return

            loading_msg = await ctx.send(f"🔍 '{player_name}' 플레이어의 함선 전적 검색 중... ({region_name} 서버)")

            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return

            async with http_session() as session:
                # 1단계: 플레이어 검색
                result = await _wows_find_player(session, api_base_url, player_name)
                if not result:
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                account_id, found_nickname = result

                await loading_msg.edit(content=f"🔍 '{found_nickname}'의 함선 데이터 로딩 중...")
            
                # 2단계: 함선별 통계 가져오기
                ships_url = f"{api_base_url}/wows/ships/stats/"
                ships_params = {
                    'application_id': WARGAMING_API_KEY,
                    'account_id': account_id
                }
            
                try:
                    async with session.get(ships_url, params=ships_params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status != 200:
                            await loading_msg.edit(content=f"❌ 함선 정보를 가져오는데 실패했습니다. (상태: {response.status})")
                            return
                    
                        ships_data = await response.json()
                    
                        if ships_data.get('status') != 'ok':
                            error_msg = ships_data.get('error', {}).get('message', '알 수 없는 오류')
                            await loading_msg.edit(content=f"❌ API 오류: {error_msg}")
                            return
                    
                        if not ships_data.get('data'):
                            await loading_msg.edit(content="❌ 함선 전적 데이터가 없습니다.")
                            return
                    
                        player_ships = ships_data['data'].get(str(account_id))
                    
                        if not player_ships:
                            await loading_msg.edit(content=f"❌ '{found_nickname}' 플레이어의 함선 전적이 없습니다.")
                            return
                    
                        print(f"✅ {len(player_ships)}개 함선 데이터 로드 완료")
                    
                except asyncio.TimeoutError:
                    await loading_msg.edit(content="❌ 요청 시간 초과! API 응답이 너무 느립니다. 잠시 후 다시 시도해주세요.")
                    return
                except Exception as e:
                    await loading_msg.edit(content=f"❌ 함선 데이터 로드 실패: {str(e)}")
                    print(f"함선 데이터 로드 오류: {e}")
                    return
            
                # 3단계: 함선 정보 가져오기 (함선 이름)
                ship_names = {}
                ship_details = {}
            
                await loading_msg.edit(content=f"🔍 '{found_nickname}'의 함선 이름 로딩 중...")
            
                # 전투 수 기준으로 정렬 (상위 10개만 이름이 필요하다)
                player_ships.sort(key=lambda x: x.get('pvp', {}).get('battles', 0), reverse=True)
            
                if player_ships:
                    # 캐시된 백과사전에서 조회 (예전엔 명령어마다 다시 받아왔다)
                    all_ships = await get_wows_ships(session, api_base_url, region_lower)
                    for ship in player_ships[:10]:
                        ship_id_int = int(ship['ship_id'])
                        ship_info = all_ships.get(ship_id_int)
                        if not ship_info:
                            continue
                        ship_names[ship_id_int] = ship_info.get('name', f'함선 ID {ship_id_int}')
                        ship_details[ship_id_int] = {
                            'tier': ship_info.get('tier', 0),
                            'type': ship_info.get('type', 'Unknown'),
                            'nation': ship_info.get('nation', 'Unknown')
                        }
                    print(f"✅ {len(ship_names)}개 함선 이름 로드 완료")
            
                # 상위 10개 함선만 표시
                top_ships = player_ships[:10]
            
                # 임베드 생성
                embed = discord.Embed(
                    title=f"⚓ {found_nickname}의 함선별 전적",
                    description=f"World of Warships {region_name} 서버 (상위 10개 함선)",
                    color=0x3498DB
                )
            
                for ship in top_ships:
                    ship_id = ship['ship_id']
                    ship_name = ship_names.get(ship_id, f"알 수 없는 함선 (ID: {ship_id})")
                    details = ship_details.get(ship_id, {'tier': 0, 'type': 'Unknown', 'nation': 'Unknown'})
                    pvp_stats = ship.get('pvp', {})
                
                    battles = pvp_stats.get('battles', 0)
                    if battles == 0:
                        continue
                
                    wins = pvp_stats.get('wins', 0)
                    damage = pvp_stats.get('damage_dealt', 0)
                    frags = pvp_stats.get('frags', 0)
                    survived = pvp_stats.get('survived_battles', 0)
                
                    win_rate = (wins / battles * 100) if battles > 0 else 0
                    avg_damage = damage / battles if battles > 0 else 0
                    avg_frags = frags / battles if battles > 0 else 0
                    survival_rate = (survived / battles * 100) if battles > 0 else 0
                
                    # 함선별 PR (pr.json에 기댓값이 없으면 대략적인 점수로 대신)
                    ship_pr = 0
                    if battles > 0:
                        ship_pr = calc_ship_pr(ship_id, avg_damage, avg_frags, win_rate)
                        if ship_pr is None:
                            ship_pr = int((avg_damage/1000)*0.4*100 + win_rate*0.3 + avg_frags*20 + survival_rate*0.1)
                
                    # 함선 타입 이모지
                    type_emoji = {
                        'Destroyer': '🔰',
                        'Cruiser': '⚓',
                        'Battleship': '🛡️',
                        'AirCarrier': '✈️',
                        'Submarine': '🔱'
                    }.get(details.get('type', ''), '🚢')
                
                    # 티어 표시 (로마 숫자)
                    tier_roman = ['', 'Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ', 'Ⅵ', 'Ⅶ', 'Ⅷ', 'Ⅸ', 'Ⅹ', 'ⅩⅠ']
                    tier = details.get('tier', 0)
                    tier_str = tier_roman[tier] if 0 < tier < len(tier_roman) else f"T{tier}"
                
                    ship_info = (
                        f"```\n"
                        f"PR: {ship_pr:,}\n"
                        f"전투: {battles:,}회 | 승률: {win_rate:.1f}%\n"
                        f"평균 피해: {avg_damage:,.0f}\n"
                        f"평균 격침: {avg_frags:.2f} | 생존율: {survival_rate:.1f}%\n"
                        f"```"
                    )
                
                    embed.add_field(
                        name=f"{type_emoji} {tier_str} {ship_name}",
                        value=ship_info,
                        inline=False
                    )
            
                embed.set_footer(text=f"Account ID: {account_id} | 전체 함선 중 상위 10개 표시")
            
                # 특정 플레이어에 대한 특별 메시지
                special_message = ""
                if found_nickname.lower() == "cockamonster":
                    special_message = "\n\n**존나못하네** 🤣"
            
                await loading_msg.edit(content=special_message, embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ 함선 전적 검색 중 오류가 발생했습니다: {str(e)}")
            print(f"워쉽 함선 전적 검색 오류: {e}")

    @commands.command(name='워쉽클랜')
    async def wows_clan(self, ctx, region: str = 'na', *, clan_tag: str = None):
        """클랜 정보를 검색하는 명령어"""
        try:
            region_lower, api_base_url, region_name, clan_tag = _wows_parse_args(region, clan_tag)

            if not clan_tag:
                await ctx.send("❌ 사용법: `.워쉽클랜 [리전] [클랜태그]`\n예시: `.워쉽클랜 na CLAN`")
                return

            loading_msg = await ctx.send(f"🔍 클랜 '{clan_tag}' 검색 중... ({region_name} 서버)")

            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return
        
            async with http_session() as session:
                clan_url = f"{api_base_url}/wows/clans/list/"
                clan_params = {
                    'application_id': WARGAMING_API_KEY,
                    'search': clan_tag
                }
            
                async with session.get(clan_url, params=clan_params) as response:
                    if response.status != 200:
                        await loading_msg.edit(content="❌ API 요청 실패!")
                        return
                
                    clan_data = await response.json()
                    if clan_data.get('status') != 'ok' or not clan_data.get('data'):
                        await loading_msg.edit(content=f"❌ 클랜 '{clan_tag}'를 찾을 수 없습니다.")
                        return
                
                    clan_info = clan_data['data'][0]
                    clan_id = clan_info['clan_id']
                
                    # 클랜 상세 정보
                    clan_detail_url = f"{api_base_url}/wows/clans/info/"
                    clan_detail_params = {
                        'application_id': WARGAMING_API_KEY,
                        'clan_id': clan_id
                    }
                
                    async with session.get(clan_detail_url, params=clan_detail_params) as detail_response:
                        if detail_response.status != 200:
                            await loading_msg.edit(content="❌ 클랜 상세 정보를 가져오는데 실패했습니다.")
                            return
                    
                        detail_data = await detail_response.json()
                        if detail_data.get('status') != 'ok':
                            await loading_msg.edit(content="❌ 클랜 정보를 찾을 수 없습니다.")
                            return
                    
                        clan_detail = detail_data['data'][str(clan_id)]
                    
                        # 멤버 정보
                        members = clan_detail.get('members', [])
                        member_count = len(members)
                    
                        # 클랜 통계 계산
                        total_battles = 0
                        total_wins = 0
                        for member in members:
                            stats = member.get('statistics', {}).get('pvp', {})
                            total_battles += stats.get('battles', 0)
                            total_wins += stats.get('wins', 0)
                    
                        avg_battles = total_battles / member_count if member_count > 0 else 0
                        avg_win_rate = (total_wins / total_battles * 100) if total_battles > 0 else 0
                    
                        # 임베드 생성
                        embed = discord.Embed(
                            title=f"🏛️ {clan_detail.get('name', 'Unknown')}",
                            description=f"**{region_name} 서버** • 태그: `{clan_detail.get('tag', 'N/A')}`",
                            color=0x3498DB
                        )
                    
                        embed.add_field(
                            name="📊 클랜 정보",
                            value=f"```\n"
                                  f"멤버 수: {member_count}명\n"
                                  f"평균 전투: {avg_battles:,.0f}회\n"
                                  f"평균 승률: {avg_win_rate:.2f}%\n"
                                  f"```",
                            inline=False
                        )
                    
                        if clan_detail.get('description'):
                            desc = clan_detail['description'][:200] + "..." if len(clan_detail['description']) > 200 else clan_detail['description']
                            embed.add_field(
                                name="📝 설명",
                                value=desc,
                                inline=False
                            )
                    
                        # 멤버 목록 (상위 5명)
                        if members:
                            top_members = sorted(members, key=lambda x: x.get('statistics', {}).get('pvp', {}).get('battles', 0), reverse=True)[:5]
                            member_list = "\n".join([f"{i+1}. {m.get('account_name', 'Unknown')} ({m.get('statistics', {}).get('pvp', {}).get('battles', 0):,}전)" for i, m in enumerate(top_members)])
                            embed.add_field(
                                name="👥 상위 멤버 (전투 수 기준)",
                                value=f"```\n{member_list}\n```",
                                inline=False
                            )
                    
                        embed.set_footer(text=f"Clan ID: {clan_id}")
                        await loading_msg.edit(content="", embed=embed)
                    
        except Exception as e:
            await ctx.send(f"❌ 클랜 검색 중 오류: {str(e)}")
            print(f"워쉽 클랜 검색 오류: {e}")

    @commands.command(name='워쉽함선정보')
    async def wows_ship_info(self, ctx, *, ship_name: str):
        """함선 백과사전 정보를 검색하는 명령어"""
        try:
            # 대괄호가 포함된 검색어는 즉시 거부
            if '[' in ship_name or ']' in ship_name:
                await ctx.send("❌ 검색어에 대괄호 `[]`를 포함할 수 없습니다. 대괄호 없이 함선 이름만 입력하세요.\n예시: `.워쉽함선정보 Montana`")
                return
        
            if not _wows_api_key_ok():
                await ctx.send("❌ Wargaming API 키가 설정되지 않았습니다!")
                return
        
            loading_msg = await ctx.send(f"🔍 함선 '{ship_name}' 정보 검색 중...")
        
            async with http_session() as session:
                # 캐시된 백과사전에서 이름 검색 (예전엔 호출마다 10페이지를 순차로 받았다)
                found_ship_id = None
                try:
                    all_ships = await get_wows_ships(session, WOWS_API_REGIONS['na'], 'na')
                    if not all_ships:
                        await loading_msg.edit(content="❌ 함선 목록을 가져오지 못했습니다. 잠시 후 다시 시도해주세요.")
                        return

                    search_name_lower = ship_name.lower().strip()
                    exact_matches = []
                    partial_matches = []

                    for cached_ship_id, ship_data in all_ships.items():
                        ship_name_full = ship_data.get('name', '')
                        # 이름에 대괄호가 있는 항목(테스트/특수 함선)은 제외
                        if not ship_name_full or '[' in ship_name_full or ']' in ship_name_full:
                            continue

                        ship_name_lower = ship_name_full.lower()
                        if search_name_lower == ship_name_lower:
                            exact_matches.append((str(cached_ship_id), ship_name_full))
                        elif search_name_lower in ship_name_lower:
                            partial_matches.append((str(cached_ship_id), ship_name_full))

                    print(
                        f"검색어: '{ship_name}', 함선 {len(all_ships)}척 중 "
                        f"정확한 매칭: {len(exact_matches)}, 부분 매칭: {len(partial_matches)}"
                    )

                    if exact_matches:
                        found_ship_id = exact_matches[0][0]
                    elif partial_matches:
                        # 이름이 짧을수록 검색어에 가까운 함선일 확률이 높다
                        partial_matches.sort(key=lambda item: len(item[1]))
                        found_ship_id = partial_matches[0][0]
                except asyncio.TimeoutError:
                    await loading_msg.edit(content="❌ 함선 검색 시간 초과! API 응답이 너무 느립니다.")
                    return
                except Exception as e:
                    await loading_msg.edit(content=f"❌ 함선 검색 중 오류: {str(e)}")
                    print(f"함선 검색 오류: {e}")
                    return
            
                if not found_ship_id:
                    await loading_msg.edit(content=f"❌ 함선 '{ship_name}'를 찾을 수 없습니다.")
                    return
            
                # 함선 ID로 상세 정보 가져오기
                await loading_msg.edit(content=f"🔍 '{ship_name}' 상세 정보 로딩 중...")
            
                # 스펙 정보 포함하여 요청 (모든 필드 가져오기)
                detail_params = {
                    'application_id': WARGAMING_API_KEY,
                    'ship_id': found_ship_id
                    # fields 파라미터 없이 모든 필드 가져오기
                }
            
                try:
                    # 예전엔 ships_url이 정의되지 않아 항상 NameError가 났다
                    encyclopedia_url = f"{WOWS_API_REGIONS['na']}/wows/encyclopedia/ships/"
                    async with session.get(encyclopedia_url, params=detail_params, timeout=aiohttp.ClientTimeout(total=20)) as detail_response:
                        if detail_response.status != 200:
                            await loading_msg.edit(content=f"❌ 함선 상세 정보를 가져올 수 없습니다. (상태: {detail_response.status})")
                            return
                    
                        detail_data = await detail_response.json()
                        if detail_data.get('status') != 'ok':
                            error_msg = detail_data.get('error', {}).get('message', '알 수 없는 오류')
                            await loading_msg.edit(content=f"❌ API 오류: {error_msg}")
                            return
                    
                        ship_info = detail_data.get('data', {}).get(str(found_ship_id))
                        if not ship_info:
                            await loading_msg.edit(content=f"❌ 함선 정보를 찾을 수 없습니다.")
                            return
                    
                        ship_id = found_ship_id
                    
                        # 기본 정보
                        images = ship_info.get('images') or {}
                        default_profile = ship_info.get('default_profile') or {}
                        modules_tree = ship_info.get('modules_tree') or {}
                    
                        embed = discord.Embed(
                            title=f"🚢 {ship_info.get('name', 'Unknown')}",
                            description=f"**티어 {ship_info.get('tier', '?')}** • {ship_info.get('type', 'Unknown')} • {ship_info.get('nation', 'Unknown')}",
                            color=0x3498DB
                        )
                    
                        if images.get('small'):
                            embed.set_thumbnail(url=images['small'])
                    
                        # 기본 스펙 정보 추출
                        spec_info = f"```\n"
                        spec_found = False
                    
                        # 기본 스펙
                        hull = default_profile.get('hull') or {}
                        mobility = default_profile.get('mobility') or {}
                        artillery = default_profile.get('artillery') or {}
                        torpedoes = default_profile.get('torpedoes') or {}
                        concealment = default_profile.get('concealment') or {}
                    
                        # HP 정보
                        if hull.get('health'):
                            base_hp = hull['health']
                            spec_info += f"HP: {base_hp:,}\n"
                            spec_found = True
                    
                        # 속도 정보
                        if mobility.get('max_speed'):
                            base_speed = mobility['max_speed']
                            spec_info += f"최대 속도: {base_speed} knots\n"
                            spec_found = True
                    
                        # 포문 사거리
                        if artillery.get('distance'):
                            base_distance = artillery['distance']
                            spec_info += f"포문 사거리: {base_distance} km\n"
                            spec_found = True
                    
                        # AP/HE 포문 피해
                        shells = artillery.get('shells') or {}
                        ap_shell = shells.get('AP') or {}
                        he_shell = shells.get('HE') or {}
                    
                        if ap_shell.get('damage'):
                            ap_damage = ap_shell['damage']
                            spec_info += f"AP 포문 피해: {ap_damage}\n"
                            spec_found = True
                        if he_shell.get('damage'):
                            he_damage = he_shell['damage']
                            spec_info += f"HE 포문 피해: {he_damage}\n"
                            spec_found = True
                    
                        # 포문 발사 속도
                        if artillery.get('gun_rate'):
                            base_rate = artillery['gun_rate']
                            spec_info += f"포문 발사 속도: {base_rate} 발/분\n"
                            spec_found = True
                    
                        # 어뢰 정보
                        if torpedoes:
                            if torpedoes.get('max_damage'):
                                spec_info += f"어뢰 최대 피해: {torpedoes['max_damage']:,}\n"
                                spec_found = True
                            if torpedoes.get('distance'):
                                base_torp_distance = torpedoes['distance']
                                spec_info += f"어뢰 사거리: {base_torp_distance} km\n"
                                spec_found = True
                            if torpedoes.get('torpedo_speed'):
                                spec_info += f"어뢰 속도: {torpedoes['torpedo_speed']} knots\n"
                                spec_found = True
                    
                        # 회전 반경
                        if mobility.get('turning_radius'):
                            base_radius = mobility['turning_radius']
                            spec_info += f"회전 반경: {base_radius} m\n"
                            spec_found = True
                    
                        # 탐지 거리
                        if concealment.get('detect_distance_by_ship'):
                            base_detect = concealment['detect_distance_by_ship']
                            spec_info += f"탐지 거리: {base_detect} km\n"
                            spec_found = True
                    
                        if not spec_found:
                            spec_info += "상세 스펙 정보 없음\n"
                    
                        spec_info += f"```"
                    
                        embed.add_field(name="📊 함선 스펙", value=spec_info, inline=False)
                    
                        # 기본 정보
                        basic_info = f"```\n"
                        basic_info += f"티어: {ship_info.get('tier', '?')}\n"
                        basic_info += f"타입: {ship_info.get('type', 'Unknown')}\n"
                        basic_info += f"국가: {ship_info.get('nation', 'Unknown')}\n"
                        basic_info += f"```"
                    
                        embed.add_field(name="📋 기본 정보", value=basic_info, inline=False)
                    
                        # 함선 평균 통계 정보 (설명 자리에 표시)
                        avg_stats = f"```\n"
                        stats_found = False
                    
                        try:
                            # pr.json에서 함선의 기댓값 가져오기 (서버 평균과 유사)
                            expected = PR_EXPECTED_VALUES.get(str(found_ship_id))
                        
                            if expected and isinstance(expected, dict):
                                # 승률 (기댓값)
                                exp_win_rate = expected.get('win_rate', 0)
                                if exp_win_rate > 0:
                                    avg_stats += f"승률: {exp_win_rate:.2f}%\n"
                                    stats_found = True
                            
                                # 평균 격침 (기댓값)
                                exp_frags = expected.get('average_frags', 0)
                                if exp_frags > 0:
                                    avg_stats += f"평균 격침: {exp_frags:.2f}\n"
                                    stats_found = True
                            
                                # 평균 피해 (기댓값)
                                exp_damage = expected.get('average_damage_dealt', 0)
                                if exp_damage > 0:
                                    avg_stats += f"평균 피해: {exp_damage:,.0f}\n"
                                    stats_found = True
                            
                                # K/D 비율 추정
                                if exp_frags > 0:
                                    avg_stats += f"K/D 비율: {exp_frags:.2f}\n"
                                    stats_found = True
                        except Exception as e:
                            print(f"함선 평균 통계 가져오기 오류: {e}")
                    
                        if not stats_found:
                            avg_stats += "서버 평균 통계 정보 없음\n"
                    
                        avg_stats += f"```"
                        embed.add_field(name="📊 서버 평균 통계", value=avg_stats, inline=False)
                    
                        embed.set_footer(text=f"Ship ID: {ship_id}")
                        await loading_msg.edit(content="", embed=embed)
                except asyncio.TimeoutError:
                    await loading_msg.edit(content="❌ 함선 상세 정보 로딩 시간 초과!")
                except Exception as e:
                    await loading_msg.edit(content=f"❌ 함선 상세 정보 가져오기 중 오류: {str(e)}")
                    print(f"함선 상세 정보 오류: {e}")
                
        except Exception as e:
            await ctx.send(f"❌ 함선 정보 검색 중 오류: {str(e)}")
            print(f"워쉽 함선 정보 검색 오류: {e}")

    @commands.command(name='워쉽비교')
    async def wows_compare(self, ctx, region: str = 'na', *, players: str = None):
        """두 플레이어를 비교하는 명령어"""
        try:
            region_lower = region.lower()
            if region_lower not in WOWS_API_REGIONS:
                if players is None:
                    await ctx.send("❌ 사용법: `.워쉽비교 [리전] 플레이어1 플레이어2`\n예시: `.워쉽비교 Player1 Player2` 또는 `.워쉽비교 na Player1 Player2`")
                    return
                player_list = [region] + players.split()
                region_lower = 'na'
            else:
                if not players:
                    await ctx.send("❌ 사용법: `.워쉽비교 [리전] 플레이어1 플레이어2`\n예시: `.워쉽비교 Player1 Player2`")
                    return
                player_list = players.split()

            if len(player_list) < 2:
                await ctx.send("❌ 두 명의 플레이어 이름을 입력하세요!")
                return

            player1_name, player2_name = player_list[0], player_list[1]
            api_base_url = WOWS_API_REGIONS[region_lower]
            region_name = _WOWS_REGION_NAMES.get(region_lower, 'NA')

            loading_msg = await ctx.send(f"🔍 '{player1_name}' vs '{player2_name}' 비교 중...")
            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return

            async with http_session() as session:
                async def _collect_player(player_name):
                    """플레이어 한 명의 전적+PR을 모은다. (데이터, 오류메시지) 반환."""
                    result = await _wows_find_player(session, api_base_url, player_name)
                    if not result:
                        return None, f"❌ '{player_name}' 플레이어를 찾을 수 없습니다."
                    account_id, nickname = result

                    stats_url = f"{api_base_url}/wows/account/info/"
                    stats_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
                    async with session.get(stats_url, params=stats_params) as stats_response:
                        stats_data = await stats_response.json()
                    if stats_data.get('status') != 'ok' or not stats_data.get('data'):
                        return None, f"❌ '{nickname}' 전적 정보를 가져올 수 없습니다."

                    player_data = stats_data['data'][str(account_id)]
                    stats = player_data.get('statistics', {}).get('pvp', {})
                    battles = stats.get('battles', 0)
                    wins = stats.get('wins', 0)
                    damage = stats.get('damage_dealt', 0)
                    frags = stats.get('frags', 0)
                    win_rate = (wins / battles * 100) if battles > 0 else 0
                    avg_damage = damage / battles if battles > 0 else 0
                    avg_frags = frags / battles if battles > 0 else 0

                    pr = 0
                    if battles > 0:
                        try:
                            ships_url = f"{api_base_url}/wows/ships/stats/"
                            ships_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
                            async with session.get(ships_url, params=ships_params) as ships_response:
                                ships_data = await ships_response.json()

                            if ships_data.get('status') == 'ok' and ships_data.get('data'):
                                player_ships = ships_data['data'].get(str(account_id), [])
                                if player_ships:
                                    pr = calc_account_pr(player_ships) or 0
                        except Exception as e:
                            print(f"비교 PR 계산 오류 ({nickname}): {e}")
                            pr = 0

                    return {
                        'name': nickname,
                        'battles': battles,
                        'win_rate': win_rate,
                        'avg_damage': avg_damage,
                        'avg_frags': avg_frags,
                        'pr': pr
                    }, None

                # 두 플레이어는 서로 독립적이므로 동시에 조회한다
                collected = await asyncio.gather(
                    _collect_player(player1_name),
                    _collect_player(player2_name),
                )

                players_data = []
                for entry, error_message in collected:
                    if error_message:
                        await loading_msg.edit(content=error_message)
                        return
                    players_data.append(entry)


                if len(players_data) != 2:
                    await loading_msg.edit(content="❌ 두 플레이어 정보를 모두 가져올 수 없습니다.")
                    return

                p1, p2 = players_data[0], players_data[1]
                winner = "무승부"
                if p1['pr'] > p2['pr']:
                    winner = p1['name']
                elif p2['pr'] > p1['pr']:
                    winner = p2['name']

                embed = discord.Embed(
                    title=f"⚔️ {p1['name']} vs {p2['name']}",
                    description=f"**{region_name} 서버** • 승자: **{winner}** 🏆",
                    color=0x3498DB
                )
                embed.add_field(
                    name=f"👤 {p1['name']}",
                    value=(
                        f"```\n"
                        f"PR: {p1['pr']:,}\n"
                        f"전투: {p1['battles']:,}\n"
                        f"승률: {p1['win_rate']:.2f}%\n"
                        f"평균 피해: {p1['avg_damage']:,.0f}\n"
                        f"평균 격침: {p1['avg_frags']:.2f}\n"
                        f"```"
                    ),
                    inline=True
                )
                embed.add_field(
                    name=f"👤 {p2['name']}",
                    value=(
                        f"```\n"
                        f"PR: {p2['pr']:,}\n"
                        f"전투: {p2['battles']:,}\n"
                        f"승률: {p2['win_rate']:.2f}%\n"
                        f"평균 피해: {p2['avg_damage']:,.0f}\n"
                        f"평균 격침: {p2['avg_frags']:.2f}\n"
                        f"```"
                    ),
                    inline=True
                )
                await loading_msg.edit(content="", embed=embed)

        except Exception as e:
            await ctx.send(f"❌ 플레이어 비교 중 오류: {str(e)}")
            print(f"워쉽 비교 오류: {e}")

    @commands.command(name='워쉽랭크')
    async def wows_ranked(self, ctx, region: str = 'na', *, player_name: str = None):
        """랭크전 전적을 검색하는 명령어"""
        try:
            if not player_name:
                if region.lower() in WOWS_API_REGIONS:
                    await ctx.send("❌ 사용법: `.워쉽랭크 [리전] 플레이어명`")
                else:
                    player_name = region
                    region = 'na'
                if not player_name:
                    return
        
            region_lower = region.lower() if region.lower() in WOWS_API_REGIONS else 'na'
            api_base_url = WOWS_API_REGIONS[region_lower]
            region_names = _WOWS_REGION_NAMES
            region_name = region_names.get(region_lower, 'NA')
        
            loading_msg = await ctx.send(f"🔍 '{player_name}' 랭크전 전적 검색 중... ({region_name} 서버)")
        
            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return
        
            async with http_session() as session:
                result = await _wows_find_player(session, api_base_url, player_name)
                if not result:
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                account_id, found_nickname = result
            
                # 랭크전 통계
                stats_url = f"{api_base_url}/wows/account/info/"
                stats_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
            
                async with session.get(stats_url, params=stats_params) as stats_response:
                    stats_data = await stats_response.json()
                    if stats_data.get('status') != 'ok':
                        await loading_msg.edit(content="❌ 통계 정보를 가져올 수 없습니다.")
                        return
                
                    player_data = stats_data['data'][str(account_id)]
                    ranked_stats = player_data.get('statistics', {}).get('rank_solo', {})
                
                    if not ranked_stats or ranked_stats.get('battles', 0) == 0:
                        await loading_msg.edit(content=f"❌ '{found_nickname}' 플레이어의 랭크전 기록이 없습니다.")
                        return
                
                    battles = ranked_stats.get('battles', 0)
                    wins = ranked_stats.get('wins', 0)
                    damage = ranked_stats.get('damage_dealt', 0)
                    win_rate = (wins / battles * 100) if battles > 0 else 0
                    avg_damage = damage / battles if battles > 0 else 0
                
                    embed = discord.Embed(
                        title=f"🏆 {found_nickname}의 랭크전 전적",
                        description=f"**{region_name} 서버**",
                        color=0xFFD700
                    )
                
                    embed.add_field(
                        name="📊 랭크전 통계",
                        value=f"```\n"
                              f"전투: {battles:,}회\n"
                              f"승리: {wins:,}회\n"
                              f"승률: {win_rate:.2f}%\n"
                              f"평균 피해: {avg_damage:,.0f}\n"
                              f"```",
                        inline=False
                    )
                
                    embed.set_footer(text=f"Account ID: {account_id}")
                    await loading_msg.edit(content="", embed=embed)
                    
        except Exception as e:
            await ctx.send(f"❌ 랭크전 전적 검색 중 오류: {str(e)}")
            print(f"워쉽 랭크전 오류: {e}")

    @commands.command(name='워쉽업적')
    async def wows_achievements(self, ctx, region: str = 'na', *, player_name: str = None):
        """업적/배지 조회 명령어"""
        try:
            if not player_name:
                if region.lower() in WOWS_API_REGIONS:
                    await ctx.send("❌ 사용법: `.워쉽업적 [리전] 플레이어명`")
                else:
                    player_name = region
                    region = 'na'
                if not player_name:
                    return
        
            region_lower = region.lower() if region.lower() in WOWS_API_REGIONS else 'na'
            api_base_url = WOWS_API_REGIONS[region_lower]
            region_names = _WOWS_REGION_NAMES
            region_name = region_names.get(region_lower, 'NA')
        
            loading_msg = await ctx.send(f"🔍 '{player_name}' 업적 검색 중... ({region_name} 서버)")
        
            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return
        
            async with http_session() as session:
                result = await _wows_find_player(session, api_base_url, player_name)
                if not result:
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                account_id, found_nickname = result
            
                # 업적 정보
                stats_url = f"{api_base_url}/wows/account/info/"
                stats_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
            
                async with session.get(stats_url, params=stats_params) as stats_response:
                    stats_data = await stats_response.json()
                    if stats_data.get('status') != 'ok':
                        await loading_msg.edit(content="❌ 통계 정보를 가져올 수 없습니다.")
                        return
                
                    player_data = stats_data['data'][str(account_id)]
                    achievements = player_data.get('achievements', {})
                
                    if not achievements:
                        await loading_msg.edit(content=f"❌ '{found_nickname}' 플레이어의 업적 정보가 없습니다.")
                        return
                
                    # 주요 업적 추출
                    major_achievements = {
                        'kraken': achievements.get('kraken_unleashed', 0),
                        'high_caliber': achievements.get('high_caliber', 0),
                        'confederate': achievements.get('confederate', 0),
                        'double_strike': achievements.get('double_strike', 0),
                        'dreadnought': achievements.get('dreadnought', 0),
                        'first_blood': achievements.get('first_blood', 0)
                    }
                
                    embed = discord.Embed(
                        title=f"🏅 {found_nickname}의 업적",
                        description=f"**{region_name} 서버**",
                        color=0xFFD700
                    )
                
                    achievement_text = f"```\n"
                    achievement_text += f"Kraken: {major_achievements['kraken']}회\n"
                    achievement_text += f"High Caliber: {major_achievements['high_caliber']}회\n"
                    achievement_text += f"Confederate: {major_achievements['confederate']}회\n"
                    achievement_text += f"Double Strike: {major_achievements['double_strike']}회\n"
                    achievement_text += f"Dreadnought: {major_achievements['dreadnought']}회\n"
                    achievement_text += f"First Blood: {major_achievements['first_blood']}회\n"
                    achievement_text += f"```"
                
                    embed.add_field(name="⭐ 주요 업적", value=achievement_text, inline=False)
                
                    embed.set_footer(text=f"Account ID: {account_id}")
                    await loading_msg.edit(content="", embed=embed)
                    
        except Exception as e:
            await ctx.send(f"❌ 업적 검색 중 오류: {str(e)}")
            print(f"워쉽 업적 오류: {e}")

    @commands.command(name='워쉽최근전투')
    async def wows_recent_battles(self, ctx, region: str = 'na', *, player_name: str = None):
        """최근 전투 기록을 조회하는 명령어"""
        try:
            if not player_name:
                if region.lower() in WOWS_API_REGIONS:
                    await ctx.send("❌ 사용법: `.워쉽최근전투 [리전] 플레이어명`")
                else:
                    player_name = region
                    region = 'na'
                if not player_name:
                    return
        
            region_lower = region.lower() if region.lower() in WOWS_API_REGIONS else 'na'
            api_base_url = WOWS_API_REGIONS[region_lower]
            region_names = _WOWS_REGION_NAMES
            region_name = region_names.get(region_lower, 'NA')
        
            loading_msg = await ctx.send(f"🔍 '{player_name}' 최근 전투 기록 검색 중... ({region_name} 서버)")
        
            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return
        
            # 주의: Wargaming API는 최근 전투 기록을 직접 제공하지 않습니다
            # 대신 마지막 전투 시간과 전체 통계만 제공됨
            await loading_msg.edit(content="⚠️ Wargaming API는 최근 전투 기록을 직접 제공하지 않습니다.\n대신 전체 통계를 확인하려면 `.워쉽전적` 명령어를 사용하세요.")
        
        except Exception as e:
            await ctx.send(f"❌ 최근 전투 검색 중 오류: {str(e)}")
            print(f"워쉽 최근 전투 오류: {e}")

    @commands.command(name='워쉽랭킹')
    async def wows_ship_ranking(self, ctx, *, ship_name: str):
        """Wargaming API가 함선별 랭킹을 제공하지 않아 .워쉽함선정보로 안내한다."""
        await ctx.send(
            "⚠️ Wargaming API는 함선별 랭킹을 제공하지 않습니다.\n"
            f"대신 `.워쉽함선정보 {ship_name}` 로 함선 정보를 확인하세요."
        )

    @commands.command(name='워쉽티어')
    async def wows_tier_stats(self, ctx, region: str = 'na', *, player_name: str = None):
        """티어별 통계를 조회하는 명령어"""
        try:
            if not player_name:
                if region.lower() in WOWS_API_REGIONS:
                    await ctx.send("❌ 사용법: `.워쉽티어 [리전] 플레이어명`")
                else:
                    player_name = region
                    region = 'na'
                if not player_name:
                    return
        
            region_lower = region.lower() if region.lower() in WOWS_API_REGIONS else 'na'
            api_base_url = WOWS_API_REGIONS[region_lower]
            region_names = _WOWS_REGION_NAMES
            region_name = region_names.get(region_lower, 'NA')
        
            loading_msg = await ctx.send(f"🔍 '{player_name}' 티어별 통계 검색 중... ({region_name} 서버)")
        
            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return
        
            async with http_session() as session:
                result = await _wows_find_player(session, api_base_url, player_name)
                if not result:
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                account_id, found_nickname = result
            
                # 함선별 통계 가져오기
                ships_url = f"{api_base_url}/wows/ships/stats/"
                ships_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
            
                async with session.get(ships_url, params=ships_params) as ships_response:
                    ships_data = await ships_response.json()
                    if ships_data.get('status') != 'ok' or not ships_data.get('data'):
                        await loading_msg.edit(content="❌ 함선 통계를 가져올 수 없습니다.")
                        return
                
                    player_ships = ships_data['data'][str(account_id)]
                
                    # 티어별 집계
                    tier_stats = {}
                    # 티어 정보는 캐시된 백과사전에서 조회
                    all_ships = await get_wows_ships(session, api_base_url, region_lower)
                    ship_tiers = {
                        ship_id: info.get('tier', 0)
                        for ship_id, info in all_ships.items()
                    }
                
                    for ship in player_ships:
                        pvp = ship.get('pvp', {})
                        battles = pvp.get('battles', 0)
                        if battles == 0:
                            continue
                    
                        ship_id = ship['ship_id']
                        tier = ship_tiers.get(ship_id, 0)
                    
                        if tier not in tier_stats:
                            tier_stats[tier] = {'battles': 0, 'wins': 0}
                        tier_stats[tier]['battles'] += battles
                        tier_stats[tier]['wins'] += pvp.get('wins', 0)
                
                    if not tier_stats:
                        await loading_msg.edit(content=f"❌ '{found_nickname}' 플레이어의 티어별 통계가 없습니다.")
                        return
                
                    embed = discord.Embed(
                        title=f"📊 {found_nickname}의 티어별 통계",
                        description=f"**{region_name} 서버**",
                        color=0x3498DB
                    )
                
                    tier_text = "```\n"
                    for tier in sorted(tier_stats.keys(), reverse=True):
                        stats = tier_stats[tier]
                        win_rate = (stats['wins'] / stats['battles'] * 100) if stats['battles'] > 0 else 0
                        tier_text += f"티어 {tier}: {stats['battles']:,}전 ({win_rate:.1f}%)\n"
                    tier_text += "```"
                
                    embed.add_field(name="🎯 티어별 전투", value=tier_text, inline=False)
                    embed.set_footer(text=f"Account ID: {account_id}")
                    await loading_msg.edit(content="", embed=embed)
                    
        except Exception as e:
            await ctx.send(f"❌ 티어별 통계 검색 중 오류: {str(e)}")
            print(f"워쉽 티어 통계 오류: {e}")

    @commands.command(name='워쉽국가')
    async def wows_nation_stats(self, ctx, region: str = 'na', *, player_name: str = None):
        """국가별 통계를 조회하는 명령어"""
        try:
            if not player_name:
                if region.lower() in WOWS_API_REGIONS:
                    await ctx.send("❌ 사용법: `.워쉽국가 [리전] 플레이어명`")
                else:
                    player_name = region
                    region = 'na'
                if not player_name:
                    return
        
            region_lower = region.lower() if region.lower() in WOWS_API_REGIONS else 'na'
            api_base_url = WOWS_API_REGIONS[region_lower]
            region_names = _WOWS_REGION_NAMES
            region_name = region_names.get(region_lower, 'NA')
        
            loading_msg = await ctx.send(f"🔍 '{player_name}' 국가별 통계 검색 중... ({region_name} 서버)")
        
            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return
        
            async with http_session() as session:
                result = await _wows_find_player(session, api_base_url, player_name)
                if not result:
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                account_id, found_nickname = result
            
                # 함선별 통계
                ships_url = f"{api_base_url}/wows/ships/stats/"
                ships_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
            
                async with session.get(ships_url, params=ships_params) as ships_response:
                    ships_data = await ships_response.json()
                    if ships_data.get('status') != 'ok' or not ships_data.get('data'):
                        await loading_msg.edit(content="❌ 함선 통계를 가져올 수 없습니다.")
                        return
                
                    player_ships = ships_data['data'][str(account_id)]
                
                    # 국가별 집계
                    nation_stats = {}
                    # 국가 정보는 캐시된 백과사전에서 조회
                    all_ships = await get_wows_ships(session, api_base_url, region_lower)
                    ship_nations = {
                        ship_id: info.get('nation', 'Unknown')
                        for ship_id, info in all_ships.items()
                    }
                
                    for ship in player_ships:
                        pvp = ship.get('pvp', {})
                        battles = pvp.get('battles', 0)
                        if battles == 0:
                            continue
                    
                        ship_id = ship['ship_id']
                        nation = ship_nations.get(ship_id, 'Unknown')
                    
                        if nation not in nation_stats:
                            nation_stats[nation] = {'battles': 0, 'wins': 0}
                        nation_stats[nation]['battles'] += battles
                        nation_stats[nation]['wins'] += pvp.get('wins', 0)
                
                    if not nation_stats:
                        await loading_msg.edit(content=f"❌ '{found_nickname}' 플레이어의 국가별 통계가 없습니다.")
                        return
                
                    embed = discord.Embed(
                        title=f"🌍 {found_nickname}의 국가별 통계",
                        description=f"**{region_name} 서버**",
                        color=0x3498DB
                    )
                
                    nation_text = "```\n"
                    for nation, stats in sorted(nation_stats.items(), key=lambda x: x[1]['battles'], reverse=True):
                        win_rate = (stats['wins'] / stats['battles'] * 100) if stats['battles'] > 0 else 0
                        nation_text += f"{nation}: {stats['battles']:,}전 ({win_rate:.1f}%)\n"
                    nation_text += "```"
                
                    embed.add_field(name="🎯 국가별 전투", value=nation_text, inline=False)
                    embed.set_footer(text=f"Account ID: {account_id}")
                    await loading_msg.edit(content="", embed=embed)
        
        except Exception as e:
            await ctx.send(f"❌ 국가별 통계 검색 중 오류: {str(e)}")
            print(f"워쉽 국가 통계 오류: {e}")

    @commands.command(name='워쉽타입')
    async def wows_type_stats(self, ctx, region: str = 'na', *, player_name: str = None):
        """타입별 통계를 조회하는 명령어"""
        try:
            if not player_name:
                if region.lower() in WOWS_API_REGIONS:
                    await ctx.send("❌ 사용법: `.워쉽타입 [리전] 플레이어명`")
                else:
                    player_name = region
                    region = 'na'
                if not player_name:
                    return
        
            region_lower = region.lower() if region.lower() in WOWS_API_REGIONS else 'na'
            api_base_url = WOWS_API_REGIONS[region_lower]
            region_names = _WOWS_REGION_NAMES
            region_name = region_names.get(region_lower, 'NA')
        
            loading_msg = await ctx.send(f"🔍 '{player_name}' 타입별 통계 검색 중... ({region_name} 서버)")
        
            if not _wows_api_key_ok():
                await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
                return
        
            async with http_session() as session:
                result = await _wows_find_player(session, api_base_url, player_name)
                if not result:
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                account_id, found_nickname = result
            
                # 함선별 통계
                ships_url = f"{api_base_url}/wows/ships/stats/"
                ships_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
            
                async with session.get(ships_url, params=ships_params) as ships_response:
                    ships_data = await ships_response.json()
                    if ships_data.get('status') != 'ok' or not ships_data.get('data'):
                        await loading_msg.edit(content="❌ 함선 통계를 가져올 수 없습니다.")
                        return
                
                    player_ships = ships_data['data'][str(account_id)]
                
                    # 타입별 집계
                    type_stats = {}
                    # 타입 정보는 캐시된 백과사전에서 조회
                    all_ships = await get_wows_ships(session, api_base_url, region_lower)
                    ship_types = {
                        ship_id: info.get('type', 'Unknown')
                        for ship_id, info in all_ships.items()
                    }
                
                    for ship in player_ships:
                        pvp = ship.get('pvp', {})
                        battles = pvp.get('battles', 0)
                        if battles == 0:
                            continue
                    
                        ship_id = ship['ship_id']
                        ship_type = ship_types.get(ship_id, 'Unknown')
                    
                        if ship_type not in type_stats:
                            type_stats[ship_type] = {'battles': 0, 'wins': 0}
                        type_stats[ship_type]['battles'] += battles
                        type_stats[ship_type]['wins'] += pvp.get('wins', 0)
                
                    if not type_stats:
                        await loading_msg.edit(content=f"❌ '{found_nickname}' 플레이어의 타입별 통계가 없습니다.")
                        return
                
                    embed = discord.Embed(
                        title=f"🚢 {found_nickname}의 타입별 통계",
                        description=f"**{region_name} 서버**",
                        color=0x3498DB
                    )
                
                    type_names = {
                        'Destroyer': '🔰 구축함',
                        'Cruiser': '⚓ 순양함',
                        'Battleship': '🛡️ 전함',
                        'AirCarrier': '✈️ 항공모함',
                        'Submarine': '🔱 잠수함'
                    }
                
                    type_text = "```\n"
                    for ship_type, stats in sorted(type_stats.items(), key=lambda x: x[1]['battles'], reverse=True):
                        type_name = type_names.get(ship_type, ship_type)
                        win_rate = (stats['wins'] / stats['battles'] * 100) if stats['battles'] > 0 else 0
                        type_text += f"{type_name}: {stats['battles']:,}전 ({win_rate:.1f}%)\n"
                    type_text += "```"
                
                    embed.add_field(name="🎯 타입별 전투", value=type_text, inline=False)
                    embed.set_footer(text=f"Account ID: {account_id}")
                    await loading_msg.edit(content="", embed=embed)
                    
        except Exception as e:
            await ctx.send(f"❌ 타입별 통계 검색 중 오류: {str(e)}")
            print(f"워쉽 타입 통계 오류: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(WoWS(bot))
