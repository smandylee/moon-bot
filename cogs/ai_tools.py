"""단발성 AI 기능: .gpt, .부검, .재판."""
from discord.ext import commands
import re
import asyncio

from moonbot.ai import OPENAI_MODEL, ai_generate, gemini_model, get_openai_client
from moonbot.net import scan_channels


class AITools(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='gpt')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def chatgpt_command(self, ctx, *, message):
        """ChatGPT와 대화하는 명령어"""
        try:
            client = get_openai_client()
            if client is None:
                await ctx.send("❌ OpenAI API 키가 설정되지 않았습니다!")
                return
        
            # 동기 SDK라서 스레드에서 호출한다 (이벤트 루프 블로킹 방지)
            response = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "user", "content": message}
                    ],
                    max_tokens=1000
                )
            )
        
            # 응답 추출
            reply = response.choices[0].message.content
        
            # 응답 전송
            await ctx.send(f"🤖 **ChatGPT**: {reply}")
        
        except Exception as e:
            await ctx.send(f"❌ 오류가 발생했습니다: {str(e)}")

    @commands.command(name='부검')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def message_search(self, ctx, *, search_query):
        """키워드 또는 상황으로 메시지를 검색하는 명령어"""
        try:
            # 로딩 메시지 전송
            loading_msg = await ctx.send(f"🔍 '{search_query}' 부검 중... (채팅 기록 수집 중)")
        
            # 검색 결과 저장
            search_results = []
        
            # 모든 텍스트 채널을 병렬로 훑는다.
            # 키워드 히트와 AI 분석용 메시지 풀을 한 번에 모아서, 결과가 부족할 때
            # 전 채널을 다시 스캔하지 않도록 한다.
            async def _scan_for_query(channel):
                hits = []
                pool = []
                async for message in channel.history(limit=2000):
                    if not message.content or message.content.startswith('.'):
                        continue
                    if search_query.lower() in message.content.lower():
                        if len(hits) < 20:
                            hits.append({
                                'message': message,
                                'channel': channel,
                                'type': 'keyword'
                            })
                    elif len(pool) < 100:
                        pool.append(message)
                    if len(hits) >= 20 and len(pool) >= 100:
                        break
                return hits, pool

            message_pool = []
            for hits, pool in await scan_channels(ctx.guild, ctx.guild.me, _scan_for_query):
                search_results.extend(hits)
                message_pool.extend(pool)
            search_results = search_results[:20]
        
            # 키워드 검색 결과가 적으면 상황 검색 시도
            if len(search_results) < 5:
                await loading_msg.edit(content=f"🔍 키워드 검색 결과 부족. AI 상황 분석으로 확장 검색 중...")
            
                # 1차 스캔에서 이미 모아둔 메시지를 재사용한다
                additional_messages = message_pool[:100]
            
                # AI로 상황 분석
                if additional_messages:
                    analysis_text = "\n".join([f"{msg.author.display_name}: {msg.content}" for msg in additional_messages[:50]])
                
                    prompt = f"""
다음은 Discord 서버의 채팅 메시지들이야. 
검색어 "{search_query}"와 관련된 메시지들을 찾아줘.

검색어: {search_query}

분석할 메시지들:
{analysis_text}

다음 기준으로 관련 메시지들을 찾아줘:
1. 키워드가 직접 포함된 메시지
2. 검색어와 의미적으로 관련된 메시지 (상황, 감정, 주제 등)
3. 검색어가 묘사하는 상황과 일치하는 메시지

관련 메시지들의 번호만 알려줘 (1, 3, 7 이런 식으로).
"""
                
                    try:
                        response = await ai_generate(gemini_model, prompt)
                        ai_result = response.text.strip()
                    
                        numbers = re.findall(r'\d+', ai_result)
                    
                        # 해당 번호의 메시지들을 결과에 추가
                        for num in numbers[:10]:  # 최대 10개
                            idx = int(num) - 1
                            if 0 <= idx < len(additional_messages):
                                msg = additional_messages[idx]
                                # 중복 방지
                                if not any(r['message'].id == msg.id for r in search_results):
                                    search_results.append({
                                        'message': msg,
                                        'channel': msg.channel,
                                        'type': 'situation'
                                    })
                    except:
                        pass  # AI 분석 실패시 무시
        
            # 결과가 없으면
            if not search_results:
                await loading_msg.edit(content=f"❌ '{search_query}'와 관련된 메시지를 찾을 수 없어.")
                return
        
            # 결과 정렬 (최신순)
            search_results.sort(key=lambda x: x['message'].created_at, reverse=True)
        
            # 결과 메시지 생성
            result_text = f"🔍 **'{search_query}' 부검 결과** ({len(search_results)}개 발견)\n\n"
        
            for i, result in enumerate(search_results[:10], 1):  # 최대 10개만 표시
                msg = result['message']
                channel = result['channel']
            
                # 시간 포맷
                time_str = msg.created_at.strftime("%Y-%m-%d %H:%M")
            
                # 메시지 내용 (너무 길면 자르기)
                content = msg.content
                if len(content) > 100:
                    content = content[:100] + "..."
            
                # Discord 링크 생성
                message_link = f"https://discord.com/channels/{ctx.guild.id}/{channel.id}/{msg.id}"
            
                result_text += f"**{i}.** {time_str} | {msg.author.display_name}\n"
                result_text += f"💬 {content}\n"
                result_text += f"🔗 {message_link}\n\n"
        
            # 결과 전송
            await loading_msg.edit(content=result_text)
        
        except Exception as e:
            await ctx.send(f"❌ 부검 중 오류가 발생했어: {str(e)}")
            print(f"부검 오류: {e}")

    @commands.command(name='재판')
    @commands.cooldown(1, 60, commands.BucketType.channel)
    async def ai_trial(self, ctx, *, hint: str = None):
        """AI 판사가 최근 대화를 분석해서 판결을 내리는 명령어"""
        try:
            # 로딩 메시지 전송
            loading_msg = await ctx.send("⚖️ **AI 재판소** 개정 중... 최근 대화 수집 중")
        
            # 최근 채팅 수집 (더 많이)
            recent_messages = []
            try:
                async for message in ctx.channel.history(limit=100):
                    if message.content and not message.content.startswith('.'):
                        recent_messages.append({
                            'author': message.author.display_name,
                            'content': message.content,
                            'time': message.created_at.strftime("%H:%M")
                        })
            except:
                pass
        
            if len(recent_messages) < 5:
                await loading_msg.edit(content="❌ 최근 대화가 부족해서 재판을 진행할 수 없어.")
                return
        
            # 시간순으로 정렬 (오래된 것부터)
            recent_messages.reverse()
        
            # 대화 텍스트 생성
            chat_log = "\n".join([f"[{msg['time']}] {msg['author']}: {msg['content']}" for msg in recent_messages[-50:]])
        
            await loading_msg.edit(content="⚖️ **AI 재판소** 대화 분석 중... 🔍")
        
            # 힌트가 있으면 추가
            hint_text = f"\n\n**신고자 힌트:** {hint}" if hint else ""
        
            # Gemini AI로 재판 진행
            prompt = f"""
너는 디스코드 서버의 AI 판사야. 최근 대화 내용을 분석해서 논쟁, 갈등, 분쟁, 또는 재판할 만한 상황을 찾아서 판결해야 해.

**최근 채팅 로그:**
{chat_log}
{hint_text}

**분석 지침:**
1. 대화에서 논쟁, 의견 충돌, 누군가의 잘못, 갈등 상황을 찾아
2. 만약 명확한 갈등이 없다면, 대화 중 재미있게 재판할 수 있는 상황을 찾아 (예: 누가 이상한 말을 했다, 누가 오타를 냈다, 누가 갑자기 뜬금없는 소리를 했다 등)
3. 실제 유저 이름을 사용해서 판결해

**판결 스타일:**
- 진지한 법정 드라마처럼 시작하되 점점 웃기게
- 인터넷 밈이나 게임 용어 활용 가능
- 냉정하지만 유머러스한 판사 캐릭터
- 대화 내용을 근거로 인용하면서 판결

**다음 형식으로 판결문을 작성해줘:**

⚖️ **【 AI 재판소 판결문 】**

👥 **피고인:** [관련 유저 이름]

📋 **사건 개요:**
[대화에서 발견한 상황을 법적 용어로 재미있게 요약]

🔍 **증거 채택:**
[실제 대화 내용 인용 - 2~3개]

⚡ **쟁점:**
[이 사건의 핵심 쟁점]

📜 **판결:**
[유죄/무죄/일부 유죄 등 + 이유]

🔨 **형량 선고:**
[재미있는 벌칙 제안 - 예: 커피 사기, 이모티콘 금지 1일, 사과문 작성, 칭찬 3번 하기 등]

💬 **재판장 코멘트:**
[판사로서 한마디 (약간 꼰대력 + 유머)]

---
*본 판결에 불복할 경우 `.재판 항소할거임` 입력*
"""
        
            # Gemini API 호출
            response = await ai_generate(gemini_model, prompt)
            verdict = response.text
        
            # 결과 전송 (너무 길면 분할)
            if len(verdict) > 1900:
                # 분할 전송
                await loading_msg.edit(content=verdict[:1900])
                await ctx.send(verdict[1900:])
            else:
                await loading_msg.edit(content=verdict)
        
        except Exception as e:
            await ctx.send(f"❌ 재판 중 오류가 발생했어: {str(e)}")
            print(f"재판 오류: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AITools(bot))
