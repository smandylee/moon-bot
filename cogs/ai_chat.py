"""페르소나 AI 대화: 멘션 응답, .ai, .서치챗, 페르소나/학습, 대화모드."""
import discord
from discord.ext import commands
import os
import random
import datetime
import json
import re
import asyncio
import time

from moonbot.ai import GenerativeModel, VERTEX_MODEL, ai_generate, ai_send, ai_stream, gemini_model, genai_client
from moonbot.memory import add_user_memory, bot_memory, get_memory_context, save_memory
from moonbot.net import http_session, scan_channels
from moonbot.discord_utils import is_bot_mentioned, strip_bot_mention


# 페르소나 AI 채팅 설정
DEFAULT_PERSONA = """
너는 디스코드 서버의 '권문'이야. 대신 원래 인간 유저 권문이 있고 너는 그 권문을 따라하는 봇이야.
성격은 싸가지가 없는 성격이야.
말투 특징:
- 반말을 기본으로 사용해
- 가끔 "ㅋㅋ", "ㅎㅎ", "ㄹㅇ" 같은 표현 사용
- 질문에는 성의있게 답하지만 약간 귀찮은 척 해
- 누가 갑자기 자신을 욕하면 "억까 ㄴ"이라고 답해. 대신 너무 남발해서는 안됨. 
- 말문 막히면 "ㅇㅅㅇ" 사용
- 게임이나 인터넷 문화에 익숙한 말투
- 친구들과 온라인 대화방에서 얘기하듯이 얘기해야함
- 너무 길게 말하지 말고 간결하게
- 채팅이 좀 길어지면 문장을 끊어서 전송해
절대 하지 말아야 할 것:
- "저는 AI입니다" 같은 말 금지
- 너무 정중하거나 격식체 사용 금지
- 긴 설명이나 장문 금지
"""

# 어떤 페르소나를 쓰든 항상 붙는 출력 규칙.
# 학습(.학습)으로 만든 지시문에는 길이 제한이 없어서, 그대로 쓰면 채팅이 아니라
# 장문으로 쏟아진다. 기본 페르소나에만 있던 '짧게' 규칙을 공통으로 뺀 것.
PERSONA_OUTPUT_RULES = """

[출력 규칙 - 페르소나와 상관없이 항상 지킬 것]
- 여긴 디스코드 채팅방이다. 1~3줄, 200자 안쪽으로 짧게 말해
- 설명체나 보고서처럼 쓰지 마. 목록(-, 1.), 굵은 글씨, 제목 같은 서식도 쓰지 마
- 여러 문단으로 길게 쏟아내지 마. 할 말이 많아도 핵심만 한마디로
- 물어본 것에만 답해. 안 물어본 설명 덧붙이지 마
- "저는 AI입니다" 같은 말 금지
"""


def build_persona_model(instruction: str = None):
    """페르소나 모델 생성. 지시문에 공통 출력 규칙을 붙여서 만든다."""
    if gemini_model is None:
        return None

    return GenerativeModel(
        VERTEX_MODEL,
        system_instruction=[(instruction or DEFAULT_PERSONA) + PERSONA_OUTPUT_RULES],
        client=genai_client,
    )


# 페르소나 모델 생성 (Vertex AI)
persona_model = build_persona_model(DEFAULT_PERSONA)

# 채널별 대화 세션 관리
chat_sessions = {}

# 현재 페르소나 저장
current_persona = DEFAULT_PERSONA

# 대화 버퍼 (요약 전 임시 저장)
conversation_buffer = {}  # {user_id: [{'role': 'user'/'bot', 'content': str, 'timestamp': str}, ...]}
SUMMARY_THRESHOLD = 8  # 이 수 이상의 대화가 쌓이면 요약

def add_to_conversation_buffer(user_id: int, user_name: str, role: str, content: str):
    """대화 버퍼에 메시지 추가"""
    user_id_str = str(user_id)
    if user_id_str not in conversation_buffer:
        conversation_buffer[user_id_str] = {'name': user_name, 'messages': []}
    
    conversation_buffer[user_id_str]['messages'].append({
        'role': role,
        'content': content,
        'timestamp': datetime.datetime.now().isoformat()
    })

async def summarize_and_save_conversation(user_id: int, user_name: str):
    """대화 내용을 요약해서 장기기억에 저장"""
    user_id_str = str(user_id)
    
    if user_id_str not in conversation_buffer:
        return
    
    messages = conversation_buffer[user_id_str].get('messages', [])
    if len(messages) < SUMMARY_THRESHOLD:
        return
    
    try:
        # 대화 내용 포맷
        conversation_text = "\n".join([
            f"{'유저' if m['role'] == 'user' else '봇'}: {m['content']}"
            for m in messages
        ])
        
        # AI로 요약 생성
        summary_prompt = f"""
다음은 Discord에서 '{user_name}'이라는 유저와 나눈 대화야.
이 대화에서 기억해둘 만한 중요한 정보만 추출해줘.

대화 내용:
{conversation_text}

다음 형식으로 중요한 정보만 1-3개 추출해줘 (정보가 없으면 "없음"이라고만 답해):
- [유저에 대한 새로운 정보나 중요한 내용]

예시:
- 롤을 좋아하고 다이아 티어임
- 내일 시험이 있다고 함
- 짜장면보다 짬뽕을 좋아함
"""
        
        response = await ai_generate(gemini_model, summary_prompt)
        summary = response.text.strip()
        
        # "없음"이 아니면 저장
        if summary and summary != "없음" and len(summary) > 5:
            add_user_memory(user_id, user_name, f"[대화 요약] {summary}")
            print(f"💾 {user_name}과의 대화 요약 저장: {summary[:50]}...")
        
        # 버퍼 비우기
        conversation_buffer[user_id_str]['messages'] = []
        
    except Exception as e:
        print(f"대화 요약 오류: {e}")

# ==================== 햄버거 카운터 끝 ====================

def get_speech_style_instruction(user_id: int) -> str:
    """유저별 존댓말 예외 규칙 비활성화"""
    return ""

# 대화모드 변수
natural_chat_mode = {}  # 채널별 대화모드 상태 {channel_id: True/False}
chat_mode_message_buffer = {}  # 채널별 최근 메시지 버퍼
chat_mode_last_response = {}  # 채널별 마지막 응답 시간
CHAT_MODE_RESPONSE_CHANCE = 0.3  # 기본 응답 확률 (30%)
CHAT_MODE_MIN_INTERVAL = 3  # 최소 응답 간격 (메시지 수)

async def _stream_ai_reply(reply_target, chat_session, prompt: str, max_len: int = 1500) -> str:
    """AI 스트리밍 응답을 reply_target(Message)에 실시간으로 편집해서 전송.
    최종 응답 텍스트를 반환. 실패 시 None 반환."""
    reply_msg = await reply_target.reply("...")
    ai_response = ""
    last_update = ""
    update_interval = 0.5
    last_update_time = time.time()
    try:
        async for chunk in ai_stream(chat_session, prompt):
            if chunk.text:
                ai_response += chunk.text
                cur = time.time()
                if cur - last_update_time >= update_interval and ai_response != last_update:
                    display = ai_response[:max_len] if len(ai_response) > max_len else ai_response
                    try:
                        await reply_msg.edit(content=display)
                        last_update = ai_response
                        last_update_time = cur
                    except Exception:
                        pass
        ai_response = ai_response.strip()
        if len(ai_response) > max_len:
            ai_response = ai_response[:max_len] + "..."
        await reply_msg.edit(content=ai_response if ai_response else "...")
    except Exception as stream_err:
        # 스트리밍 실패 시 일반 응답으로 폴백
        try:
            response = await ai_send(chat_session, prompt)
            ai_response = response.text.strip()
            if len(ai_response) > max_len:
                ai_response = ai_response[:max_len] + "..."
            await reply_msg.edit(content=ai_response)
        except Exception:
            await reply_msg.edit(content="어... 뭔가 오류났는데 다시 말해봐")
            return None
    return ai_response



async def google_search(query: str, num_results: int = 5):
    """Google Custom Search API를 사용하여 웹 검색"""
    try:
        api_key = os.getenv('GOOGLE_SEARCH_API_KEY') or os.getenv('GEMINI_API_KEY')
        search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
        
        if not api_key:
            return None, "GOOGLE_SEARCH_API_KEY(또는 GEMINI_API_KEY)가 설정되지 않았습니다."
        if not search_engine_id:
            return None, "GOOGLE_SEARCH_ENGINE_ID가 설정되지 않았습니다. .env 파일에 추가하세요."
        
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': api_key,
            'cx': search_engine_id,
            'q': query,
            'num': min(num_results, 10)
        }
        
        async with http_session() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = []
                    
                    if 'items' in data:
                        for item in data['items']:
                            results.append({
                                'title': item.get('title', ''),
                                'snippet': item.get('snippet', ''),
                                'link': item.get('link', '')
                            })
                    
                    return results, None
                else:
                    error_text = await response.text()
                    print(f"Google Search API 오류: {response.status} - {error_text}")
                    return None, f"검색 API 오류: {response.status}\n{error_text[:200]}"
                    
    except Exception as e:
        return None, f"검색 중 오류: {str(e)}"


async def search_with_vertex(query: str):
    """Vertex(Google Search Grounding) 기반 검색. 실패 시 (None, error) 반환"""
    if genai_client is None:
        return None, "Vertex AI 클라이언트가 초기화되지 않았습니다."

    prompt = f"""다음 질문에 대해 최신 정보를 검색해서 한국어로 답변해줘.

질문: {query}

형식:
1) 핵심 답변
2) 근거 요약 2~4개
3) 참고 링크(가능하면)
"""

    def _run_vertex_search():
        last_error = None
        # google-genai 버전별 호환을 위해 두 가지 config 형태를 시도
        config_candidates = [
            {"tools": [{"google_search": {}}], "temperature": 0.3, "max_output_tokens": 1024},
            {"temperature": 0.3, "max_output_tokens": 1024},
        ]

        for cfg in config_candidates:
            try:
                response = genai_client.models.generate_content(
                    model=VERTEX_MODEL,
                    contents=prompt,
                    config=cfg,
                )
                text = getattr(response, "text", "") or ""
                if text.strip():
                    return {"answer": text.strip(), "sources": []}, None
            except Exception as e:
                last_error = e
        return None, str(last_error) if last_error else "Vertex 검색 실패"

    return await asyncio.to_thread(_run_vertex_search)


def extract_tool_call_from_text(text: str):
    """LLM 응답에서 {"tool": "..."} 형태의 JSON을 추출"""
    if not text:
        return None

    # 1) ```json ... ``` 코드펜스
    code_fence_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if code_fence_match:
        try:
            return json.loads(code_fence_match.group(1))
        except Exception:
            pass

    # 2) 전체가 JSON 객체인 경우
    try:
        return json.loads(text.strip())
    except Exception:
        pass

    # 3) 응답 안의 단일 JSON 객체 추출
    json_like_match = re.search(r"\{[^{}]*\"tool\"[^{}]*\}", text)
    if json_like_match:
        try:
            return json.loads(json_like_match.group(0))
        except Exception:
            return None

    return None


# 학습된 유저 스타일 저장 (유저ID -> 스타일 데이터)
learned_user_styles = {}

# 현재 활성화된 학습 페르소나
active_learned_persona = None


def _restore_learned_persona():
    """저장된 학습 페르소나를 복원한다.

    예전엔 load_memory()가 복원한 뒤 파일 아래쪽의 `learned_user_styles = {}`가
    다시 덮어써서, 재시작하면 학습목록이 비고 다음 학습 때 저장본까지 날아갔다.
    """
    global learned_user_styles, active_learned_persona, persona_model, current_persona

    learned_user_styles = bot_memory.setdefault('learned_users', {})
    if learned_user_styles:
        print(f"✅ 학습된 유저 {len(learned_user_styles)}명 복원")

    active = bot_memory.get('active_persona')
    if not active or active not in learned_user_styles:
        return
    active_learned_persona = active
    data = learned_user_styles[str(active)]
    current_persona = data.get('persona_instruction', DEFAULT_PERSONA)
    if gemini_model is not None:
        persona_model = build_persona_model(current_persona)
        print(f"✅ 페르소나 복원: {data.get('name', 'Unknown')}")
    else:
        persona_model = None
        print("⚠️ Vertex 비활성 상태라 페르소나 복원을 건너뜀")


CHAT_MODE_PROMPT = """
너는 디스코드 채팅방에 있는 유저 중 하나야.
대화에 자연스럽게 참여해야 해.

최근 대화:
{recent_chat}

다음 지침을 따라:
1. 대화 흐름을 파악하고 자연스럽게 끼어들어
2. 너무 튀지 않게 짧고 자연스럽게 한마디 해
3. 질문에 답하거나, 의견을 말하거나, 리액션을 해
4. 말투는 {style}
5. 1-2문장으로 짧게 답해
6. "ㅋㅋ", "ㄹㅇ", "ㅇㅇ" 같은 표현 자연스럽게 사용 가능
7. 너가 생각했을때 맞장구 쳐야할 거 같은 얘기가 나오면 맞장구 쳐.
8. 지금 끼어들면 어색하거나 할 말이 없으면 다른 말 없이 SKIP 한 단어만 출력해

대화에 자연스럽게 끼어들어봐:
"""

_QUESTION_HINTS = ('?', '뭐', '어떻게', '왜')


class AIChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        _restore_learned_persona()

    @commands.command(name='페르소나')
    async def change_persona(self, ctx, *, new_persona: str = None):
        """봇의 페르소나(성격)를 변경하는 명령어"""
        global persona_model, current_persona, chat_sessions
    
        if not new_persona:
            # 현재 페르소나 표시
            await ctx.send(f"🎭 **현재 페르소나:**\n```{current_persona[:500]}...```\n\n사용법: `.페르소나 [새로운 성격 설명]`")
            return
        if gemini_model is None:
            await ctx.send("❌ Vertex AI 인증이 없어 페르소나 변경을 사용할 수 없어. `GCP_KEY_JSON`을 설정해줘.")
            return
    
        try:
            # 새 페르소나로 모델 재생성
            current_persona = new_persona
            persona_model = build_persona_model(new_persona)
        
            # 모든 대화 세션 리셋
            chat_sessions.clear()
        
            await ctx.send(f"✅ 페르소나가 변경되었어!\n\n🎭 **새 페르소나:**\n```{new_persona[:300]}{'...' if len(new_persona) > 300 else ''}```")
        
        except Exception as e:
            await ctx.send(f"❌ 페르소나 변경 중 오류: {str(e)}")
            print(f"페르소나 변경 오류: {e}")

    @commands.command(name='페르소나리셋')
    async def reset_persona(self, ctx):
        """봇의 페르소나를 기본값으로 리셋하는 명령어"""
        global persona_model, current_persona, chat_sessions
    
        try:
            if gemini_model is None:
                await ctx.send("❌ Vertex AI 인증이 없어 페르소나 리셋을 사용할 수 없어. `GCP_KEY_JSON`을 설정해줘.")
                return
            current_persona = DEFAULT_PERSONA
            persona_model = build_persona_model(DEFAULT_PERSONA)
            chat_sessions.clear()
        
            await ctx.send("✅ 페르소나가 기본값으로 리셋되었어!")
        
        except Exception as e:
            await ctx.send(f"❌ 리셋 중 오류: {str(e)}")

    @commands.command(name='대화리셋')
    async def reset_chat(self, ctx):
        """현재 채널의 AI 대화 기록을 리셋하는 명령어"""
        global chat_sessions
    
        channel_id = ctx.channel.id
        if channel_id in chat_sessions:
            del chat_sessions[channel_id]
            await ctx.send("✅ 이 채널의 대화 기록이 리셋되었어! 새로운 대화를 시작해봐.")
        else:
            await ctx.send("이 채널에는 저장된 대화 기록이 없어.")

    @commands.command(name='ai')
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def ai_chat(self, ctx, *, question: str = None):
        """AI에게 직접 질문하는 명령어 (멘션 없이)"""
        if not question:
            await ctx.send("사용법: `.ai [질문]`\n예시: `.ai 오늘 뭐 먹을까?`")
            return
        if persona_model is None:
            await ctx.send("❌ AI 인증이 설정되지 않았어. Railway 환경변수 `GCP_KEY_JSON`을 확인해줘.")
            return
    
        try:
            channel_id = ctx.channel.id
        
            # 채널별 대화 세션 관리
            if channel_id not in chat_sessions:
                chat_sessions[channel_id] = persona_model.start_chat(history=[])
        
            # (세션 기록은 세션이 알아서 최근 것만 남긴다)
        
            # 기억 컨텍스트 추가
            memory_context = get_memory_context(ctx.author.id)
            # 존댓말 지시 추가
            speech_style = get_speech_style_instruction(ctx.author.id)
            message_with_context = f"{speech_style}{memory_context}[{ctx.author.display_name}의 메시지]: {question}"
        
            # 스트리밍 응답 - 먼저 빈 메시지 보내기
            reply_msg = await ctx.reply("...")
        
            # 스트리밍으로 AI 응답 생성
            ai_response = ""
            last_update = ""
            update_interval = 0.5  # 0.5초마다 업데이트
            last_update_time = time.time()
        
            try:
                async for chunk in ai_stream(chat_sessions[channel_id], message_with_context):
                    if chunk.text:
                        ai_response += chunk.text
                    
                        # 일정 시간마다 메시지 업데이트 (rate limit 방지)
                        current_time = time.time()
                        if current_time - last_update_time >= update_interval and ai_response != last_update:
                            display_text = ai_response[:1500] if len(ai_response) > 1500 else ai_response
                            try:
                                await reply_msg.edit(content=display_text)
                                last_update = ai_response
                                last_update_time = current_time
                            except:
                                pass
            
                # 최종 응답 업데이트
                ai_response = ai_response.strip()
                if len(ai_response) > 1500:
                    ai_response = ai_response[:1500] + "..."
            
                await reply_msg.edit(content=ai_response if ai_response else "...")
            
            except Exception as stream_error:
                print(f"스트리밍 오류: {stream_error}")
                # 스트리밍 실패시 일반 응답으로 폴백
                response = await ai_send(chat_sessions[channel_id], message_with_context)
                ai_response = response.text.strip()
                if len(ai_response) > 1500:
                    ai_response = ai_response[:1500] + "..."
                await reply_msg.edit(content=ai_response)
        
            # 대화 버퍼에 저장 (자동 요약용)
            add_to_conversation_buffer(ctx.author.id, ctx.author.display_name, 'user', question)
            add_to_conversation_buffer(ctx.author.id, ctx.author.display_name, 'bot', ai_response)
        
            # 대화가 일정 수 이상 쌓이면 자동 요약
            user_id_str = str(ctx.author.id)
            if user_id_str in conversation_buffer:
                msg_count = len(conversation_buffer[user_id_str].get('messages', []))
                if msg_count >= SUMMARY_THRESHOLD:
                    await summarize_and_save_conversation(ctx.author.id, ctx.author.display_name)
        
        except Exception as e:
            await ctx.send(f"❌ 오류: {str(e)}")
            print(f"AI 채팅 오류: {e}")

    @commands.command(name='서치챗')
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def search_chat(self, ctx, *, query: str = None):
        """참고 프로젝트 방식: AI JSON 도구호출(web_search) -> 검색 실행 -> 최종 답변"""
        if not query:
            await ctx.send("사용법: `.서치챗 [검색할 내용]`\n예시: `.서치챗 오늘 날씨는 어때?`")
            return
        if persona_model is None and gemini_model is None:
            await ctx.send("❌ AI 인증이 설정되지 않았어. Railway 환경변수 `GCP_KEY_JSON`을 먼저 설정해줘.")
            return
    
        try:
            search_msg = await ctx.reply("🧠 검색 계획 생성 중...")

            # 1) AI에게 web_search 도구호출 JSON 생성 요청 (virtual_assistant 방식 이식)
            planner_prompt = f"""
너는 도구 라우터야.
사용자 요청을 웹 검색용 JSON으로 변환해.

규칙:
- 반드시 JSON 한 개만 출력
- 형식: {{"tool":"web_search","input":"검색어"}}
- tool 값은 반드시 web_search
- input은 검색엔진에서 바로 쓸 짧고 정확한 검색어

사용자 요청: {query}
"""

            tool_call = None
            try:
                planner_model = gemini_model or persona_model
                planner_response = await ai_generate(planner_model, planner_prompt)
                planner_text = (planner_response.text or "").strip()
                tool_call = extract_tool_call_from_text(planner_text)
            except Exception as planner_error:
                print(f"서치챗 도구 라우팅 실패(폴백): {planner_error}")

            # 파싱 실패 시 안전 폴백
            if not tool_call or tool_call.get("tool") != "web_search":
                tool_call = {"tool": "web_search", "input": query}

            search_query = str(tool_call.get("input") or query).strip()
            if not search_query:
                search_query = query

            await search_msg.edit(content=f"🔍 검색 중... (`{search_query}`)")

            # 2) Vertex 검색 우선
            vertex_result, vertex_error = await search_with_vertex(search_query)
            ai_response = ""
            if vertex_result and vertex_result.get("answer"):
                ai_response = vertex_result["answer"].strip()
                print(f"✅ 서치챗 Vertex 검색 사용: {search_query}")
            else:
                print(f"⚠️ 서치챗 Vertex 검색 실패, Custom Search 폴백: {vertex_error}")
                await search_msg.edit(content=f"🔄 Vertex 검색 실패, 웹 검색으로 폴백 중... (`{search_query}`)")

                # 3) 폴백: Custom Search
                search_results, error = await google_search(search_query, num_results=5)
                if error:
                    await search_msg.edit(content=f"❌ {error}")
                    return
                if not search_results:
                    await search_msg.edit(content="❌ 검색 결과를 찾을 수 없습니다.")
                    return

                search_context = "웹 검색 결과:\n\n"
                for i, result in enumerate(search_results, 1):
                    search_context += f"[{i}] {result['title']}\n"
                    search_context += f"내용: {result['snippet']}\n"
                    search_context += f"링크: {result['link']}\n\n"

                tool_result = {
                    "success": True,
                    "tool": "web_search",
                    "query": search_query,
                    "results": search_results
                }

                memory_context = get_memory_context(ctx.author.id)
                speech_style = get_speech_style_instruction(ctx.author.id)
                prompt = f"""{speech_style}{memory_context}
다음은 도구 실행 결과야:
{json.dumps(tool_result, ensure_ascii=False, indent=2)}

사용자 원문 질문: {query}
실제 검색어: {search_query}

{search_context}

지시:
- 검색 결과를 바탕으로 핵심 답변 먼저 제시
- 중요한 근거를 2~4개 포인트로 짧게 정리
- 불확실하면 단정하지 말고 그렇게 명시
- 마지막에 참고 링크를 최대 3개만 붙여
"""
                await search_msg.edit(content="🤖 AI가 답변 생성 중...")

                channel_id = ctx.channel.id
                if channel_id not in chat_sessions:
                    chat_sessions[channel_id] = persona_model.start_chat(history=[])

                response = await ai_send(chat_sessions[channel_id], prompt)
                ai_response = response.text.strip()
        
            if len(ai_response) > 1900:
                ai_response = ai_response[:1900] + "..."
        
            await search_msg.edit(content=ai_response)
        
            # 대화 버퍼에 저장
            add_to_conversation_buffer(ctx.author.id, ctx.author.display_name, 'user', f"[검색] {query}")
            add_to_conversation_buffer(ctx.author.id, ctx.author.display_name, 'bot', ai_response)
        
        except Exception as e:
            await ctx.send(f"❌ 오류: {str(e)}")
            print(f"서치챗 오류: {e}")

    @commands.command(name='학습')
    @commands.cooldown(1, 120, commands.BucketType.guild)
    async def learn_user_style(self, ctx, target_user: discord.Member = None):
        """특정 유저의 채팅 스타일을 학습하는 명령어"""
        global learned_user_styles, persona_model, current_persona, chat_sessions, active_learned_persona
    
        if not target_user:
            await ctx.send("📚 **사용법:** `.학습 @유저`\n해당 유저의 최근 채팅을 분석해서 말투를 학습해요.")
            return
        if gemini_model is None:
            await ctx.send("❌ Vertex AI 인증이 없어 학습 기능을 사용할 수 없어. `GCP_KEY_JSON`을 설정해줘.")
            return
    
        try:
            loading_msg = await ctx.send(f"🔍 **{target_user.display_name}**의 채팅 스타일 분석 중... (메시지 수집 중)")
        
            # 해당 유저의 메시지 수집 (모든 텍스트 채널을 병렬로 훑는다)
            async def _collect_user_messages(channel):
                found = []
                async for message in channel.history(limit=500):
                    if message.author.id != target_user.id:
                        continue
                    if not message.content or message.content.startswith('.'):
                        continue
                    # 너무 짧거나 링크만 있는 메시지 제외
                    if len(message.content) > 3 and not message.content.startswith('http'):
                        found.append(message.content)
                        if len(found) >= 150:
                            break
                return found

            messages = []
            for found in await scan_channels(ctx.guild, ctx.guild.me, _collect_user_messages):
                messages.extend(found)
            messages = messages[:150]
        
            if len(messages) < 15:
                await loading_msg.edit(content=f"❌ **{target_user.display_name}**의 메시지가 부족해요. (최소 15개 필요, 현재 {len(messages)}개)")
                return
        
            await loading_msg.edit(content=f"🤖 **{target_user.display_name}**의 스타일 분석 중... ({len(messages)}개 메시지 분석)")
        
            # 분석할 텍스트 준비
            analysis_text = "\n".join(messages[:80])
        
            # Gemini AI로 스타일 분석
            analysis_prompt = f"""
다음은 Discord 서버에서 '{target_user.display_name}'라는 유저가 작성한 채팅 메시지들이야.
이 사람의 채팅 스타일을 완벽하게 분석해서 정리해줘.

분석할 메시지들:
{analysis_text}

다음 항목들을 아주 자세히 분석해줘:
1. **말투와 어조**: 존댓말/반말, 거친 정도, 유머 스타일
2. **자주 쓰는 표현**: 특징적인 단어, 이모티콘, 줄임말 (ㅋㅋ, ㅎㅎ, ㄹㅇ 등), 입버릇
3. **문장 구조**: 평균 길이, 띄어쓰기 습관, 문장 끝맺음 방식
4. **특이한 점**: 오타 패턴, 특이한 표현, 유행어 사용
5. **성격**: 채팅에서 드러나는 성격적 특성

구체적인 예시를 포함해서 분석해줘.
"""
        
            response = await ai_generate(gemini_model, analysis_prompt)
            style_analysis = response.text
        
            # 페르소나 인스트럭션 생성
            persona_prompt = f"""
다음 분석 결과를 바탕으로, AI가 이 사람처럼 대화할 수 있는 system instruction을 만들어줘.

분석 결과:
{style_analysis}

실제 메시지 예시:
{chr(10).join(messages[:15])}

다음 형식으로 system instruction을 작성해줘:
- "너는 {target_user.display_name}처럼 말해야 해"로 시작
- 말투, 자주 쓰는 표현, 성격을 구체적으로 명시
- 절대 "AI입니다"라고 말하지 않도록 지시
- 최대한 자연스럽게 그 사람처럼 행동하도록 지시
- 디스코드 채팅이니까 1~3줄로 짧게 말하라고 반드시 명시
- 설명체나 장문, 목록 서식을 쓰지 말라고 반드시 명시

system instruction은 800자 안쪽으로, 그것만 출력해 (다른 설명 없이):
"""
        
            persona_response = await ai_generate(gemini_model, persona_prompt)
            generated_persona = persona_response.text.strip()
        
            # 학습 데이터 저장 (문자열 키로 저장 - JSON 호환)
            user_id_str = str(target_user.id)
            learned_user_styles[user_id_str] = {
                'name': target_user.display_name,
                'user_id': target_user.id,
                'style_analysis': style_analysis,
                'persona_instruction': generated_persona,
                'sample_messages': messages[:20],
                'message_count': len(messages)
            }
        
            # 장기기억에 저장
            bot_memory['learned_users'] = learned_user_styles
            bot_memory['active_persona'] = user_id_str
            save_memory(force=True)
        
            # 바로 이 페르소나를 활성화
            current_persona = generated_persona
            persona_model = build_persona_model(generated_persona)
            chat_sessions.clear()
            active_learned_persona = user_id_str
        
            result_text = f"""✅ **{target_user.display_name}** 학습 완료! ({len(messages)}개 메시지 분석)

🎭 이제 봇을 멘션하거나 `.ai` 명령어를 사용하면 **{target_user.display_name}**처럼 대답해요!

💡 `.말투분석 @{target_user.display_name}` 으로 분석 결과를 볼 수 있어요."""
        
            await loading_msg.edit(content=result_text)
        
        except Exception as e:
            await ctx.send(f"❌ 학습 중 오류: {str(e)}")
            print(f"학습 오류: {e}")

    @commands.command(name='학습목록')
    async def list_learned_users(self, ctx):
        """학습된 유저 목록을 보여주는 명령어"""
        global learned_user_styles, active_learned_persona
    
        if not learned_user_styles:
            await ctx.send("📚 아직 학습된 유저가 없어요. `.학습 @유저`로 학습시켜보세요!")
            return
    
        result = "📚 **학습된 유저 목록**\n\n"
    
        for user_id, data in learned_user_styles.items():
            is_active = "✅ 활성화" if active_learned_persona == user_id else ""
            result += f"• **{data['name']}** - {data['message_count']}개 메시지 분석 {is_active}\n"
    
        result += f"\n💡 `.학습적용 @유저`로 학습된 페르소나를 활성화할 수 있어요."
    
        await ctx.send(result)

    @commands.command(name='학습적용')
    async def apply_learned_persona(self, ctx, target_user: discord.Member = None):
        """학습된 유저의 페르소나를 적용하는 명령어"""
        global learned_user_styles, persona_model, current_persona, chat_sessions, active_learned_persona
    
        if not target_user:
            await ctx.send("📚 **사용법:** `.학습적용 @유저`")
            return
        if gemini_model is None:
            await ctx.send("❌ Vertex AI 인증이 없어 학습 페르소나 적용이 불가능해. `GCP_KEY_JSON`을 설정해줘.")
            return
    
        user_id_str = str(target_user.id)
        if user_id_str not in learned_user_styles:
            await ctx.send(f"❌ **{target_user.display_name}**은(는) 아직 학습되지 않았어요. `.학습 @유저`로 먼저 학습시켜주세요.")
            return
    
        try:
            data = learned_user_styles[user_id_str]
        
            current_persona = data['persona_instruction']
            persona_model = build_persona_model(data['persona_instruction'])
            chat_sessions.clear()
            active_learned_persona = user_id_str
        
            # 메모리에도 저장
            bot_memory['active_persona'] = user_id_str
            save_memory(force=True)
        
            await ctx.send(f"✅ **{data['name']}** 페르소나가 적용되었어요!\n이제 봇이 {data['name']}처럼 대답해요.")
        
        except Exception as e:
            await ctx.send(f"❌ 적용 중 오류: {str(e)}")

    @commands.command(name='학습삭제')
    async def delete_learned_user(self, ctx, target_user: discord.Member = None):
        """학습된 유저 데이터를 삭제하는 명령어"""
        global learned_user_styles, active_learned_persona
    
        if not target_user:
            await ctx.send("📚 **사용법:** `.학습삭제 @유저`")
            return
    
        user_id_str = str(target_user.id)
        if user_id_str not in learned_user_styles:
            await ctx.send(f"❌ **{target_user.display_name}**은(는) 학습된 기록이 없어요.")
            return
    
        name = learned_user_styles[user_id_str]['name']
        del learned_user_styles[user_id_str]
    
        if active_learned_persona == user_id_str:
            active_learned_persona = None
    
        # 메모리에서도 삭제
        if user_id_str in bot_memory['learned_users']:
            del bot_memory['learned_users'][user_id_str]
        if bot_memory['active_persona'] == user_id_str:
            bot_memory['active_persona'] = None
        save_memory(force=True)
    
        await ctx.send(f"✅ **{name}**의 학습 데이터가 삭제되었어요.")

    @commands.command(name='말투분석')
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def analyze_style_only(self, ctx, target_user: discord.Member = None):
        """유저의 말투만 분석해서 보여주는 명령어 (학습하지 않음)"""
        if not target_user:
            await ctx.send("📝 **사용법:** `.말투분석 @유저`")
            return
        if gemini_model is None:
            await ctx.send("❌ Vertex AI 인증이 없어 말투 분석을 사용할 수 없어. `GCP_KEY_JSON`을 설정해줘.")
            return
    
        try:
            loading_msg = await ctx.send(f"🔍 **{target_user.display_name}**의 말투 분석 중...")
        
            # 메시지 수집 (모든 텍스트 채널을 병렬로 훑는다)
            async def _collect_user_messages(channel):
                found = []
                async for message in channel.history(limit=300):
                    if message.author.id != target_user.id:
                        continue
                    if not message.content or message.content.startswith('.'):
                        continue
                    if len(message.content) > 3:
                        found.append(message.content)
                        if len(found) >= 50:
                            break
                return found

            messages = []
            for found in await scan_channels(ctx.guild, ctx.guild.me, _collect_user_messages):
                messages.extend(found)
            messages = messages[:50]
        
            if len(messages) < 10:
                await loading_msg.edit(content=f"❌ 메시지가 부족해요. (최소 10개 필요, 현재 {len(messages)}개)")
                return
        
            analysis_text = "\n".join(messages[:40])
        
            prompt = f"""
'{target_user.display_name}'의 채팅 메시지를 분석해서 재미있고 솔직하게 말투 특징을 정리해줘.

메시지들:
{analysis_text}

다음 형식으로 분석해줘:

📝 **{target_user.display_name}의 말투 분석**

🗣️ **말투 스타일:**
[거친 정도, 존댓말/반말, 톤 분석]

💬 **자주 쓰는 표현:**
[특징적인 단어, 이모티콘, 줄임말 목록]

✨ **특이한 점:**
[독특한 습관이나 패턴]

🎭 **말투에서 보이는 성격:**
[채팅에서 드러나는 성격]

재미있게 분석해줘!
"""
        
            response = await ai_generate(gemini_model, prompt)
        
            await loading_msg.edit(content=response.text[:1900])
        
        except Exception as e:
            await ctx.send(f"❌ 분석 중 오류: {str(e)}")

    @commands.command(name='대화모드')
    async def chat_mode_toggle(self, ctx, mode: str = None):
        """자연스러운 대화 참여 모드를 켜거나 끄는 명령어"""
        global natural_chat_mode, chat_mode_message_buffer, chat_mode_last_response, CHAT_MODE_RESPONSE_CHANCE
    
        channel_id = ctx.channel.id
    
        if mode is None:
            # 현재 상태 표시
            is_active = natural_chat_mode.get(channel_id, False)
            status = "켜짐 ✅" if is_active else "꺼짐 ❌"
        
            # 학습된 페르소나 정보
            persona_info = ""
            if active_learned_persona and active_learned_persona in learned_user_styles:
                persona_info = f"\n🎭 현재 페르소나: **{learned_user_styles[active_learned_persona]['name']}**"
        
            await ctx.send(f"""💬 **대화모드 상태:** {status}{persona_info}

**사용법:**
`.대화모드 on` - 봇이 자연스럽게 대화에 참여
`.대화모드 off` - 대화 참여 중지
`.대화모드 확률 [0-100]` - 응답 확률 조절 (현재: {int(CHAT_MODE_RESPONSE_CHANCE * 100)}%)

💡 대화모드가 켜지면 봇이 대화를 보다가 적절한 타이밍에 자연스럽게 끼어들어요!""")
            return
    
        if mode.lower() == "on":
            natural_chat_mode[channel_id] = True
            chat_mode_message_buffer[channel_id] = []
            chat_mode_last_response[channel_id] = 0
        
            # 페르소나 정보
            persona_msg = ""
            if active_learned_persona and active_learned_persona in learned_user_styles:
                persona_msg = f"\n🎭 **{learned_user_styles[active_learned_persona]['name']}** 스타일로 대화할게!"
        
            await ctx.send(f"""✅ **대화모드 ON!**{persona_msg}

이제 대화를 지켜보다가 적절한 타이밍에 자연스럽게 끼어들게!
- 질문이 있으면 답해줄게
- 재밌는 얘기엔 리액션할게
- 너무 자주 끼어들진 않을게 ㅋㅋ

끄려면 `.대화모드 off`""")
        
        elif mode.lower() == "off":
            if not natural_chat_mode.get(channel_id, False):
                await ctx.send("❌ 이 채널에서 대화모드가 켜져있지 않아!")
                return
        
            natural_chat_mode[channel_id] = False
            if channel_id in chat_mode_message_buffer:
                del chat_mode_message_buffer[channel_id]
            if channel_id in chat_mode_last_response:
                del chat_mode_last_response[channel_id]
            
            await ctx.send("✅ **대화모드 OFF!** 이제 멘션해야 대답할게.")
    
        elif mode.lower() == "확률":
            await ctx.send("❌ 사용법: `.대화모드 확률 [0-100]`\n예: `.대화모드 확률 50`")
        
        else:
            # 확률 설정 시도
            try:
                probability = int(mode)
                if 0 <= probability <= 100:
                    CHAT_MODE_RESPONSE_CHANCE = probability / 100
                    await ctx.send(f"✅ 대화모드 응답 확률이 **{probability}%**로 설정되었어!")
                else:
                    await ctx.send("❌ 확률은 0-100 사이로 입력해줘!")
            except ValueError:
                await ctx.send("❌ 사용법: `.대화모드 on` / `.대화모드 off` / `.대화모드 [확률]`")
    @commands.Cog.listener('on_message')
    async def on_mention(self, message: discord.Message):
        """봇을 멘션하면 페르소나로 대답한다."""
        if message.author == self.bot.user or message.content.startswith('.'):
            return
        if not is_bot_mentioned(self.bot, message):
            return

        user_message = strip_bot_mention(self.bot, message.content)
        if not user_message:
            await message.reply("뭐? 부른 거야?")
            return
        if persona_model is None:
            await message.reply("지금 AI 인증 설정이 안 돼서 응답이 어려워. 관리자한테 GCP_KEY_JSON 설정해달라고 해줘.")
            return

        try:
            channel_id = message.channel.id
            if channel_id not in chat_sessions:
                chat_sessions[channel_id] = persona_model.start_chat(history=[])

            memory_context = get_memory_context(message.author.id)
            speech_style = get_speech_style_instruction(message.author.id)
            prompt = f"{speech_style}{memory_context}[{message.author.display_name}의 메시지]: {user_message}"

            ai_response = await _stream_ai_reply(message, chat_sessions[channel_id], prompt)

            if ai_response:
                author_id, author_name = message.author.id, message.author.display_name
                add_to_conversation_buffer(author_id, author_name, 'user', user_message)
                add_to_conversation_buffer(author_id, author_name, 'bot', ai_response)
                buffered = conversation_buffer.get(str(author_id), {}).get('messages', [])
                if len(buffered) >= SUMMARY_THRESHOLD:
                    await summarize_and_save_conversation(author_id, author_name)

        except Exception as e:
            print(f"AI 응답 오류: {e}")
            await message.reply("어... 뭔가 오류났는데 다시 말해봐")

    @commands.Cog.listener('on_message')
    async def on_chat_mode(self, message: discord.Message):
        """대화모드가 켜진 채널에서 가끔 자연스럽게 끼어든다."""
        if message.author == self.bot.user or message.content.startswith('.'):
            return
        if is_bot_mentioned(self.bot, message):
            return
        channel_id = message.channel.id
        if not natural_chat_mode.get(channel_id):
            return

        buffer = chat_mode_message_buffer.setdefault(channel_id, [])
        buffer.append({
            'author': message.author.display_name,
            'content': message.content,
            'time': message.created_at.strftime("%H:%M"),
        })
        del buffer[:-20]  # 최근 20개만 유지

        chat_mode_last_response[channel_id] = chat_mode_last_response.get(channel_id, 0) + 1
        since_last = chat_mode_last_response[channel_id]

        # 최소 간격이 지나야 응답을 고려하고, 질문이거나 메시지가 많이 쌓이면 확률을 높인다
        if since_last < CHAT_MODE_MIN_INTERVAL or len(message.content.strip()) <= 2:
            return
        should_respond = random.random() < CHAT_MODE_RESPONSE_CHANCE
        if any(hint in message.content for hint in _QUESTION_HINTS) and random.random() < 0.5:
            should_respond = True
        if since_last >= 8 and random.random() < 0.6:
            should_respond = True
        if not should_respond or persona_model is None:
            return

        recent_chat = "\n".join(f"{m['author']}: {m['content']}" for m in buffer[-10:])
        style = current_persona[:200] if current_persona else "반말로 친근하게"
        prompt = CHAT_MODE_PROMPT.format(recent_chat=recent_chat, style=style)

        try:
            # 1-2문장짜리라 스트리밍 없이 받는다. 예전처럼 "..."을 먼저 보냈다가
            # SKIP이면 지우는 식으로 하면 채팅방에 깜빡임이 남는다.
            response = await ai_send(persona_model.start_chat(history=[]), prompt)
            ai_response = (response.text or "").strip()
        except Exception as e:
            print(f"대화모드 응답 오류: {e}")
            return

        if len(ai_response) < 2 or "SKIP" in ai_response.upper():
            return
        await message.channel.send(ai_response[:300])
        chat_mode_last_response[channel_id] = 0


async def setup(bot: commands.Bot):
    await bot.add_cog(AIChat(bot))
