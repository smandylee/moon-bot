import discord
from discord.ext import commands
import random
import os
from dotenv import load_dotenv
import openai
import datetime
from typing import Optional
import json
import asyncio


# .env 파일에서 환경변수 로드
load_dotenv()

# OpenAI API 설정
openai.api_key = os.getenv('OPENAI_API_KEY')

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True  # 권한 활성화
intents.guilds = True
intents.messages = True
intents.members = True  # 멤버 목록 보기 권한 활성화
bot = commands.Bot(command_prefix='.', intents=intents)

# 봇 초기화 완료
print("🤖 Moon Bot 초기화 완료")

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
'''
@bot.event
async def on_ready():
    """봇이 준비되었을 때 실행되는 이벤트"""
    print('야 이 개시발련들아 나 왔다')
    
    # 잠시 대기 후 메시지 전송 (봇이 완전히 준비될 때까지)
    import asyncio
    await asyncio.sleep(2)
    
    # 특정 채널 ID에만 메시지 전송
    target_channel_id = 1106921812199219380
    
    for guild in bot.guilds:
        target_channel = guild.get_channel(target_channel_id)
        if target_channel and isinstance(target_channel, discord.TextChannel):
            try:
                await target_channel.send('야 이 개시발련들아 나 왔다')
                print(f"출근 메시지 전송 성공: {guild.name} - {target_channel.name}")
                break  # 한 번만 보내고 종료
            except Exception as e:
                print(f"출근 메시지 전송 실패: {guild.name} - {e}")
'''
@bot.command(name='랜덤')
async def random_message(ctx):
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

@bot.command(name='롤')
async def roll_mention(ctx):
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

@bot.command(name='헬다')
async def valorant_mention(ctx):
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

@bot.command(name='배')
async def overwatch_mention(ctx):
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

@bot.command(name='멤버목록')
async def member_list(ctx):
    """봇이 볼 수 있는 멤버 목록을 확인하는 명령어"""
    guild = ctx.guild
    
    # 서버 정보 출력
    await ctx.send(f"📊 **서버 정보**\n"
                  f"서버명: {guild.name}\n"
                  f"전체 멤버 수: {guild.member_count}\n"
                  f"봇이 볼 수 있는 멤버 수: {len(guild.members)}")
    
    # 멤버 목록 출력 (처음 20명만)
    member_list_text = "👥 **멤버 목록 (처음 20명)**\n"
    for i, member in enumerate(guild.members[:20]):
        member_list_text += f"{i+1}. {member.name} ({member.id})\n"
    
    if len(guild.members) > 20:
        member_list_text += f"\n... 그리고 {len(guild.members) - 20}명 더"
    
    await ctx.send(member_list_text)
    
    # 터미널에도 출력
    print(f"\n=== {guild.name} 서버 멤버 목록 ===")
    print(f"전체 멤버 수: {guild.member_count}")
    print(f"봇이 볼 수 있는 멤버 수: {len(guild.members)}")
    print("멤버 목록:")
    for i, member in enumerate(guild.members):
        print(f"{i+1}. {member.name} ({member.id})")
    print("=" * 50)


@bot.command(name='이미지')
async def send_image(ctx, image_url: str, *, title=None):
    """이미지를 임베드로 보내는 명령어"""
    if title is None:
        title = "이미지"
    await send_image_embed(ctx.channel, image_url, title, "사용자가 요청한 이미지입니다.")

@bot.command(name='스카이넷')
async def skynet(ctx):
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

@bot.event
async def on_message(message):
    """모든 메시지를 감지하는 이벤트"""
    print(f"🔍 메시지 수신: {message.author.name} - {message.content[:30]}...")
    
    # 봇 자신의 메시지는 무시
    if message.author == bot.user:
        print("🤖 봇 자신의 메시지 무시")
        return
    
    
    
    # 명령어로 시작하는 메시지는 무시 (명령어 시스템이 처리하도록)
    if message.content.startswith('.'):
        await bot.process_commands(message)
        return
    
    # 특정 유저 ID (여기에 원하는 유저 ID를 입력하세요)
    target_user_id = 320380927857655808  # 실제 유저 ID
    
    # 특정 메시지 내용
    target_messages = ["ㅇㄲㄴ","억까입니다","억까ㄴ","억까ㄴㄴ","억까하지마","억까하지마 시발련아","ㅇㄲㄴㄴ"]
    
    # 특정 유저가 특정 메시지를 입력했을 때
    if message.author.id == target_user_id and message.content in target_messages:
        # 이미지 URL (예시 - 실제 이미지 URL로 변경하세요)
        image_url = "https://hips.hearstapps.com/popularmechanics/assets/16/22/1464974787-terminator-movie-terminator-5-genisys-00.jpg"
        
        # 웹훅 임베드로 이미지 전송
        await send_image_embed(
            message.channel, 
            image_url, 
            "색욕권문", 
            f"{message.author.mention}님이 특별한 이미지를 요청하셨습니다! 🌙"
        )
    
    # "ㅇㅈ" 출력 기능 (아무나 입력 가능)
    # 특정 메시지들을 감지해서 "ㅇㅈ" 출력
    trigger_messages = ["권문 병신", "권문 장애인", "권문 여친 서가영"]
    
    # 아무나 입력해도 "ㅇㅈ" 출력
    if message.content in trigger_messages:
        await message.channel.send("ㅇㅈ")
    
    # "유기" 단어 감지 기능
    if "유기" in message.content:
        await message.channel.send("권문 또 유기야?")
    
    # 민제 시발련아
    if "민제" in message.content:
        await message.channel.send("박민제 시발련아")
    
    # 이재용
    if "이재용" in message.content:
        await message.channel.send("이젖뀨 여미새련")
    
    # 뮤트 기능 - "@유저명 5분동안 닥쳐" 패턴 감지
    import re
    
    # 두 가지 패턴 지원: 맨션 방식과 유저명 직접 입력 방식
    mute_pattern1 = r'<@!?(\d+)>\s*(\d+)분동안\s*닥쳐'  # 맨션 방식
    mute_pattern2 = r'@(\S+)\s+(\d+)분동안\s*닥쳐'      # 유저명 직접 입력 방식
    
    mute_match1 = re.match(mute_pattern1, message.content)
    mute_match2 = re.match(mute_pattern2, message.content)
    
    # 디버깅: 메시지 내용 출력
    print(f"받은 메시지: {message.content}")
    print(f"패턴1 매치: {mute_match1}")
    print(f"패턴2 매치: {mute_match2}")
    
    if mute_match1 or mute_match2:
        try:
            # 어떤 패턴이 매치되었는지 확인
            if mute_match1:
                user_id = int(mute_match1.group(1))
                duration = int(mute_match1.group(2))
            elif mute_match2:
                user_id = int(mute_match2.group(1))
                duration = int(mute_match2.group(2))
            else:
                return  # 매치되지 않았으면 종료
            target_user = message.guild.get_member(user_id)
            
            if target_user:
                # 뮤트 역할 찾기 또는 생성
                mute_role = discord.utils.get(message.guild.roles, name="뮤트")
                if not mute_role:
                    mute_role = await message.guild.create_role(name="뮤트", reason="뮤트 기능을 위한 역할")
                    
                    # 모든 채널에서 뮤트 역할 권한 설정
                    for channel in message.guild.channels:
                        if isinstance(channel, discord.TextChannel):
                            await channel.set_permissions(mute_role, send_messages=False)
                
                # 유저에게 뮤트 역할 추가
                await target_user.add_roles(mute_role, reason=f"메시지 패턴으로 {duration}분 뮤트")
                
                # 음성 채널 뮤트도 함께 적용
                if target_user.voice:
                    await target_user.edit(mute=True, reason=f"음성 채널 {duration}분 뮤트")
                    await message.channel.send(f"🔇 {target_user.mention}을(를) {duration}분간 텍스트+음성 뮤트했습니다.")
                else:
                    await message.channel.send(f"🔇 {target_user.mention}을(를) {duration}분간 텍스트 뮤트했습니다.")
                
                # 지정된 시간 후 뮤트 해제
                import asyncio
                await asyncio.sleep(duration * 60)
                await target_user.remove_roles(mute_role, reason="뮤트 시간 만료")
                
                # 음성 채널 뮤트도 해제
                if target_user.voice:
                    await target_user.edit(mute=False, reason="음성 채널 뮤트 해제")
                    await message.channel.send(f"🔊 {target_user.mention}의 텍스트+음성 뮤트가 해제되었습니다.")
                else:
                    await message.channel.send(f"🔊 {target_user.mention}의 텍스트 뮤트가 해제되었습니다.")
                
        except Exception as e:
            await message.channel.send(f"❌ 뮤트 중 오류가 발생했습니다: {str(e)}")
    
    # 뮤트 해제 기능 - "@유저명 아봉해제" 패턴 감지
    unmute_pattern = r'<@!?(\d+)>\s*아봉해제'
    unmute_match = re.match(unmute_pattern, message.content)
    
    if unmute_match:
        try:
            user_id = int(unmute_match.group(1))
            target_user = message.guild.get_member(user_id)
            
            if target_user:
                mute_role = discord.utils.get(message.guild.roles, name="뮤트")
                is_text_muted = mute_role and mute_role in target_user.roles
                is_voice_muted = target_user.voice and target_user.voice.mute
                
                if is_text_muted or is_voice_muted:
                    # 텍스트 뮤트 해제
                    if is_text_muted:
                        await target_user.remove_roles(mute_role, reason="아봉해제 패턴으로 언뮤트")
                    
                    # 음성 채널 뮤트 해제
                    if is_voice_muted:
                        await target_user.edit(mute=False, reason="음성 채널 뮤트 해제")
                    
                    # 결과 메시지
                    if is_text_muted and is_voice_muted:
                        await message.channel.send(f"🔊 {target_user.mention}의 텍스트+음성 뮤트가 해제되었습니다.")
                    elif is_text_muted:
                        await message.channel.send(f"🔊 {target_user.mention}의 텍스트 뮤트가 해제되었습니다.")
                    elif is_voice_muted:
                        await message.channel.send(f"🔊 {target_user.mention}의 음성 뮤트가 해제되었습니다.")
                else:
                    await message.channel.send(f"❌ {target_user.mention}은(는) 뮤트 상태가 아닙니다.")
                    
        except Exception as e:
            await message.channel.send(f"❌ 언뮤트 중 오류가 발생했습니다: {str(e)}")
    
    # 일반 메시지 처리
    await bot.process_commands(message)

@bot.command(name='gpt')
async def chatgpt_command(ctx, *, message):
    """ChatGPT와 대화하는 명령어"""
    try:
        from openai import OpenAI
        
        # OpenAI 클라이언트 생성
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # ChatGPT API 호출
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": message}
            ],
            max_tokens=1000
        )
        
        # 응답 추출
        reply = response.choices[0].message.content
        
        # 응답 전송
        await ctx.send(f"🤖 **ChatGPT**: {reply}")
        
    except Exception as e:
        await ctx.send(f"❌ 오류가 발생했습니다: {str(e)}")

@bot.command(name='도움말')
async def help_command(ctx):
    """도움말을 출력하는 명령어"""
    help_text = """
**🎮 사용 가능한 명령어들:**

`.랜덤` - 랜덤하게 싹바가지 없이 말한다 
`.이미지 [URL] [제목]` - 이미지를 임베드로 보내기
`.gpt [메시지]` - 핑프년아 니가 검색해(보류)
`.@유저명 [분]동안 닥쳐` - [시간(분)]만큼 닥쳐
`.@유저명 아봉 해제` - 이 위대한 권문이 특별히 자비를 베풀도록 하지
`.뮤트상태 @유저명` - 유저의 뮤트 상태 확인
`.도움말` - 아 도움 유기함 ㅅㄱ
`.배` - 배 탈 사람 맨션
'.헬다' - SAY HELLO TO THE DEMOCRACY
'.롤' - 개병신정신병게임할사람 모집

**🔮 운세 관련 명령어:**
`.가챠운세` - 가챠 전에 확인하는 특별한 운세

**🎯 특별 기능:**
특정 유저가 "ㅇㄲㄴ"을 입력하면 웹훅 임베드로 이미지가 출력됩니다!


```
    """
    await ctx.send(help_text)

@bot.command(name='뮤트상태')
async def mute_status(ctx, user: discord.Member):
    """유저의 뮤트 상태를 확인하는 명령어"""
    mute_role = discord.utils.get(ctx.guild.roles, name="뮤트")
    is_text_muted = mute_role and mute_role in user.roles
    is_voice_muted = user.voice and user.voice.mute
    
    status_text = f"**{user.display_name}의 뮤트 상태:**\n"
    status_text += f"📝 텍스트 뮤트: {'🔇 뮤트됨' if is_text_muted else '🔊 뮤트 안됨'}\n"
    status_text += f"🎤 음성 뮤트: {'🔇 뮤트됨' if is_voice_muted else '🔊 뮤트 안됨'}"
    
    await ctx.send(status_text)







@bot.command(name='가챠운세')
async def yin_pick_fortune(ctx):
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

@bot.command(name='워쉽가챠')
async def warships_gacha(ctx, count: int = 1):
    """월드 오브 워쉽 × 블루 아카이브 콜라보 가챠 시뮬레이터 (1회/10회 뽑기)"""
    if count not in [1, 10]:
        await ctx.send('1회 또는 10회 뽑기만 지원합니다. 예시: `.워쉽가챠 1` 또는 `.워쉽가챠 10`')
        return

    # 아이템 및 확률 정의
    gacha_table = [
        ("VIII BA BINAH", 0.4),
        ("IX BA UTNAPISHTIM", 0.4),
        ("IX BA HOVERCRAFT", 0.4),
        ("X BA ARONA'S WHALE", 0.4),
        ("VIII BA TIRPITZ", 0.5),
        ("IX BA TAKAHASHI", 0.5),
        ("X BA MONTANA", 0.5),
        ("크레딧 +40% × 25", 9.69),
        ("군함 경험치 +200% × 25", 9.69),
        ("함장 경험치 +200% × 25", 9.69),
        ("자유 경험치 +600% × 25", 9.69),
        ("크레딧 +160% × 25", 9.69),
        ("군함 경험치 +800% × 25", 9.69),
        ("함장 경험치 +800% × 25", 9.69),
        ("자유 경험치 +2,400% × 25", 9.69),
        ("1,200,000 크레딧 × 25", 9.69),
        ("신호기 패키지 × 25", 9.69),
    ]

    # 아이템별 이미지 매핑
    item_images = {
        "VIII BA BINAH": "https://static.wikia.nocookie.net/bluarchive/images/2/2a/Binah_Ship.png",
        "IX BA UTNAPISHTIM": "https://static.wikia.nocookie.net/bluarchive/images/3/3b/Utnapishtim_Ship.png",
        "IX BA HOVERCRAFT": "https://static.wikia.nocookie.net/bluarchive/images/4/4c/Hovercraft_Ship.png",
        "X BA ARONA'S WHALE": "https://static.wikia.nocookie.net/bluarchive/images/5/5d/Arona_Ship.png",
        "VIII BA TIRPITZ": "https://static.wikia.nocookie.net/bluarchive/images/6/6e/Tirpitz_Ship.png",
        "IX BA TAKAHASHI": "https://static.wikia.nocookie.net/bluarchive/images/7/7f/Takahashi_Ship.png",
        "X BA MONTANA": "https://static.wikia.nocookie.net/bluarchive/images/8/8a/Montana_Ship.png",
        # 일반 보상은 대표 아이콘(예: 크레딧, 경험치 등)로 대체
        "크레딧 +40% × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "군함 경험치 +200% × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "함장 경험치 +200% × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "자유 경험치 +600% × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "크레딧 +160% × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "군함 경험치 +800% × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "함장 경험치 +800% × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "자유 경험치 +2,400% × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "1,200,000 크레딧 × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
        "신호기 패키지 × 25": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
    }

    # 누적 확률 테이블 생성
    cumulative = []
    acc = 0.0
    for name, prob in gacha_table:
        acc += prob
        cumulative.append((name, acc))

    # 뽑기 함수
    def draw_one():
        r = random.uniform(0, 100)
        for name, upper in cumulative:
            if r < upper:
                return name
        return gacha_table[-1][0]  # fallback

    # 결과 집계
    results = {}
    draws = []
    for _ in range(count):
        item = draw_one()
        draws.append(item)
        results[item] = results.get(item, 0) + 1

    # 결과 임베드 생성
    embed = discord.Embed(
        title=f"월드 오브 워쉽 × 블루 아카이브 콜라보 가챠 시뮬레이터 결과 ({count}회)",
        color=0x3498DB
    )
    # 썸네일 제거 (이미지 표시 X)
    for item, num in results.items():
        embed.add_field(name=item, value=f"{num}개", inline=False)
    await ctx.send(embed=embed)

# 봇 실행
if __name__ == "__main__":
    # 환경변수에서 토큰 가져오기
    TOKEN = os.getenv('DISCORD_TOKEN')
    
    if not TOKEN:
        print("❌ DISCORD_TOKEN이 설정되지 않았습니다!")
        print("1. .env 파일을 생성하고 DISCORD_TOKEN=your_bot_token을 추가하세요")
        print("2. 또는 직접 TOKEN 변수에 봇 토큰을 입력하세요")
        exit(1)
    
    print("🚀 디스코드 봇을 시작합니다...")
    bot.run(TOKEN) 