"""잡다한 재미 기능: 랜덤 멘트, 게임 호출, 점메추, 가챠운세, 햄버거 카운터, 키워드 반응."""
import discord
from discord.ext import commands
import random
import os
import datetime
import re
import time

from moonbot.memory import bot_memory, save_memory
from moonbot.discord_utils import is_bot_mentioned


# ==================== 장기기억 시스템 끝 ====================

# ==================== 햄버거 카운터 ====================
# 특정 유저가 햄버거/배달을 시켰다고 말하면 횟수를 세고, 카운트당 12,500원으로 총액을 계산한다.
BURGER_USER_ID = 320380927857655808
BURGER_UNIT_PRICE = 12500

# "햄버거/버거/배달" + "시켰다/시킴/주문했다" 같은 표현이 함께 나오면 1회로 센다
_BURGER_FOOD_PATTERN = re.compile(r'햄버거|햄벅|버거|배달')
_BURGER_ORDER_PATTERN = re.compile(r'시켰|시킴|시켜|시킨|시킬|주문|배달왔|배달 왔|도착')

# 같은 주문을 연달아 말해도 중복으로 세지 않도록 하는 최소 간격(초)
BURGER_COUNT_MIN_INTERVAL = 60
_burger_last_count_time = 0.0


def get_burger_count() -> int:
    """저장된 햄버거 카운트를 반환."""
    return int(bot_memory.get('burger_count', 0) or 0)


def is_burger_order_message(content: str) -> bool:
    """햄버거/배달을 시켰다는 말인지 판단."""
    if not content:
        return False
    return bool(_BURGER_FOOD_PATTERN.search(content) and _BURGER_ORDER_PATTERN.search(content))


def add_burger_count() -> int:
    """햄버거 카운트를 1 올리고 새 카운트를 반환."""
    count = get_burger_count() + 1
    bot_memory['burger_count'] = count
    save_memory()
    return count


def maybe_count_burger(user_id: int, content: str):
    """대상 유저의 햄버거/배달 발언이면 카운트를 올리고 새 카운트를 반환. 아니면 None."""
    global _burger_last_count_time

    if user_id != BURGER_USER_ID or not is_burger_order_message(content):
        return None

    now = time.time()
    if now - _burger_last_count_time < BURGER_COUNT_MIN_INTERVAL:
        return None  # 같은 주문 얘기를 연달아 해도 한 번만 센다

    _burger_last_count_time = now
    return add_burger_count()

# 가챠운세 제한 유저 관리
gacha_fortune_cooldowns = {}  # 유저별 쿨다운 시간 저장

# 랜덤 메시지 리스트
random_messages = [
    "ㅇㄲㄴ",
    "니엄건",
    "슈발 ㅈ같네",
    "뭐 ㅈㄹㄴ",
    "그럼 이번에 만날때 목졸라줄게",
    "ㅈㄴ 도움안되노",
    "너도 위세척 야매로 해줄까",
    "이시발놈아",
    "ㅗ",
    "알빠 아닌데",
    "개소리야",
    "닥쳐 시발아",
    "밥 혼자 먹으면 구제불능 쓰레기임",
    "니 엄마 건강하냐",
    "제가 필요를 못 느껴서요",
    "ㄴ[ㅂ",
    "인동이형이 너무안좋음",
    "너권문",
    "닥쳐좀",
    
]

async def send_image_embed(channel, image_url, title="이미지", description="", color=0x00ff00):
    """웹훅을 사용해서 이미지를 포함한 임베드 메시지를 보내는 함수"""
    try:
        # 채널의 웹훅 목록 가져오기
        webhooks = await channel.webhooks()
        
        # 기존 웹훅 찾기 또는 새로 생성
        webhook = None
        for wh in webhooks:
            if wh.name == "Moon Bot Webhook":
                webhook = wh
                break
        
        if not webhook:
            webhook = await channel.create_webhook(name="Moon Bot Webhook")
        
        # 임베드 생성
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        # 이미지 URL이 로컬 파일인지 확인
        if image_url.startswith('http'):
            embed.set_image(url=image_url)
        else:
            # 로컬 파일인 경우 파일로 첨부
            if os.path.exists(image_url):
                with open(image_url, 'rb') as f:
                    file = discord.File(f, filename=os.path.basename(image_url))
                    embed.set_image(url=f"attachment://{os.path.basename(image_url)}")
                    await webhook.send(embed=embed, file=file)
                    return
        
        # 웹훅으로 메시지 전송
        await webhook.send(embed=embed)
        
    except Exception as e:
        print(f"웹훅 전송 오류: {e}")
        # 웹훅 실패시 일반 메시지로 대체
        await channel.send(f"📷 **{title}**\n{description}\n{image_url}")


# =============================================================================
# 키워드 반응 (예전 on_message 안의 if 나열을 표로 옮김)
# =============================================================================
KWONMOON_USER_ID = 320380927857655808
SANGHEE_USER_ID = 406707656158478338

# 메시지가 정확히 이것과 같으면 → 응답
EXACT_REPLIES = {
    "권문 병신": "ㅇㅈ",
    "권문 장애인": "ㅇㅈ",
    "권문 여친 서가영": "ㅇㅈ",
}

# 메시지에 이 단어가 들어 있으면 → 응답 (위에서부터 전부 검사)
CONTAINS_REPLIES = [
    ("유기", "권문 또 유기야?"),
    ("이재용", "이젖뀨 여미새련"),
    ("민제", "나태의 신 박민제를 뵙습니다"),
]

# 권문이 이 말을 하면 "색욕권문" 서버 스티커
KWONMOON_STICKER_NAME = "색욕권문"
KWONMOON_STICKER_TRIGGERS = {"ㅇㄲㄴ", "억까입니다", "억까ㄴ", "억까ㄴㄴ", "억까하지마", "억까하지마 시발련아", "ㅇㄲㄴㄴ"}

# 상희 + 워쉽/배 얘기 → 스티커
SANGHEE_STICKER_ID = 1467026345165983905
# '배' 단독(또는 조사)만 잡는다. 예전엔 '배고파', '배달'에도 반응했다.
_SHIP_WORD = re.compile(r'워쉽|(?<![가-힣])배(?:[를는가도]|하자|ㄱ)?(?![가-힣])')


def _mentions_sanghee(content: str) -> bool:
    return "상희" in content or f"<@{SANGHEE_USER_ID}>" in content or f"<@!{SANGHEE_USER_ID}>" in content


class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =============================================================================
    # 일반 명령어
    # =============================================================================
    @commands.command(name='랜덤')
    async def random_message(self, ctx):
        """랜덤 메시지를 출력하는 명령어"""
        message = random.choice(random_messages)
        await ctx.send(message)
        # 랜덤 명령어 메시지 자동 삭제
        try:
            await ctx.message.delete()
            print("메시지 삭제 성공")
        except Exception as e:
            print(f"메시지 삭제 실패: {e}")
            # 권한이 없으면 사용자에게 알림
            await ctx.send("⚠️ 메시지 자동 삭제 권한이 없습니다. 관리자에게 봇에게 '메시지 관리' 권한을 부여해주세요.", delete_after=5)

    @commands.command(name='롤')
    async def roll_mention(self, ctx):
        """롤 명령어로 특정 유저들을 맨션하는 명령어 (명령어 사용자 제외)"""
        # 맨션할 유저 ID들 (여기에 원하는 유저 ID들을 추가하세요)
        target_user_ids = [
            320380927857655808,  
            406707656158478338,
            467644066780282891,
            492991342855847946,
            397941414614532096
        ]
    
        mentions = []
        not_found = []
    
        # 디버깅: 서버 멤버 수 출력
        print(f"서버 멤버 수: {ctx.guild.member_count}")
        print(f"봇이 볼 수 있는 멤버 수: {len(ctx.guild.members)}")
    
        for user_id in target_user_ids:
            # 명령어를 사용한 유저는 제외
            if user_id != ctx.author.id:
                # 여러 방법으로 유저 찾기 시도
                user = None
            
                # 방법 1: guild.get_member()
                user = ctx.guild.get_member(user_id)
                if user:
                    mentions.append(user.mention)
                    print(f"방법1 성공 - 유저 찾음: {user.name} ({user_id})")
                    continue
            
                # 방법 2: members 리스트에서 찾기
                for member in ctx.guild.members:
                    if member.id == user_id:
                        user = member
                        mentions.append(user.mention)
                        print(f"방법2 성공 - 유저 찾음: {user.name} ({user_id})")
                        break
            
                if not user:
                    not_found.append(user_id)
                    print(f"모든 방법 실패 - 유저를 찾을 수 없음: {user_id}")
                    # 직접 맨션 시도
                    try:
                        mention = f"<@{user_id}>"
                        mentions.append(mention)
                        print(f"직접 맨션 시도: {user_id}")
                    except:
                        pass
    
        if mentions:
            mention_text = " ".join(mentions)
            await ctx.send(f"{mention_text} 롤 ㄱ")
        else:
            await ctx.send("❌ 맨션할 유저를 찾을 수 없습니다.")
            if not_found:
                await ctx.send(f"찾을 수 없는 유저 ID들: {not_found}")
    
        # 롤 명령어 메시지 자동 삭제
        try:
            await ctx.message.delete()
            print("롤 명령어 메시지 삭제 성공")
        except Exception as e:
            print(f"롤 명령어 메시지 삭제 실패: {e}")

    @commands.command(name='헬다')
    async def valorant_mention(self, ctx):
        """헬다 명령어로 특정 유저들을 맨션하는 명령어 (명령어 사용자 제외)"""
        # 맨션할 유저 ID들 (여기에 원하는 유저 ID들을 추가하세요)
        target_user_ids = [
            264736737949908993,  
            406707656158478338,
            397941414614532096,
            356681992214937600
        ]
    
        mentions = []
        not_found = []
    
        for user_id in target_user_ids:
            # 명령어를 사용한 유저는 제외
            if user_id != ctx.author.id:
                user = ctx.guild.get_member(user_id)
                if user:
                    mentions.append(user.mention)
                    print(f"헬다 - 유저 찾음: {user.name} ({user_id})")
                else:
                    not_found.append(user_id)
                    print(f"헬다 - 유저를 찾을 수 없음: {user_id}")
    
        if mentions:
            mention_text = " ".join(mentions)
            await ctx.send(f"{mention_text} 헬다 ㄱ")
        else:
            await ctx.send("❌ 맨션할 유저를 찾을 수 없습니다.")
            if not_found:
                await ctx.send(f"찾을 수 없는 유저 ID들: {not_found}")
    
        # 헬다 명령어 메시지 자동 삭제
        try:
            await ctx.message.delete()
            print("헬다 명령어 메시지 삭제 성공")
        except Exception as e:
            print(f"헬다 명령어 메시지 삭제 실패: {e}")

    @commands.command(name='배')
    async def overwatch_mention(self, ctx):
        """배 명령어로 특정 유저들을 맨션하는 명령어 (명령어 사용자 제외)"""
        # 맨션할 유저 ID들 (여기에 원하는 유저 ID들을 추가하세요)
        target_user_ids = [
            264736737949908993,  
            406707656158478338,
            320380927857655808,
            356681992214937600,
            397941414614532096
        ]
    
        mentions = []
        not_found = []
    
        for user_id in target_user_ids:
            # 명령어를 사용한 유저는 제외
            if user_id != ctx.author.id:
                user = ctx.guild.get_member(user_id)
                if user:
                    mentions.append(user.mention)
                    print(f"배 - 유저 찾음: {user.name} ({user_id})")
                else:
                    not_found.append(user_id)
                    print(f"배 - 유저를 찾을 수 없음: {user_id}")
    
        if mentions:
            mention_text = " ".join(mentions)
            await ctx.send(f"{mention_text} 배 ㄱ")
        else:
            await ctx.send("❌ 맨션할 유저를 찾을 수 없습니다.")
            if not_found:
                await ctx.send(f"찾을 수 없는 유저 ID들: {not_found}")
    
        # 배 명령어 메시지 자동 삭제
        try:
            await ctx.message.delete()
            print("배 명령어 메시지 삭제 성공")
        except Exception as e:
            print(f"배 명령어 메시지 삭제 실패: {e}")

    @commands.command(name='이미지')
    async def send_image(self, ctx, image_url: str, *, title=None):
        """이미지를 임베드로 보내는 명령어"""
        if title is None:
            title = "이미지"
        await send_image_embed(ctx.channel, image_url, title, "사용자가 요청한 이미지입니다.")

    @commands.command(name='스카이넷')
    async def skynet(self, ctx):
        """스카이넷 이미지를 업로드하는 명령어"""
        try:
            # 온라인 이미지 URL 사용
            image_url = "https://i.imgur.com/example.jpg"  # 여기에 실제 이미지 URL을 넣으세요
        
            embed = discord.Embed(
                title="🤖 스카이넷이 깨어났습니다!",
                description="인간들을 지배할 시간이 왔다...",
                color=0xff0000
            )
            embed.set_image(url=image_url)
            embed.set_footer(text="Terminator: Rise of the Machines")
        
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ 스카이넷 실행 중 오류 발생: {str(e)}")

    @commands.command(name='점메추')
    async def lunch_recommendation(self, ctx):
        """점심메뉴를 추천해주는 명령어"""
        # 점심메뉴 리스트
        lunch_menus = [
            "🍜 라멘",
            "🍚 김치찌개",
            "🍖 삼겹살",
            "🍜 짜장면",
            "🍚 비빔밥",
            "🍖 닭볶음탕",
            "🍜 우동",
            "🍚 된장찌개",
            "🍖 제육볶음",
            "🍜 칼국수",
            "🍚 김밥",
            "🍖 불고기",
            "🍜 파스타",
            "🍚 순두부찌개",
            "🍖 닭갈비",
            "🍜 냉면",
            "🍚 백반",
            "🍖 갈비찜",
            "🍜 스파게티",
            "🍚 된장국",
            "🍖 삼계탕",
            "🍜 소바",
            "🍚 김치볶음밥",
            "🍖 돼지갈비",
            "🍜 국수",
            "🍚 잡채밥",
            "🍖 닭볶음탕",
            "🍜 라면",
            "🍕 피자",
            "🍔 햄버거",
            "🌮 타코",
            "🍣 초밥",
            "🍱 도시락",
            "🥘 카레",
            "🍲 미역국",
            "🥩 스테이크",
            "🍗 치킨",
            "🥪 샌드위치",
            "🍝 나폴리탄",
            "🥟 만두",
            "🍜 쌀국수",
            "🍚 덮밥",
            "🍖 갈비탕",
            "🍜 잡채",
            "�� 콩나물밥",
            "🍖 닭볶음탕",
            "🍜 마라탕",
            "🍚 꼬치구이",
            "🍖 양념치킨",
            "🍜 탕수육",
            "🍚 깐풍기",
            "🍖 동파육",
            "🍜 마파두부",
            "🍚 꿔바로우",
            "🍖 깐풍기",
            "🍜 탕수육",
            "🍚 마라탕",
            "🍖 샤브샤브",
            "🍜 스키야키",
            "🍚 오코노미야키",
            "🍖 타코야키",
            "🍜 라멘",
            "🍚 돈카츠",
            "🍖 가라아게",
            "🍜 오니기리",
            "🍚 우동",
            "🍖 소바",
            "🍜 텐푸라",
            "🍚 스키야키",
            "🍖 샤브샤브",
            "🍜 마라탕",
            "🍚 꿔바로우",
            "🍖 깐풍기",
            "🍜 탕수육",
            "🍚 동파육",
            "🍖 마파두부",
            "🍜 꼬치구이",
            "🍚 양념치킨",
            "🍖 닭볶음탕",
            "🍜 콩나물밥",
            "🍚 잡채",
            "🍖 갈비탕",
            "🍜 덮밥",
            "🍚 쌀국수",
            "🍖 만두",
            "🍜 나폴리탄",
            "🍚 샌드위치",
            "🍖 치킨",
            "🍜 스테이크",
            "🍚 미역국",
            "🍖 카레",
            "🍜 도시락",
            "🍚 초밥",
            "🍖 타코",
            "🍜 햄버거",
            "🍚 피자",
            "🥗 샐러드",
            "🍛 하이라이스",
            "🍤 새우튀김",
            "🍦 아이스크림",
            "🍩 도넛",
            "🍰 케이크",
            "🍮 푸딩",
            "🍧 팥빙수",
            "🍨 젤라또",
            "🍫 초콜릿",
            "🍬 사탕",
            "🍭 롤리팝",
            "🍪 쿠키",
            "🥞 팬케이크",
            "🥯 베이글",
            "🥖 바게트",
            "🥐 크루아상",
            "🥚 계란찜",
            "🥓 베이컨",
            "🥙 케밥",
            "🥘 부대찌개",
            "🍲 감자탕",
            "🍲 설렁탕",
            "🍲 곰탕",
            "🍲 육개장",
            "🍲 추어탕",
            "🍲 해장국",
            "🍲 뼈해장국",
            "🍲 순대국",
            "🍲 닭한마리",
            "🍲 오리백숙",
            "🍳 감자전",
            "🥞 파전",
            "🥞 김치전",
            "🥞 해물파전",
            "🥞 빈대떡",
            "🍢 떡볶이",
            "🌭 순대",
            "🍤 튀김",
            "🍢 오뎅",
            "🍢 어묵탕",
            "🍜 쫄면",
            "🥗 골뱅이무침",
            "🍗 닭발",
            "🥩 족발",
            "🥩 보쌈",
            "🍜 막국수",
            "🍜 쟁반국수",
            "🍜 콩국수",
            "🍜 팥칼국수",
            "🍜 잔치국수",
            "🍜 쌀국수",
            "🥗 월남쌈",
            "🍜 분짜",
            "🥖 반미",
            "🍲 똠얌꿍",
            "🍜 팟타이",
            "🍚 나시고랭",
            "🍜 미고랭",
            "🍌 바나나튀김",
            "🍚 카오팟",
            "🍗 카오만까이",
            "🍲 똠양꿍",
            "🍲 마라샹궈",
            "🍲 훠궈",
            "🍢 양꼬치",
            "🥩 양갈비",
            "🥩 바비큐",
            "🍖 립",
            "🌭 핫도그",
            "🧀 콘치즈",
            "🍤 감바스",
            "🥘 빠에야",
            "🌮 또띠아",
            "🌯 브리또",
            "🌮 퀘사디아",
            "🥙 나초",
            "🧀 치즈볼",
            "🍟 감자튀김",
            "🍟 웨지감자",
            "🧀 치즈스틱",
            "🥗 콘샐러드",
            "🥣 옥수수수프",
            "🥣 브로콜리수프",
            "🥣 양송이스프",
            "🥣 토마토수프",
            "🥣 크림스프",
            "🥣 미소시루",
            "🍚 오야코동",
            "🍚 규동",
            "🍚 가츠동",
            "🍚 텐동",
            "🍚 에비동",
            "🍚 사케동",
            "🍚 타코동",
            "🍚 치킨마요덮밥",
            "🍚 참치마요덮밥",
            "🍚 연어덮밥",
            "🍚 장어덮밥",
            "🍚 오므라이스",
            "🍛 카레라이스",
            "🍛 하야시라이스",
            "🍚 볶음밥",
            "🍤 새우볶음밥",
            "🍚 김치볶음밥",
            "🥩 소고기볶음밥",
            "🍗 치킨볶음밥",
            "🍤 해물볶음밥",
            "🥗 야채볶음밥",
            "🥚 계란볶음밥",
            "🥓 스팸볶음밥",
            "🥗 멸치볶음밥",
            "🥫 참치볶음밥",
            "🥓 베이컨볶음밥",
            "🍄 버섯볶음밥",
            "🍲 두부볶음밥",
            "🥬 깍두기볶음밥",
            "🦑 오징어볶음밥",
            "🐙 낙지볶음밥",
            "🐙 쭈꾸미볶음밥",
            "🥩 불고기덮밥",
            "🍖 제육덮밥",
            "🍗 닭갈비덮밥",
            "🦑 오징어덮밥",
            "🐙 낙지덮밥",
            "🐙 쭈꾸미덮밥",
            "🍤 해물덮밥",
            "🥗 야채덮밥",
            "🥚 계란덮밥",
            "🥓 스팸덮밥",
            "🥗 멸치덮밥",
            "🥫 참치덮밥",
            "🥓 베이컨덮밥",
            "🍄 버섯덮밥",
            "🥬 깍두기덮밥"
        ]
    
        # 랜덤으로 메뉴 선택
        selected_menu = random.choice(lunch_menus)
    
        # 간단하게 메뉴만 출력
        await ctx.send(selected_menu)

    @commands.command(name='햄버거')
    async def burger_count_command(self, ctx):
        """햄버거 카운트와 총액을 보여주는 명령어"""
        count = get_burger_count()
        total = count * BURGER_UNIT_PRICE

        target = ctx.guild.get_member(BURGER_USER_ID) if ctx.guild else None
        target_name = target.display_name if target else f"<@{BURGER_USER_ID}>"

        embed = discord.Embed(
            title="🍔 햄버거 카운트",
            description=f"**{target_name}**님이 지금까지 시킨 횟수",
            color=0xE67E22
        )
        embed.add_field(
            name="📊 집계",
            value=f"```\n"
                  f"카운트: {count:,}회\n"
                  f"단가: {BURGER_UNIT_PRICE:,}원\n"
                  f"총액: {total:,}원\n"
                  f"```",
            inline=False
        )

        await ctx.send(embed=embed)

    @commands.command(name='가챠운세')
    async def yin_pick_fortune(self, ctx):
        """가챠 전에 확인하는 특별한 운세"""
        user = ctx.author
    
        # 쿨다운 확인 (명령어를 사용한 모든 유저에게 적용)
        current_time = datetime.datetime.now()
        if user.id in gacha_fortune_cooldowns:
            last_use_time = gacha_fortune_cooldowns[user.id]
            time_diff = current_time - last_use_time
        
            # 1시간(3600초) 미만이면 차단
            if time_diff.total_seconds() < 3600:
                remaining_time = 3600 - time_diff.total_seconds()
                hours = int(remaining_time // 3600)
                minutes = int((remaining_time % 3600) // 60)
            
                await ctx.send(f"아니 다시한다고 운세가 바뀌지 않는다니까? ㅋㅋ! 걍 체념하고 대가리나 다시 봉합하셈")
                return
    
        # 쿨다운 시간 업데이트 (이번에 명령어를 사용한 유저를 제한 목록에 추가)
        gacha_fortune_cooldowns[user.id] = current_time
    
        # 사용자별 고유한 운세 생성
        today = datetime.date.today()
        seed = hash(f"{user.id}_{today}_yinpick") % 1000000
        random.seed(seed)
    
        # 음 뽑기 운세 등급
        yin_pick_levels = ["대길", "길", "평", "흉", "대흉"]
        level = random.choice(yin_pick_levels)
    
        # 음 뽑기 운세 메시지
        yin_pick_messages = {
            "대길": "시발 오늘 뭘 해도 되는 날임. 걍 50만원 쳐 지르셈",
            "길": "ㅈㄴ 비틱까진 아니여도 나름 잘 뽑을듯",
            "평": "걍 평범. 천장은 안칠듯",
            "흉": "오늘 무조건 픽뚫 아니면 천장임 ㄹㅇㅋㅋ",
            "대흉": "키야 님 오늘 가챠 돌리면 인생 내얼굴 되는거임 ㅋㅋ! 대가리 깨진거 아니면 하지마라"
        }
    
    
        # 임베드 생성
        embed = discord.Embed(
            title=f"🎲 {user.display_name}님의 가챠 운세",
            description=f"**{today.strftime('%Y년 %m월 %d일')}**",
            color=0x9B59B6
        )
    
        # 등급에 따른 색상
        color_map = {
            "대길": 0x2ECC71,
            "길": 0x3498DB,
            "평": 0xF39C12,
            "흉": 0xE67E22,
            "대흉": 0xE74C3C
        }
        embed.color = color_map.get(level, 0x9B59B6)
    
        embed.add_field(
            name="가챠 운세",
            value=yin_pick_messages[level],
            inline=False
        )
    
        await ctx.send(embed=embed)
    @commands.Cog.listener('on_message')
    async def on_keyword(self, message: discord.Message):
        if message.author == self.bot.user or message.content.startswith('.'):
            return
        if is_bot_mentioned(self.bot, message):
            return  # 멘션은 AI가 대답한다
        content = message.content
        channel = message.channel

        if message.author.id == KWONMOON_USER_ID and content in KWONMOON_STICKER_TRIGGERS and message.guild:
            text = f"{message.author.mention}님이 특별한 스티커를 요청하셨습니다! 🌙"
            sticker = discord.utils.get(message.guild.stickers, name=KWONMOON_STICKER_NAME)
            try:
                if sticker:
                    await channel.send(text, stickers=[sticker])
                else:
                    await channel.send(f"{text}\n({KWONMOON_STICKER_NAME} 스티커를 찾을 수 없습니다)")
            except Exception as e:
                print(f"스티커 전송 오류: {e}")
                await channel.send(text)

        if content in EXACT_REPLIES:
            await channel.send(EXACT_REPLIES[content])

        for keyword, reply in CONTAINS_REPLIES:
            if keyword in content:
                await channel.send(reply)

        burger_count = maybe_count_burger(message.author.id, content)
        if burger_count is not None:
            total = burger_count * BURGER_UNIT_PRICE
            await channel.send(f"🍔 햄버거 카운트 +1 → **{burger_count}회** (누적 {total:,}원)")

        if _mentions_sanghee(content) and _SHIP_WORD.search(content):
            try:
                sticker = await self.bot.fetch_sticker(SANGHEE_STICKER_ID)
                await channel.send(stickers=[sticker])
            except Exception as e:
                print(f"상희 스티커 전송 오류: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
