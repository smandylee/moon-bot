import discord
from discord.ext import commands
import random
import os
import base64
from dotenv import load_dotenv
import openai
import datetime
from typing import Optional
import json
import re
import asyncio
import threading
import queue
import time
import shlex
import aiohttp
import traceback
from urllib.parse import urlparse
from types import SimpleNamespace

# Gemini( Vertex AI 모드 ) 설정
try:
    from google import genai
except Exception:
    genai = None

# PR Expected Values 로드
try:
    with open('pr.json', 'r', encoding='utf-8') as f:
        pr_data = json.load(f)
        PR_EXPECTED_VALUES = pr_data.get('data', {})
    print(f"✅ PR 기댓값 데이터 로드 완료: {len(PR_EXPECTED_VALUES)}개 함선")
except Exception as e:
    print(f"⚠️ PR 기댓값 데이터 로드 실패: {e}")
    PR_EXPECTED_VALUES = {}


# .env 파일에서 환경변수 로드 (파일이 없어도 오류 발생하지 않음)
try:
    load_dotenv()
except Exception as e:
    print(f"⚠️ .env 파일 로드 실패: {e}")
    print("환경변수를 직접 설정하거나 .env 파일을 확인해주세요.")

# OpenAI API 설정
openai.api_key = os.getenv('OPENAI_API_KEY', 'your_openai_api_key_here')

# Vertex AI 초기화 (google-genai SDK, Vertex 모드)
GCP_PROJECT_ID = "alphavertex-486307"
GCP_LOCATION = "global"  # Gemini 3 Flash Preview 권장
VERTEX_MODEL = "gemini-3-flash-preview"  # Gemini 3 Flash

# 서비스 계정 키 파일 경로 설정
GCP_KEY_FILE = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'gcp-key.json')
HAS_GCP_CREDENTIALS = False

if os.path.exists(GCP_KEY_FILE):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GCP_KEY_FILE
    print(f"✅ GCP 서비스 계정 키 로드: {GCP_KEY_FILE}")
    HAS_GCP_CREDENTIALS = True
else:
    # Railway 등 서버 환경에서는 환경변수로 처리
    gcp_key_json = os.getenv('GCP_KEY_JSON')
    if gcp_key_json:
        try:
            normalized_key = gcp_key_json.strip()
            # Base64로 들어온 경우도 지원
            if not normalized_key.startswith("{"):
                try:
                    normalized_key = base64.b64decode(normalized_key).decode("utf-8")
                except Exception:
                    pass

            key_obj = json.loads(normalized_key)
            key_file_path = '/tmp/gcp-key.json'
            with open(key_file_path, 'w', encoding='utf-8') as f:
                json.dump(key_obj, f, ensure_ascii=False)
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = key_file_path
            print("✅ GCP 서비스 계정 키 로드 (환경변수)")
            HAS_GCP_CREDENTIALS = True
        except Exception as key_error:
            print(f"❌ GCP_KEY_JSON 파싱 실패: {key_error}")
    else:
        print("⚠️ GCP 서비스 계정 키를 찾을 수 없습니다.")

class _CompatResponse:
    def __init__(self, text: str):
        self.text = text or ""


class _CompatChunk:
    def __init__(self, text: str):
        self.text = text or ""


class _CompatChatSession:
    def __init__(self, model):
        self._model = model
        self.history = []

    def send_message(self, message: str, stream: bool = False):
        if not stream:
            response = self._model.generate_content(message)
            self.history.append({"role": "user", "text": message})
            self.history.append({"role": "model", "text": response.text})
            return response

        def _stream_gen():
            full_text = ""
            try:
                prompt = self._model._build_prompt_with_history(message, self.history)
                response_stream = self._model._client.models.generate_content_stream(
                    model=self._model.model_name,
                    contents=prompt,
                )
                for chunk in response_stream:
                    chunk_text = getattr(chunk, "text", "") or ""
                    if chunk_text:
                        full_text += chunk_text
                        yield _CompatChunk(chunk_text)
            finally:
                self.history.append({"role": "user", "text": message})
                self.history.append({"role": "model", "text": full_text})

        return _stream_gen()


class GenerativeModel:
    def __init__(self, model_name: str, system_instruction=None, client=None):
        self.model_name = model_name
        self._client = client
        if isinstance(system_instruction, list):
            self.system_instruction = "\n".join([str(s) for s in system_instruction if s])
        else:
            self.system_instruction = str(system_instruction or "")

    def _build_prompt_with_history(self, prompt: str, history=None) -> str:
        chunks = []
        if self.system_instruction:
            chunks.append(f"[System]\n{self.system_instruction}")
        if history:
            hist = history[-20:]
            lines = []
            for item in hist:
                role = item.get("role", "user")
                text = item.get("text", "")
                if text:
                    lines.append(f"{role}: {text}")
            if lines:
                chunks.append("[History]\n" + "\n".join(lines))
        chunks.append(f"[User]\n{prompt}")
        return "\n\n".join(chunks)

    def generate_content(self, prompt: str):
        if not self._client:
            raise RuntimeError("AI client is not initialized")
        full_prompt = self._build_prompt_with_history(prompt)
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=full_prompt,
        )
        return _CompatResponse(getattr(response, "text", ""))

    def start_chat(self, history=None):
        session = _CompatChatSession(self)
        if history:
            session.history = list(history)
        return session


genai_client = None
if HAS_GCP_CREDENTIALS and genai is not None:
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=GCP_PROJECT_ID,
            location=GCP_LOCATION,
        )
        gemini_model = GenerativeModel(VERTEX_MODEL, client=genai_client)
        print(f"✅ Vertex AI 초기화 완료 (google-genai, 프로젝트: {GCP_PROJECT_ID}, 리전: {GCP_LOCATION})")
    except Exception as e:
        print(f"❌ Vertex AI 초기화 실패: {e}")
        gemini_model = None
else:
    if genai is None:
        print("⚠️ google-genai 패키지를 찾지 못해 Vertex AI를 비활성화합니다.")
    else:
        print("⚠️ Vertex AI 비활성화: GCP 인증 정보가 없습니다.")
    gemini_model = None

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

# 페르소나 모델 생성 (Vertex AI)
persona_model = None
if gemini_model is not None:
    persona_model = GenerativeModel(
        VERTEX_MODEL,
        system_instruction=[DEFAULT_PERSONA],
        client=genai_client,
    )

# 채널별 대화 세션 관리
chat_sessions = {}

# 현재 페르소나 저장
current_persona = DEFAULT_PERSONA

# ==================== 장기기억 시스템 ====================
MEMORY_FILE = 'bot_memory.json'

# 메모리 데이터 구조
bot_memory = {
    'learned_users': {},      # 학습된 유저 스타일
    'active_persona': None,   # 현재 활성화된 페르소나 유저 ID
    'user_memories': {},      # 유저별 기억 {user_id: [{fact, timestamp}, ...]}
    'server_facts': [],       # 서버 관련 기억
    'conversation_summaries': {}  # 채널별 대화 요약
}

def save_memory():
    """메모리를 파일에 저장"""
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(bot_memory, f, ensure_ascii=False, indent=2)
        print("💾 메모리 저장 완료")
    except Exception as e:
        print(f"❌ 메모리 저장 실패: {e}")

def load_memory():
    """파일에서 메모리 로드"""
    global bot_memory, learned_user_styles, active_learned_persona, persona_model, current_persona
    
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                bot_memory.update(loaded)
            
            # 학습된 유저 스타일 복원
            if bot_memory.get('learned_users'):
                learned_user_styles = bot_memory['learned_users']
                print(f"✅ 학습된 유저 {len(learned_user_styles)}명 복원")
            
            # 활성화된 페르소나 복원
            if bot_memory.get('active_persona') and bot_memory['active_persona'] in learned_user_styles:
                active_learned_persona = bot_memory['active_persona']
                data = learned_user_styles[str(active_learned_persona)]
                current_persona = data.get('persona_instruction', DEFAULT_PERSONA)
                if gemini_model is not None:
                    persona_model = GenerativeModel(
                        VERTEX_MODEL,
                        system_instruction=[current_persona],
                        client=genai_client,
                    )
                    print(f"✅ 페르소나 복원: {data.get('name', 'Unknown')}")
                else:
                    persona_model = None
                    print("⚠️ Vertex 비활성 상태라 페르소나 복원을 건너뜀")
            
            print(f"✅ 메모리 로드 완료")
        else:
            print("📝 메모리 파일 없음, 새로 시작")
    except Exception as e:
        print(f"❌ 메모리 로드 실패: {e}")

def add_user_memory(user_id: int, user_name: str, fact: str):
    """유저에 대한 기억 추가"""
    user_id_str = str(user_id)
    if user_id_str not in bot_memory['user_memories']:
        bot_memory['user_memories'][user_id_str] = {'name': user_name, 'facts': []}
    
    bot_memory['user_memories'][user_id_str]['facts'].append({
        'fact': fact,
        'timestamp': datetime.datetime.now().isoformat()
    })
    
    # 최대 50개 기억만 유지
    if len(bot_memory['user_memories'][user_id_str]['facts']) > 50:
        bot_memory['user_memories'][user_id_str]['facts'] = bot_memory['user_memories'][user_id_str]['facts'][-50:]
    
    save_memory()

def get_user_memories(user_id: int) -> list:
    """유저에 대한 기억 가져오기"""
    user_id_str = str(user_id)
    if user_id_str in bot_memory['user_memories']:
        return bot_memory['user_memories'][user_id_str].get('facts', [])
    return []

def get_memory_context(user_id: int) -> str:
    """대화에 사용할 기억 컨텍스트 생성"""
    memories = get_user_memories(user_id)
    if not memories:
        return ""
    
    recent_memories = memories[-10:]  # 최근 10개만
    memory_text = "\n".join([f"- {m['fact']}" for m in recent_memories])
    return f"\n[이 유저에 대해 기억하는 것들]\n{memory_text}\n"

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
        
        response = gemini_model.generate_content(summary_prompt)
        summary = response.text.strip()
        
        # "없음"이 아니면 저장
        if summary and summary != "없음" and len(summary) > 5:
            add_user_memory(user_id, user_name, f"[대화 요약] {summary}")
            print(f"💾 {user_name}과의 대화 요약 저장: {summary[:50]}...")
        
        # 버퍼 비우기
        conversation_buffer[user_id_str]['messages'] = []
        
    except Exception as e:
        print(f"대화 요약 오류: {e}")

# 메모리 로드 실행
load_memory()

# ==================== 장기기억 시스템 끝 ====================

def get_speech_style_instruction(user_id: int) -> str:
    """유저별 존댓말 예외 규칙 비활성화"""
    return ""

# Wargaming API 설정
WARGAMING_API_KEY = os.getenv('WARGAMING_API_KEY', 'your_wargaming_api_key_here')
WOWS_API_REGIONS = {
    'na': 'https://api.worldofwarships.com',
    'eu': 'https://api.worldofwarships.eu',
    'asia': 'https://api.worldofwarships.asia',
    'ru': 'https://api.worldofwarships.ru'
}
WOWS_API_BASE_URL = WOWS_API_REGIONS['na']  # 기본값: NA 서버

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True  # 권한 활성화
intents.guilds = True
intents.messages = True
intents.members = True  # 멤버 목록 보기 권한 활성화
bot = commands.Bot(command_prefix='.', intents=intents)

# 봇 초기화 완료
print("🤖 Moon Bot 초기화 완료")

# 터미널 입력 관련 전역 변수
terminal_message_queue = queue.Queue()
terminal_input_active = False
terminal_channel_id = None

def terminal_command_handler():
    """터미널에서 봇 명령어를 입력받는 함수"""
    global terminal_input_active, terminal_channel_id
    
    print("💻 터미널 명령어 모드가 활성화되었습니다.")
    print("사용 가능한 명령어:")
    print("  - 'terminal on': 터미널 입력 모드 활성화")
    print("  - 'terminal off': 터미널 입력 모드 비활성화")
    print("  - 'dm': 특정 유저에게 DM 전송")
    print("  - 'quit': 봇 종료")
    print("  - 'help': 도움말 표시")
    
    while True:
        try:
            command = input("봇 명령어> ").strip().lower()
            
            if command == 'terminal on':
                if terminal_input_active:
                    print("❌ 이미 터미널 입력 모드가 활성화되어 있습니다!")
                    continue
                
                # 서버와 채널 선택
                if bot.guilds:
                    guild = bot.guilds[0]
                    text_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]
                    
                    if text_channels:
                        print(f"\n📋 사용 가능한 채널 목록:")
                        for i, channel in enumerate(text_channels, 1):
                            channel_type = "📢 공지" if channel.type == discord.ChannelType.news else "💬 채팅"
                            print(f"  {i}. {channel.name} ({channel_type})")
                        
                        # 채널 선택
                        while True:
                            try:
                                choice = input(f"\n채널 번호를 선택하세요 (1-{len(text_channels)}): ").strip()
                                if choice.isdigit():
                                    channel_index = int(choice) - 1
                                    if 0 <= channel_index < len(text_channels):
                                        selected_channel = text_channels[channel_index]
                                        terminal_channel_id = selected_channel.id
                                        terminal_input_active = True
                                        
                                        channel_type = "📢 공지" if selected_channel.type == discord.ChannelType.news else "💬 채팅"
                                        print(f"\n✅ 터미널 입력 모드가 활성화되었습니다!")
                                        print(f"📡 메시지가 전송될 채널: {selected_channel.name} ({channel_type})")
                                        print("💬 이제 메시지를 입력하세요 (종료하려면 'quit' 입력):")
                                        
                                        # 터미널 입력 스레드 시작
                                        terminal_thread = threading.Thread(target=terminal_input_handler, daemon=True)
                                        terminal_thread.start()
                                        
                                        # 터미널 입력 모드가 활성화된 동안 명령어 입력 루프 일시 중지
                                        while terminal_input_active:
                                            time.sleep(0.1)
                                        
                                        print("🔄 터미널 입력 모드가 종료되었습니다. 명령어 모드로 돌아갑니다.")
                                        break
                                    else:
                                        print(f"❌ 1-{len(text_channels)} 사이의 번호를 입력해주세요.")
                                else:
                                    print("❌ 숫자를 입력해주세요.")
                            except (EOFError, KeyboardInterrupt):
                                print("\n❌ 채널 선택이 취소되었습니다.")
                                break
                    else:
                        print("❌ 텍스트 채널을 찾을 수 없습니다!")
                else:
                    print("❌ 봇이 서버에 연결되지 않았습니다!")
                    
            elif command == 'terminal off':
                if not terminal_input_active:
                    print("❌ 현재 터미널 입력 모드가 켜져있지 않습니다!")
                    continue
                
                terminal_input_active = False
                terminal_channel_id = None
                print("✅ 터미널 입력 모드가 비활성화되었습니다.")
                
            elif command == 'quit':
                print("🛑 봇을 종료합니다...")
                # 봇 종료를 위한 이벤트 루프 중단
                asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
                break
                
            elif command == 'dm':
                # DM 전송 모드
                if bot.guilds:
                    guild = bot.guilds[0]
                    members = [m for m in guild.members if not m.bot]
                    
                    if members:
                        print(f"\n📋 DM 전송 가능한 유저 목록:")
                        for i, member in enumerate(members, 1):
                            print(f"  {i}. {member.name} ({member.display_name})")
                        
                        # 유저 선택
                        try:
                            choice = input(f"\n유저 번호를 선택하세요 (1-{len(members)}): ").strip()
                            if choice.isdigit():
                                user_index = int(choice) - 1
                                if 0 <= user_index < len(members):
                                    selected_user = members[user_index]
                                    print(f"\n✅ {selected_user.display_name}에게 DM 전송 모드")
                                    print("💬 메시지를 입력하세요 (종료하려면 'exit' 입력):")
                                    
                                    # DM 전송 루프
                                    while True:
                                        try:
                                            dm_message = input("DM> ").strip()
                                            if dm_message.lower() == 'exit':
                                                print("📤 DM 전송 모드 종료")
                                                break
                                            if dm_message:
                                                # DM 전송
                                                async def send_dm():
                                                    try:
                                                        await selected_user.send(dm_message)
                                                        print(f"✅ DM 전송 완료: {dm_message[:50]}...")
                                                    except discord.Forbidden:
                                                        print("❌ DM 전송 실패: 유저가 DM을 차단했거나 설정을 꺼놨습니다.")
                                                    except Exception as e:
                                                        print(f"❌ DM 전송 오류: {e}")
                                                
                                                asyncio.run_coroutine_threadsafe(send_dm(), bot.loop)
                                        except (EOFError, KeyboardInterrupt):
                                            print("\n📤 DM 전송 모드 종료")
                                            break
                                else:
                                    print(f"❌ 1-{len(members)} 사이의 번호를 입력해주세요.")
                            else:
                                print("❌ 숫자를 입력해주세요.")
                        except (EOFError, KeyboardInterrupt):
                            print("\n❌ 유저 선택이 취소되었습니다.")
                    else:
                        print("❌ DM 전송 가능한 유저가 없습니다!")
                else:
                    print("❌ 봇이 서버에 연결되지 않았습니다!")
                
            elif command == 'help':
                print("💻 사용 가능한 명령어:")
                print("  - 'terminal on': 터미널 입력 모드 활성화 (채널 선택 가능)")
                print("  - 'terminal off': 터미널 입력 모드 비활성화")
                print("  - 'dm': 특정 유저에게 DM 전송")
                print("  - 'quit': 봇 종료")
                print("  - 'help': 도움말 표시")
                
            elif command:
                print(f"❌ 알 수 없는 명령어: {command}")
                print("'help'를 입력하여 사용 가능한 명령어를 확인하세요.")
                
        except (EOFError, KeyboardInterrupt):
            print("\n🛑 봇을 종료합니다...")
            asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
            break
        except Exception as e:
            print(f"❌ 명령어 처리 오류: {e}")

def terminal_input_handler():
    """터미널에서 입력을 받아 큐에 넣는 함수"""
    global terminal_input_active
    print("💬 터미널 입력 모드가 활성화되었습니다. 메시지를 입력하세요 (종료하려면 'quit' 입력):")
    
    while terminal_input_active:
        try:
            message = input("> ")
            if message.lower() == 'quit':
                terminal_input_active = False
                print("❌ 터미널 입력 모드를 종료합니다.")
                break
            elif message.strip():  # 빈 메시지가 아닌 경우만 큐에 추가
                terminal_message_queue.put(message)
        except (EOFError, KeyboardInterrupt):
            terminal_input_active = False
            print("❌ 터미널 입력 모드를 종료합니다.")
            break

async def process_terminal_messages():
    """큐에서 메시지를 가져와 채널로 전송하는 함수"""
    global terminal_channel_id
    
    while True:
        try:
            # 큐에서 메시지 가져오기 (non-blocking)
            try:
                message = terminal_message_queue.get_nowait()
            except queue.Empty:
                # 큐가 비어있으면 잠시 대기 후 다시 시도
                await asyncio.sleep(0.5)
                continue
            
            # 채널이 설정되어 있고 봇이 준비된 경우에만 전송
            if terminal_channel_id and bot.is_ready():
                try:
                    channel = bot.get_channel(terminal_channel_id)
                    if channel:
                        await channel.send(message)
                        print(f"✅ 메시지 전송 완료: {message}")
                    else:
                        print(f"❌ 채널을 찾을 수 없습니다: {terminal_channel_id}")
                except Exception as e:
                    print(f"❌ 메시지 전송 실패: {e}")
            
        except Exception as e:
            print(f"❌ 터미널 메시지 처리 오류: {e}")
        
        # 잠시 대기
        await asyncio.sleep(0.1)

@bot.event
async def on_ready():
    """봇이 준비되었을 때 실행되는 이벤트"""
    print(f"🎯 {bot.user}가 로그인했습니다!")
    print(f"📡 {len(bot.guilds)}개 서버에 연결됨")
    
    # 터미널 메시지 처리 태스크 시작
    bot.loop.create_task(process_terminal_messages())

# 가챠운세 제한 유저 관리
gacha_fortune_cooldowns = {}  # 유저별 쿨다운 시간 저장

# 대화모드 변수
natural_chat_mode = {}  # 채널별 대화모드 상태 {channel_id: True/False}
chat_mode_message_buffer = {}  # 채널별 최근 메시지 버퍼
chat_mode_last_response = {}  # 채널별 마지막 응답 시간
CHAT_MODE_RESPONSE_CHANCE = 0.3  # 기본 응답 확률 (30%)
CHAT_MODE_MIN_INTERVAL = 3  # 최소 응답 간격 (메시지 수)

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


def _extract_image_urls(data):
    """Civitai 응답에서 이미지 URL 목록을 재귀적으로 추출"""
    urls = []

    def walk(value):
        if value is None:
            return

        if isinstance(value, str):
            if value.startswith("http://") or value.startswith("https://"):
                parsed = urlparse(value)
                if parsed.path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    urls.append(value)
            return

        if isinstance(value, dict):
            for key in ("url", "imageUrl", "image_url", "src", "href"):
                if key in value:
                    walk(value[key])
            for v in value.values():
                walk(v)
            return

        if isinstance(value, list):
            for item in value:
                walk(item)
            return

        if hasattr(value, "__dict__"):
            walk(vars(value))

    walk(data)
    return list(dict.fromkeys(urls))


def _load_named_presets():
    """환경변수 기반 모델/LoRA 이름 프리셋 로드"""
    model_presets = {}
    lora_presets = {}

    raw_model_json = os.getenv("CIVITAI_MODEL_PRESETS_JSON", "").strip()
    raw_lora_json = os.getenv("CIVITAI_LORA_PRESETS_JSON", "").strip()

    if raw_model_json:
        try:
            parsed = json.loads(raw_model_json)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if isinstance(k, str) and isinstance(v, str):
                        model_presets[k] = v
        except Exception as e:
            print(f"모델 프리셋 JSON 파싱 실패: {e}")

    if raw_lora_json:
        try:
            parsed = json.loads(raw_lora_json)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if isinstance(k, str) and isinstance(v, str):
                        lora_presets[k] = v
        except Exception as e:
            print(f"LoRA 프리셋 JSON 파싱 실패: {e}")

    return model_presets, lora_presets


def _resolve_name_or_urn(value: str, presets: dict, kind: str):
    """URN 직접 입력 또는 이름 프리셋을 URN으로 변환"""
    if not value:
        return None, f"{kind} 값이 비어 있어."

    candidate = value.strip()
    if candidate.startswith("urn:"):
        return candidate, None

    lower_map = {k.lower(): v for k, v in presets.items()}
    resolved = lower_map.get(candidate.lower())
    if resolved:
        return resolved, None

    available = ", ".join(presets.keys()) if presets else "(없음)"
    return None, f"{kind} 프리셋 '{candidate}'을(를) 찾지 못했어. 사용 가능: {available}"


def _parse_civitai_command_args(raw: str):
    """
    .이미지생성 옵션 파서
    지원:
    - --model <이름 또는 URN>
    - --lora <이름 또는 URN[:strength]> (여러 번 사용 가능)
    - --size <WIDTHxHEIGHT> (예: 768x1024)
    - --steps <int>
    - --cfg <float>
    - --no-default-lora
    - --raw (자연어 프롬프트 자동 변환 비활성화)
    """
    try:
        tokens = shlex.split(raw)
    except Exception:
        return None, "명령어 파싱 실패: 따옴표를 확인해줘."

    model = None
    loras = []  # [{"urn": str, "strength": float}]
    width = None
    height = None
    steps = 24
    cfg_scale = 7.0
    use_default_lora = True
    raw_mode = False
    prompt_tokens = []

    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--model":
            if i + 1 >= len(tokens):
                return None, "--model 뒤에 모델 이름 또는 URN이 필요해."
            model = tokens[i + 1]
            i += 2
            continue
        if t == "--lora":
            if i + 1 >= len(tokens):
                return None, "--lora 뒤에 LoRA 이름/URN 또는 이름/URN:강도가 필요해."
            value = tokens[i + 1]
            if ":" in value:
                urn, s = value.rsplit(":", 1)
                try:
                    strength = float(s)
                except Exception:
                    return None, f"LoRA 강도 파싱 실패: {value}"
            else:
                urn = value
                strength = 0.8
            strength = max(0.0, min(strength, 2.0))
            loras.append({"urn": urn, "strength": strength})
            i += 2
            continue
        if t == "--size":
            if i + 1 >= len(tokens):
                return None, "--size 뒤에 768x1024 형식이 필요해."
            size = tokens[i + 1].lower()
            if "x" not in size:
                return None, "--size는 768x1024 형식으로 입력해줘."
            w, h = size.split("x", 1)
            try:
                width = int(w)
                height = int(h)
            except Exception:
                return None, "--size 숫자 파싱 실패."
            i += 2
            continue
        if t == "--steps":
            if i + 1 >= len(tokens):
                return None, "--steps 뒤에 숫자가 필요해."
            try:
                steps = int(tokens[i + 1])
            except Exception:
                return None, "--steps 숫자 파싱 실패."
            i += 2
            continue
        if t == "--cfg":
            if i + 1 >= len(tokens):
                return None, "--cfg 뒤에 숫자가 필요해."
            try:
                cfg_scale = float(tokens[i + 1])
            except Exception:
                return None, "--cfg 숫자 파싱 실패."
            i += 2
            continue
        if t == "--no-default-lora":
            use_default_lora = False
            i += 1
            continue
        if t == "--raw":
            raw_mode = True
            i += 1
            continue

        prompt_tokens.append(t)
        i += 1

    prompt = " ".join(prompt_tokens).strip()
    if not prompt:
        return None, "프롬프트가 비어 있어. 텍스트를 같이 넣어줘."

    return {
        "prompt": prompt,
        "model": model,
        "loras": loras,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "use_default_lora": use_default_lora,
        "raw_mode": raw_mode,
    }, None


async def _build_civitai_prompt(user_prompt: str) -> str:
    """자연어 입력을 Civitai용 영문 프롬프트로 정리"""
    if not user_prompt:
        return user_prompt

    # AI 사용 불가 시 원문 사용
    if gemini_model is None:
        return user_prompt

    instruction = f"""
다음 사용자 입력을 이미지 생성용 프롬프트로 변환해.

규칙:
- 영어로만 출력
- 쉼표로 구분된 키워드 스타일
- 불필요한 설명 금지, 프롬프트 본문만 출력
- 과도하게 길지 않게 1줄로 출력

사용자 입력:
{user_prompt}
"""

    try:
        response = await asyncio.to_thread(gemini_model.generate_content, instruction)
        converted = (response.text or "").strip().replace("\n", ", ")
        return converted if converted else user_prompt
    except Exception as e:
        print(f"프롬프트 변환 실패(원문 사용): {e}")
        return user_prompt


@bot.command(name='이미지생성')
async def civitai_generate_image(ctx, *, prompt: str = None):
    """Civitai 이미지 생성 명령어"""
    if not prompt:
        await ctx.send(
            "사용법: `.이미지생성 [프롬프트] [옵션]`\n"
            "옵션: `--model 이름/URN`, `--lora 이름/URN[:강도]`(반복 가능), `--size 768x1024`, `--steps 24`, `--cfg 7`, `--no-default-lora`\n"
            "예시: `.이미지생성 \"cinematic portrait\" --model 실사 --lora 얼굴보정:0.9 --size 768x1024`\n"
            "프리셋 목록: `.이미지프리셋`"
        )
        return

    civitai_token = os.getenv("CIVITAI_API_TOKEN")
    if not civitai_token:
        await ctx.send("❌ `CIVITAI_API_TOKEN`이 설정되지 않았어. Railway 변수에 추가해줘.")
        return

    parsed, parse_error = _parse_civitai_command_args(prompt)
    if parse_error:
        await ctx.send(f"❌ {parse_error}")
        return

    model_presets, lora_presets = _load_named_presets()

    default_model_urn = os.getenv("CIVITAI_MODEL_URN", "urn:air:sd1:checkpoint:civitai:4201@130072")
    default_lora_urn = os.getenv("CIVITAI_DEFAULT_LORA_URN", "urn:air:sd1:lora:civitai:162141@182559")
    try:
        default_lora_strength = float(os.getenv("CIVITAI_DEFAULT_LORA_STRENGTH", "0.8"))
    except Exception:
        default_lora_strength = 0.8
    default_lora_strength = max(0.0, min(default_lora_strength, 2.0))

    model_input = parsed["model"] or default_model_urn
    model_urn, model_error = _resolve_name_or_urn(model_input, model_presets, "모델")
    if model_error:
        await ctx.send(f"❌ {model_error}")
        return

    final_prompt = parsed["prompt"]
    loading_msg = await ctx.reply("🎨 프롬프트 정리 중...")
    if not parsed["raw_mode"]:
        final_prompt = await _build_civitai_prompt(parsed["prompt"])
    await loading_msg.edit(content="🎨 Civitai에 이미지 생성 요청 중...")

    try:
        debug_context = {
            "model": model_urn,
            "raw_mode": parsed["raw_mode"],
            "use_default_lora": parsed["use_default_lora"],
            "loras": [l["urn"] for l in parsed["loras"]],
            "size": f"{parsed['width'] or 768}x{parsed['height'] or 1024}",
            "steps": parsed["steps"],
            "cfg": parsed["cfg_scale"],
        }

        def _create_job():
            os.environ["CIVITAI_API_TOKEN"] = civitai_token
            import civitai

            payload = {
                "model": model_urn,
                "params": {
                    "prompt": final_prompt,
                    "negativePrompt": "low quality, blurry, deformed, extra fingers, bad anatomy",
                    "scheduler": "EulerA",
                    "steps": parsed["steps"],
                    "cfgScale": parsed["cfg_scale"],
                    "width": parsed["width"] or 768,
                    "height": parsed["height"] or 1024,
                    "clipSkip": 2
                }
            }

            additional_networks = {}
            if parsed["use_default_lora"] and default_lora_urn:
                resolved_default_lora, default_lora_error = _resolve_name_or_urn(default_lora_urn, lora_presets, "기본 LoRA")
                if default_lora_error:
                    raise ValueError(default_lora_error)
                additional_networks[resolved_default_lora] = {
                    "type": "Lora",
                    "strength": default_lora_strength
                }

            for lora in parsed["loras"]:
                resolved_lora_urn, lora_error = _resolve_name_or_urn(lora["urn"], lora_presets, "LoRA")
                if lora_error:
                    raise ValueError(lora_error)
                additional_networks[resolved_lora_urn] = {
                    "type": "Lora",
                    "strength": lora["strength"]
                }

            if additional_networks:
                payload["additionalNetworks"] = additional_networks

            return civitai.image.create(payload)
        job_response = await asyncio.to_thread(_create_job)

        image_urls = _extract_image_urls(job_response)
        if image_urls:
            await loading_msg.edit(content="✅ 이미지 생성 완료!")
            await send_image_embed(
                ctx.channel,
                image_urls[0],
                title="🎨 Civitai 생성 이미지",
                description=f"프롬프트: {final_prompt[:180]}"
            )
            return

        token = None
        job_id = None
        if isinstance(job_response, dict):
            token = job_response.get("token")
            job_id = job_response.get("id") or job_response.get("jobId")
        else:
            token = getattr(job_response, "token", None)
            job_id = getattr(job_response, "id", None) or getattr(job_response, "jobId", None)

        if not token and not job_id:
            await loading_msg.edit(content="❌ Civitai 응답에서 작업 식별자(token/id)를 찾지 못했어.")
            return

        await loading_msg.edit(content="⏳ 이미지 생성 중... (최대 2분 대기)")

        def _get_job_status(token_value, job_id_value):
            import civitai
            if token_value:
                return civitai.jobs.get(token=token_value)
            return civitai.jobs.get(id=job_id_value)

        final_urls = []
        for _ in range(60):
            await asyncio.sleep(2)
            status = await asyncio.to_thread(_get_job_status, token, job_id)
            final_urls = _extract_image_urls(status)
            if final_urls:
                break

        if not final_urls:
            await loading_msg.edit(content="⚠️ 생성 요청은 접수됐지만 아직 결과 이미지가 준비되지 않았어. 잠시 후 다시 시도해줘.")
            return

        await loading_msg.edit(content="✅ 이미지 생성 완료!")
        await send_image_embed(
            ctx.channel,
            final_urls[0],
            title="🎨 Civitai 생성 이미지",
            description=f"프롬프트: {final_prompt[:180]}"
        )
    except Exception as e:
        # Civitai/HTTP 오류 상세 추출
        status_code = None
        error_body = ""
        if hasattr(e, "response") and getattr(e, "response", None) is not None:
            try:
                status_code = getattr(e.response, "status_code", None)
                error_body = getattr(e.response, "text", "") or ""
            except Exception:
                pass

        try:
            # 일부 예외는 args에 JSON/문자열을 포함
            if not error_body and getattr(e, "args", None):
                error_body = " | ".join([str(a) for a in e.args if a is not None])
        except Exception:
            pass

        user_error = f"❌ 이미지 생성 오류: {str(e)[:250]}"
        if status_code:
            user_error += f" (HTTP {status_code})"
        await loading_msg.edit(content=user_error)

        print("==== Civitai 이미지 생성 상세 오류 ====")
        print(f"기본 오류: {e}")
        print(f"HTTP 상태코드: {status_code}")
        print(f"사용 컨텍스트: {json.dumps(debug_context, ensure_ascii=False)}")
        if error_body:
            print(f"에러 바디/상세: {error_body[:2000]}")
        print(traceback.format_exc())
        print("====================================")


@bot.command(name='이미지프리셋')
async def civitai_presets(ctx):
    """등록된 Civitai 모델/LoRA 이름 프리셋 출력"""
    model_presets, lora_presets = _load_named_presets()

    model_lines = [f"- {name}" for name in model_presets.keys()] if model_presets else ["- (없음)"]
    lora_lines = [f"- {name}" for name in lora_presets.keys()] if lora_presets else ["- (없음)"]

    msg = (
        "🧩 **Civitai 프리셋 목록**\n\n"
        "**모델 이름**\n" + "\n".join(model_lines[:30]) + "\n\n"
        "**LoRA 이름**\n" + "\n".join(lora_lines[:30]) + "\n\n"
        "사용 예시:\n"
        "`.이미지생성 \"cinematic portrait\" --model 실사 --lora 얼굴보정:0.8`\n"
        "프리셋은 환경변수 `CIVITAI_MODEL_PRESETS_JSON`, `CIVITAI_LORA_PRESETS_JSON`에 JSON으로 등록하면 돼."
    )
    await ctx.send(msg)

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
    
    # DM 채널에서 온 메시지 감지 (답장)
    if isinstance(message.channel, discord.DMChannel):
        print(f"\n📩 ========== DM 수신 ==========")
        print(f"👤 보낸 사람: {message.author.name} ({message.author.display_name})")
        print(f"💬 내용: {message.content}")
        print(f"⏰ 시간: {message.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"================================\n")
    
    # 명령어로 시작하는 메시지는 명령어 시스템이 처리하도록
    if message.content.startswith('.'):
        await bot.process_commands(message)
        return
    
    # 봇이 멘션되었을 때 AI 응답
    if bot.user.mentioned_in(message) and not message.mention_everyone:
        # 멘션 제거한 메시지 내용 추출
        user_message = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
        
        if not user_message:
            await message.reply("뭐? 부른 거야?")
            return
        if persona_model is None:
            await message.reply("지금 AI 인증 설정이 안 돼서 응답이 어려워. 관리자한테 GCP_KEY_JSON 설정해달라고 해줘.")
            return
        
        try:
            channel_id = message.channel.id
            
            # 채널별 대화 세션 관리
            if channel_id not in chat_sessions:
                chat_sessions[channel_id] = persona_model.start_chat(history=[])
            
            # 대화 세션이 너무 길어지면 리셋 (토큰 절약)
            if len(chat_sessions[channel_id].history) > 20:
                chat_sessions[channel_id] = persona_model.start_chat(history=[])
            
            # 기억 컨텍스트 추가
            memory_context = get_memory_context(message.author.id)
            # 존댓말 지시 추가
            speech_style = get_speech_style_instruction(message.author.id)
            message_with_context = f"{speech_style}{memory_context}[{message.author.display_name}의 메시지]: {user_message}"
            
            # 스트리밍 응답 - 먼저 빈 메시지 보내기
            reply_msg = await message.reply("...")
            
            # 스트리밍으로 AI 응답 생성
            ai_response = ""
            last_update = ""
            update_interval = 0.5  # 0.5초마다 업데이트
            last_update_time = time.time()
            
            try:
                response = chat_sessions[channel_id].send_message(message_with_context, stream=True)
                
                for chunk in response:
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
                response = chat_sessions[channel_id].send_message(message_with_context)
                ai_response = response.text.strip()
                if len(ai_response) > 1500:
                    ai_response = ai_response[:1500] + "..."
                await reply_msg.edit(content=ai_response)
            
            # 대화 버퍼에 저장 (자동 요약용)
            add_to_conversation_buffer(message.author.id, message.author.display_name, 'user', user_message)
            add_to_conversation_buffer(message.author.id, message.author.display_name, 'bot', ai_response)
            
            # 대화가 일정 수 이상 쌓이면 자동 요약
            user_id_str = str(message.author.id)
            if user_id_str in conversation_buffer:
                msg_count = len(conversation_buffer[user_id_str].get('messages', []))
                if msg_count >= SUMMARY_THRESHOLD:
                    await summarize_and_save_conversation(message.author.id, message.author.display_name)
                
        except Exception as e:
            print(f"AI 응답 오류: {e}")
            await message.reply("어... 뭔가 오류났는데 다시 말해봐")
        
        return  # AI 응답 후 다른 처리 스킵
    
    # 자연스러운 대화모드 처리
    channel_id = message.channel.id
    if channel_id in natural_chat_mode and natural_chat_mode[channel_id]:
        # 메시지 버퍼에 추가
        if channel_id not in chat_mode_message_buffer:
            chat_mode_message_buffer[channel_id] = []
        
        chat_mode_message_buffer[channel_id].append({
            'author': message.author.display_name,
            'content': message.content,
            'time': message.created_at.strftime("%H:%M")
        })
        
        # 버퍼 크기 제한 (최근 20개만 유지)
        if len(chat_mode_message_buffer[channel_id]) > 20:
            chat_mode_message_buffer[channel_id] = chat_mode_message_buffer[channel_id][-20:]
        
        # 마지막 응답 이후 메시지 수 확인
        if channel_id not in chat_mode_last_response:
            chat_mode_last_response[channel_id] = 0
        
        chat_mode_last_response[channel_id] += 1
        
        # 최소 간격 체크 & 확률 체크
        should_respond = False
        
        # 최소 3개 메시지가 지나야 응답 고려
        if chat_mode_last_response[channel_id] >= CHAT_MODE_MIN_INTERVAL:
            # 기본 확률로 응답 결정
            if random.random() < CHAT_MODE_RESPONSE_CHANCE:
                should_respond = True
            
            # 질문이 있으면 확률 높임
            if '?' in message.content or '뭐' in message.content or '어떻게' in message.content or '왜' in message.content:
                if random.random() < 0.5:  # 질문이면 50% 확률
                    should_respond = True
            
            # 메시지가 많이 쌓이면 확률 높임
            if chat_mode_last_response[channel_id] >= 8:
                if random.random() < 0.6:
                    should_respond = True
        
        if should_respond and len(message.content.strip()) > 2:
            try:
                # 최근 대화 컨텍스트 생성
                recent_chat = "\n".join([
                    f"{msg['author']}: {msg['content']}" 
                    for msg in chat_mode_message_buffer[channel_id][-10:]
                ])
                
                # AI에게 자연스럽게 끼어들지 판단 + 응답 생성 요청
                prompt = f"""
너는 디스코드 채팅방에 있는 유저 중 하나야. 
대화에 자연스럽게 참여해야 해.

최근 대화:
{recent_chat}

다음 지침을 따라:
1. 대화 흐름을 파악하고 자연스럽게 끼어들어
2. 너무 튀지 않게 짧고 자연스럽게 한마디 해
3. 질문에 답하거나, 의견을 말하거나, 리액션을 해
4. 말투는 {current_persona[:200] if current_persona else "반말로 친근하게"}
5. 1-2문장으로 짧게 답해
6. "ㅋㅋ", "ㄹㅇ", "ㅇㅇ" 같은 표현 자연스럽게 사용 가능
7. 너가 생각했을때 맞짱구 쳐야할 거 같은 얘기가 나오면 맞짱구 쳐.

대화에 자연스럽게 끼어들어봐:
"""
                
                # 스트리밍 응답
                reply_msg = await message.channel.send("...")
                
                ai_response = ""
                last_update = ""
                update_interval = 0.4
                last_update_time = time.time()
                
                try:
                    response = persona_model.start_chat(history=[]).send_message(prompt, stream=True)
                    
                    for chunk in response:
                        if chunk.text:
                            ai_response += chunk.text
                            
                            # SKIP 감지되면 바로 중단
                            if "SKIP" in ai_response.upper():
                                await reply_msg.delete()
                                return
                            
                            # 일정 시간마다 메시지 업데이트
                            current_time = time.time()
                            if current_time - last_update_time >= update_interval and ai_response != last_update:
                                display_text = ai_response[:300] if len(ai_response) > 300 else ai_response
                                try:
                                    await reply_msg.edit(content=display_text)
                                    last_update = ai_response
                                    last_update_time = current_time
                                except:
                                    pass
                    
                    ai_response = ai_response.strip()
                    
                    # SKIP이면 메시지 삭제
                    if ai_response.upper() == "SKIP" or len(ai_response) < 2:
                        await reply_msg.delete()
                    else:
                        if len(ai_response) > 300:
                            ai_response = ai_response[:300]
                        await reply_msg.edit(content=ai_response)
                        chat_mode_last_response[channel_id] = 0
                        
                except Exception as stream_error:
                    print(f"대화모드 스트리밍 오류: {stream_error}")
                    await reply_msg.delete()
            
            except Exception as e:
                print(f"대화모드 응답 오류: {e}")
    
    # 특정 유저 ID (여기에 원하는 유저 ID를 입력하세요)
    target_user_id = 320380927857655808  # 실제 유저 ID
    
    # 특정 메시지 내용
    target_messages = ["ㅇㄲㄴ","억까입니다","억까ㄴ","억까ㄴㄴ","억까하지마","억까하지마 시발련아","ㅇㄲㄴㄴ"]
    
    # 특정 유저가 특정 메시지를 입력했을 때
    if message.author.id == target_user_id and message.content in target_messages:
         
        # 디스코드 스티커 사용
        try:
            # 서버의 스티커 목록에서 "색욕권문" 스티커 찾기
            sticker = discord.utils.get(message.guild.stickers, name="색욕권문")
            
            if sticker:
                # 스티커를 메시지로 전송
                await message.channel.send(f"{message.author.mention}님이 특별한 스티커를 요청하셨습니다! 🌙", stickers=[sticker])
            else:
                # 스티커를 찾을 수 없으면 텍스트로 알림
                await message.channel.send(f"{message.author.mention}님이 특별한 스티커를 요청하셨습니다! 🌙\n(색욕권문 스티커를 찾을 수 없습니다)")
                
        except Exception as e:
            print(f"스티커 전송 오류: {e}")
            await message.channel.send(f"{message.author.mention}님이 특별한 스티커를 요청하셨습니다! 🌙")
    
    # "ㅇㅈ" 출력 기능 (아무나 입력 가능)
    # 특정 메시지들을 감지해서 "ㅇㅈ" 출력
    trigger_messages = ["권문 병신", "권문 장애인", "권문 여친 서가영"]
    
    # 아무나 입력해도 "ㅇㅈ" 출력
    if message.content in trigger_messages:
        await message.channel.send("ㅇㅈ")
    
    # "유기" 단어 감지 기능
    if "유기" in message.content:
        await message.channel.send("권문 또 유기야?")
    
    # "상희" + "워쉽/배" 또는 "특정유저멘션" + "워쉽/배" 감지 시 스티커 출력
    sanghee_mentioned = "상희" in message.content or "<@406707656158478338>" in message.content or "<@!406707656158478338>" in message.content
    ship_keyword = "워쉽" in message.content or "배" in message.content
    
    if sanghee_mentioned and ship_keyword:
        try:
            sticker = await bot.fetch_sticker(1467026345165983905)
            await message.channel.send(stickers=[sticker])
        except Exception as e:
            print(f"상희 스티커 전송 오류: {e}")
    
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

@bot.command(name='부검')
async def message_search(ctx, *, search_query):
    """키워드 또는 상황으로 메시지를 검색하는 명령어"""
    try:
        # 로딩 메시지 전송
        loading_msg = await ctx.send(f"🔍 '{search_query}' 부검 중... (채팅 기록 수집 중)")
        
        # 검색 결과 저장
        search_results = []
        
        # 서버의 모든 텍스트 채널에서 메시지 수집
        for channel in ctx.guild.text_channels:
            try:
                if not channel.permissions_for(ctx.guild.me).read_message_history:
                    continue
                    
                async for message in channel.history(limit=2000):
                    if message.content and not message.content.startswith('.'):
                        # 키워드 검색 (정확한 단어 매칭)
                        if search_query.lower() in message.content.lower():
                            search_results.append({
                                'message': message,
                                'channel': channel,
                                'type': 'keyword'
                            })
                        # 결과가 너무 많으면 중단
                        if len(search_results) >= 20:
                            break
                            
                if len(search_results) >= 20:
                    break
            except:
                continue
        
        # 키워드 검색 결과가 적으면 상황 검색 시도
        if len(search_results) < 5:
            await loading_msg.edit(content=f"🔍 키워드 검색 결과 부족. AI 상황 분석으로 확장 검색 중...")
            
            # 추가 메시지 수집 (상황 분석용)
            additional_messages = []
            for channel in ctx.guild.text_channels:
                try:
                    if not channel.permissions_for(ctx.guild.me).read_message_history:
                        continue
                        
                    async for message in channel.history(limit=1000):
                        if message.content and not message.content.startswith('.'):
                            additional_messages.append(message)
                            if len(additional_messages) >= 100:
                                break
                                
                    if len(additional_messages) >= 100:
                        break
                except:
                    continue
            
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
                    response = gemini_model.generate_content(prompt)
                    ai_result = response.text.strip()
                    
                    # AI 결과에서 번호 추출
                    import re
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


@bot.command(name='재판')
async def ai_trial(ctx, *, hint: str = None):
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
        response = gemini_model.generate_content(prompt)
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


@bot.command(name='페르소나')
async def change_persona(ctx, *, new_persona: str = None):
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
        persona_model = GenerativeModel(
            VERTEX_MODEL,
            system_instruction=[new_persona],
            client=genai_client,
        )
        
        # 모든 대화 세션 리셋
        chat_sessions.clear()
        
        await ctx.send(f"✅ 페르소나가 변경되었어!\n\n🎭 **새 페르소나:**\n```{new_persona[:300]}{'...' if len(new_persona) > 300 else ''}```")
        
    except Exception as e:
        await ctx.send(f"❌ 페르소나 변경 중 오류: {str(e)}")
        print(f"페르소나 변경 오류: {e}")


@bot.command(name='페르소나리셋')
async def reset_persona(ctx):
    """봇의 페르소나를 기본값으로 리셋하는 명령어"""
    global persona_model, current_persona, chat_sessions
    
    try:
        if gemini_model is None:
            await ctx.send("❌ Vertex AI 인증이 없어 페르소나 리셋을 사용할 수 없어. `GCP_KEY_JSON`을 설정해줘.")
            return
        current_persona = DEFAULT_PERSONA
        persona_model = GenerativeModel(
            VERTEX_MODEL,
            system_instruction=[DEFAULT_PERSONA],
            client=genai_client,
        )
        chat_sessions.clear()
        
        await ctx.send("✅ 페르소나가 기본값으로 리셋되었어!")
        
    except Exception as e:
        await ctx.send(f"❌ 리셋 중 오류: {str(e)}")


@bot.command(name='대화리셋')
async def reset_chat(ctx):
    """현재 채널의 AI 대화 기록을 리셋하는 명령어"""
    global chat_sessions
    
    channel_id = ctx.channel.id
    if channel_id in chat_sessions:
        del chat_sessions[channel_id]
        await ctx.send("✅ 이 채널의 대화 기록이 리셋되었어! 새로운 대화를 시작해봐.")
    else:
        await ctx.send("이 채널에는 저장된 대화 기록이 없어.")


@bot.command(name='ai')
async def ai_chat(ctx, *, question: str = None):
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
        
        # 대화 세션이 너무 길어지면 리셋
        if len(chat_sessions[channel_id].history) > 20:
            chat_sessions[channel_id] = persona_model.start_chat(history=[])
        
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
            response = chat_sessions[channel_id].send_message(message_with_context, stream=True)
            
            for chunk in response:
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
            response = chat_sessions[channel_id].send_message(message_with_context)
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
        
        async with aiohttp.ClientSession() as session:
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


@bot.command(name='서치챗')
async def search_chat(ctx, *, query: str = None):
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
            planner_response = planner_model.generate_content(planner_prompt)
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

            response = chat_sessions[channel_id].send_message(prompt)
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


# 학습된 유저 스타일 저장 (유저ID -> 스타일 데이터)
learned_user_styles = {}

# 현재 활성화된 학습 페르소나
active_learned_persona = None


@bot.command(name='학습')
async def learn_user_style(ctx, target_user: discord.Member = None):
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
        
        # 해당 유저의 메시지 수집
        messages = []
        message_count = 0
        
        # 서버의 모든 텍스트 채널에서 메시지 수집
        for channel in ctx.guild.text_channels:
            try:
                if not channel.permissions_for(ctx.guild.me).read_message_history:
                    continue
                    
                async for message in channel.history(limit=500):
                    if message.author.id == target_user.id and message.content and not message.content.startswith('.'):
                        # 너무 짧거나 링크만 있는 메시지 제외
                        if len(message.content) > 3 and not message.content.startswith('http'):
                            messages.append(message.content)
                            message_count += 1
                            if message_count >= 150:
                                break
                            
                if message_count >= 150:
                    break
            except:
                continue
        
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
        
        response = gemini_model.generate_content(analysis_prompt)
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

system instruction만 출력해 (다른 설명 없이):
"""
        
        persona_response = gemini_model.generate_content(persona_prompt)
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
        save_memory()
        
        # 바로 이 페르소나를 활성화
        current_persona = generated_persona
        persona_model = GenerativeModel(
            VERTEX_MODEL,
            system_instruction=[generated_persona],
            client=genai_client,
        )
        chat_sessions.clear()
        active_learned_persona = user_id_str
        
        result_text = f"""✅ **{target_user.display_name}** 학습 완료! ({len(messages)}개 메시지 분석)

🎭 이제 봇을 멘션하거나 `.ai` 명령어를 사용하면 **{target_user.display_name}**처럼 대답해요!

💡 `.말투분석 @{target_user.display_name}` 으로 분석 결과를 볼 수 있어요."""
        
        await loading_msg.edit(content=result_text)
        
    except Exception as e:
        await ctx.send(f"❌ 학습 중 오류: {str(e)}")
        print(f"학습 오류: {e}")


@bot.command(name='학습목록')
async def list_learned_users(ctx):
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


@bot.command(name='학습적용')
async def apply_learned_persona(ctx, target_user: discord.Member = None):
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
        persona_model = GenerativeModel(
            VERTEX_MODEL,
            system_instruction=[data['persona_instruction']],
            client=genai_client,
        )
        chat_sessions.clear()
        active_learned_persona = user_id_str
        
        # 메모리에도 저장
        bot_memory['active_persona'] = user_id_str
        save_memory()
        
        await ctx.send(f"✅ **{data['name']}** 페르소나가 적용되었어요!\n이제 봇이 {data['name']}처럼 대답해요.")
        
    except Exception as e:
        await ctx.send(f"❌ 적용 중 오류: {str(e)}")


@bot.command(name='학습삭제')
async def delete_learned_user(ctx, target_user: discord.Member = None):
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
    save_memory()
    
    await ctx.send(f"✅ **{name}**의 학습 데이터가 삭제되었어요.")


@bot.command(name='말투분석')
async def analyze_style_only(ctx, target_user: discord.Member = None):
    """유저의 말투만 분석해서 보여주는 명령어 (학습하지 않음)"""
    if not target_user:
        await ctx.send("📝 **사용법:** `.말투분석 @유저`")
        return
    if gemini_model is None:
        await ctx.send("❌ Vertex AI 인증이 없어 말투 분석을 사용할 수 없어. `GCP_KEY_JSON`을 설정해줘.")
        return
    
    try:
        loading_msg = await ctx.send(f"🔍 **{target_user.display_name}**의 말투 분석 중...")
        
        # 메시지 수집
        messages = []
        for channel in ctx.guild.text_channels:
            try:
                if not channel.permissions_for(ctx.guild.me).read_message_history:
                    continue
                
                async for message in channel.history(limit=300):
                    if message.author.id == target_user.id and message.content and not message.content.startswith('.'):
                        if len(message.content) > 3:
                            messages.append(message.content)
                            if len(messages) >= 50:
                                break
                
                if len(messages) >= 50:
                    break
            except:
                continue
        
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
        
        response = gemini_model.generate_content(prompt)
        
        await loading_msg.edit(content=response.text[:1900])
        
    except Exception as e:
        await ctx.send(f"❌ 분석 중 오류: {str(e)}")


@bot.command(name='대화모드')
async def chat_mode_toggle(ctx, mode: str = None):
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

@bot.command(name='점메추')
async def lunch_recommendation(ctx):
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

@bot.command(name='워쉽전적')
async def wows_stats(ctx, region: str = 'na', *, player_name: str = None):
    """World of Warships 플레이어 전적을 검색하는 명령어
    
    사용법:
    .워쉽전적 플레이어명          (기본: NA 서버)
    .워쉽전적 na 플레이어명       (NA 서버)
    .워쉽전적 asia 플레이어명     (ASIA 서버)
    .워쉽전적 eu 플레이어명       (EU 서버)
    .워쉽전적 ru 플레이어명       (RU 서버)
    """
    try:
        # 리전과 플레이어명 파싱
        region_lower = region.lower()
        
        # 리전이 지정되지 않은 경우 (첫 번째 인자가 플레이어명)
        if region_lower not in WOWS_API_REGIONS and player_name is None:
            player_name = region
            region_lower = 'na'  # 기본값
        
        # 플레이어명이 없으면 오류
        if not player_name:
            await ctx.send("❌ 사용법: `.워쉽전적 [리전] 플레이어명`\n예시: `.워쉽전적 na Flamu` 또는 `.워쉽전적 Flamu`\n\n지원 리전: na, eu, asia, ru")
            return
        
        # 리전별 API URL 선택
        if region_lower not in WOWS_API_REGIONS:
            await ctx.send(f"❌ 올바른 리전을 입력하세요: na, eu, asia, ru\n입력한 리전: {region_lower}")
            return
        
        api_base_url = WOWS_API_REGIONS[region_lower]
        region_names = {
            'na': 'NA (북미)',
            'eu': 'EU (유럽)', 
            'asia': 'ASIA (아시아)',
            'ru': 'RU (러시아)'
        }
        region_name = region_names.get(region_lower, region_lower.upper())
        
        # 로딩 메시지 전송
        loading_msg = await ctx.send(f"🔍 '{player_name}' 플레이어 검색 중... ({region_name} 서버)")
        
        # API 키 확인
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!\n.env 파일에 WARGAMING_API_KEY를 추가해주세요.\nhttps://developers.wargaming.net/ 에서 발급받을 수 있습니다.")
            return
        
        async with aiohttp.ClientSession() as session:
            # 1단계: 플레이어 검색 (여러 타입으로 시도)
            search_url = f"{api_base_url}/wows/account/list/"
            
            # 먼저 startswith로 시도 (더 넓은 검색)
            search_params = {
                'application_id': WARGAMING_API_KEY,
                'search': player_name,
                'type': 'startswith'
            }
            
            async with session.get(search_url, params=search_params) as response:
                if response.status != 200:
                    await loading_msg.edit(content=f"❌ API 요청 실패! Wargaming API 키를 확인해주세요.")
                    return
                
                search_data = await response.json()
                
                # 응답 상태 확인
                if search_data.get('status') != 'ok':
                    error_msg = search_data.get('error', {}).get('message', '알 수 없는 오류')
                    await loading_msg.edit(content=f"❌ API 오류: {error_msg}")
                    return
                
                # 검색 결과 확인
                if not search_data.get('data'):
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.\n\n💡 팁:\n- 플레이어 이름을 정확히 입력했는지 확인하세요\n- 대소문자는 상관없습니다\n- 일부 이름만 입력해도 검색됩니다")
                    return
                
                # 첫 번째 검색 결과 사용
                account_id = search_data['data'][0]['account_id']
                found_nickname = search_data['data'][0]['nickname']
                
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
                                    # 실제 값 합산
                                    total_actual_damage = damage
                                    total_actual_wins = wins
                                    total_actual_frags = frags
                                    
                                    # 기댓값 합산
                                    total_expected_damage = 0
                                    total_expected_wins = 0
                                    total_expected_frags = 0
                                    
                                    for ship in player_ships:
                                        ship_id = ship['ship_id']
                                        pvp_stats = ship.get('pvp', {})
                                        ship_battles = pvp_stats.get('battles', 0)
                                        
                                        if ship_battles == 0:
                                            continue
                                        
                                        # Expected values 가져오기
                                        expected = PR_EXPECTED_VALUES.get(str(ship_id))
                                        if expected and isinstance(expected, dict):
                                            exp_damage = expected.get('average_damage_dealt', 0)
                                            exp_frags = expected.get('average_frags', 0)
                                            exp_wins = expected.get('win_rate', 0) / 100  # % -> 비율
                                            
                                            # 기댓값 합산 (전투 수 * 평균)
                                            total_expected_damage += exp_damage * ship_battles
                                            total_expected_wins += exp_wins * ship_battles
                                            total_expected_frags += exp_frags * ship_battles
                                    
                                    # PR 계산 (WoWS Numbers 공식)
                                    if total_expected_damage > 0 and total_expected_wins > 0 and total_expected_frags > 0:
                                        # Step 1: Ratios
                                        rDmg = total_actual_damage / total_expected_damage
                                        rFrags = total_actual_frags / total_expected_frags
                                        rWins = total_actual_wins / total_expected_wins
                                        
                                        # Step 2: Normalization
                                        nDmg = max(0, (rDmg - 0.4) / (1 - 0.4))
                                        nFrags = max(0, (rFrags - 0.1) / (1 - 0.1))
                                        nWins = max(0, (rWins - 0.7) / (1 - 0.7))
                                        
                                        # Step 3: PR Value
                                        personal_rating = int(700 * nDmg + 300 * nFrags + 150 * nWins)
                                    
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

@bot.command(name='워쉽액터')
async def wows_actor_stats(ctx, region: str = 'na', *, player_name: str = None):
    """플레이어의 판수(전투 수) 통계를 검색하는 명령어"""
    try:
        if not player_name:
            if region.lower() in WOWS_API_REGIONS:
                await ctx.send("❌ 사용법: `.워쉽액터 [리전] 플레이어명`")
            else:
                player_name = region
                region = 'na'
            if not player_name:
                return
        
        region_lower = region.lower() if region.lower() in WOWS_API_REGIONS else 'na'
        api_base_url = WOWS_API_REGIONS[region_lower]
        region_names = {'na': 'NA', 'eu': 'EU', 'asia': 'ASIA', 'ru': 'RU'}
        region_name = region_names.get(region_lower, 'NA')
        
        loading_msg = await ctx.send(f"🔍 '{player_name}'의 판수 통계 검색 중... ({region_name} 서버)")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        async with aiohttp.ClientSession() as session:
            # 플레이어 검색
            search_url = f"{api_base_url}/wows/account/list/"
            search_params = {
                'application_id': WARGAMING_API_KEY,
                'search': player_name,
                'type': 'startswith'
            }
            
            async with session.get(search_url, params=search_params) as response:
                if response.status != 200:
                    await loading_msg.edit(content="❌ API 요청 실패!")
                    return
                
                search_data = await response.json()
                if search_data.get('status') != 'ok' or not search_data.get('data'):
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                
                account_id = search_data['data'][0]['account_id']
                found_nickname = search_data['data'][0]['nickname']
                
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

@bot.command(name='워쉽함선')
async def wows_ship_stats(ctx, region: str = 'na', *, player_name: str = None):
    """World of Warships 플레이어의 함선별 전적을 검색하는 명령어
    
    사용법:
    .워쉽함선 플레이어명          (기본: NA 서버, 상위 10개 함선)
    .워쉽함선 na 플레이어명       (NA 서버)
    .워쉽함선 asia 플레이어명     (ASIA 서버)
    """
    try:
        # 리전과 플레이어명 파싱
        region_lower = region.lower()
        
        if region_lower not in WOWS_API_REGIONS and player_name is None:
            player_name = region
            region_lower = 'na'
        
        if not player_name:
            await ctx.send("❌ 사용법: `.워쉽함선 [리전] 플레이어명`\n예시: `.워쉽함선 Flamu`")
            return
        
        if region_lower not in WOWS_API_REGIONS:
            await ctx.send(f"❌ 올바른 리전을 입력하세요: na, eu, asia, ru")
            return
        
        api_base_url = WOWS_API_REGIONS[region_lower]
        region_names = {
            'na': 'NA (북미)',
            'eu': 'EU (유럽)', 
            'asia': 'ASIA (아시아)',
            'ru': 'RU (러시아)'
        }
        region_name = region_names.get(region_lower, region_lower.upper())
        
        loading_msg = await ctx.send(f"🔍 '{player_name}' 플레이어의 함선 전적 검색 중... ({region_name} 서버)")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        async with aiohttp.ClientSession() as session:
            # 1단계: 플레이어 검색
            search_url = f"{api_base_url}/wows/account/list/"
            search_params = {
                'application_id': WARGAMING_API_KEY,
                'search': player_name,
                'type': 'startswith'
            }
            
            async with session.get(search_url, params=search_params) as response:
                if response.status != 200:
                    await loading_msg.edit(content=f"❌ API 요청 실패!")
                    return
                
                search_data = await response.json()
                
                if search_data.get('status') != 'ok' or not search_data.get('data'):
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                
                account_id = search_data['data'][0]['account_id']
                found_nickname = search_data['data'][0]['nickname']
                
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
            
            # 3단계: 함선 정보 가져오기 (함선 이름) - 재시도 로직 포함
            ship_names = {}
            ship_details = {}
            
            await loading_msg.edit(content=f"🔍 '{found_nickname}'의 함선 이름 로딩 중...")
            
            # 전투 수 기준으로 정렬 (encyclopedia 요청 전에 미리 정렬)
            player_ships.sort(key=lambda x: x.get('pvp', {}).get('battles', 0), reverse=True)
            
            # 상위 10개 함선의 ID만 가져오기
            top_ship_ids = [str(ship['ship_id']) for ship in player_ships[:10]]
            
            if top_ship_ids:
                encyclopedia_url = f"{api_base_url}/wows/encyclopedia/ships/"
                encyclopedia_params = {
                    'application_id': WARGAMING_API_KEY,
                    'ship_id': ','.join(top_ship_ids),
                    'fields': 'name,tier,type,nation'
                }
                
                # 최대 3번 재시도
                for retry in range(3):
                    try:
                        async with session.get(encyclopedia_url, params=encyclopedia_params, timeout=aiohttp.ClientTimeout(total=15)) as response:
                            if response.status == 200:
                                encyclopedia_data = await response.json()
                                if encyclopedia_data.get('status') == 'ok' and encyclopedia_data.get('data'):
                                    for ship_id, ship_info in encyclopedia_data['data'].items():
                                        ship_id_int = int(ship_id)
                                        ship_names[ship_id_int] = ship_info.get('name', f'함선 ID {ship_id}')
                                        ship_details[ship_id_int] = {
                                            'tier': ship_info.get('tier', 0),
                                            'type': ship_info.get('type', 'Unknown'),
                                            'nation': ship_info.get('nation', 'Unknown')
                                        }
                                    print(f"✅ {len(ship_names)}개 함선 이름 로드 완료")
                                    break  # 성공하면 루프 탈출
                            else:
                                print(f"⚠️ Encyclopedia API 오류 (상태: {response.status}, 재시도: {retry+1}/3)")
                                if retry < 2:
                                    await asyncio.sleep(1)  # 1초 대기 후 재시도
                    except asyncio.TimeoutError:
                        print(f"⚠️ Encyclopedia API 타임아웃 (재시도: {retry+1}/3)")
                        if retry < 2:
                            await asyncio.sleep(1)  # 1초 대기 후 재시도
                    except Exception as e:
                        print(f"⚠️ Encyclopedia API 오류: {e} (재시도: {retry+1}/3)")
                        if retry < 2:
                            await asyncio.sleep(1)  # 1초 대기 후 재시도
            
            # 전투 수 기준으로 정렬
            player_ships.sort(key=lambda x: x.get('pvp', {}).get('battles', 0), reverse=True)
            
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
                
                # 함선별 PR 계산 (WoWS Numbers 정확한 공식)
                ship_pr = 0
                if battles > 0:
                    expected = PR_EXPECTED_VALUES.get(str(ship_id))
                    
                    if expected and isinstance(expected, dict):
                        # Expected values가 있으면 정확한 공식 사용
                        try:
                            exp_damage = expected.get('average_damage_dealt', 0)
                            exp_frags = expected.get('average_frags', 0)
                            exp_wins = expected.get('win_rate', 0) / 100  # % -> 비율
                            
                            actual_wins = win_rate / 100
                            
                            # Step 1: Ratios
                            rDmg = avg_damage / exp_damage if exp_damage > 0 else 0
                            rFrags = avg_frags / exp_frags if exp_frags > 0 else 0
                            rWins = actual_wins / exp_wins if exp_wins > 0 else 0
                            
                            # Step 2: Normalization
                            nDmg = max(0, (rDmg - 0.4) / (1 - 0.4))
                            nFrags = max(0, (rFrags - 0.1) / (1 - 0.1))
                            nWins = max(0, (rWins - 0.7) / (1 - 0.7))
                            
                            # Step 3: PR Value
                            ship_pr = int(700 * nDmg + 300 * nFrags + 150 * nWins)
                        except:
                            # 오류 시 간단한 계산
                            ship_pr = int((avg_damage/1000)*0.4*100 + win_rate*0.3 + avg_frags*20 + survival_rate*0.1)
                    else:
                        # Expected values 없으면 간단한 계산
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

@bot.command(name='워쉽클랜')
async def wows_clan(ctx, region: str = 'na', *, clan_tag: str = None):
    """클랜 정보를 검색하는 명령어"""
    try:
        if not clan_tag:
            if region.lower() in WOWS_API_REGIONS:
                await ctx.send("❌ 사용법: `.워쉽클랜 [리전] [클랜태그]`\n예시: `.워쉽클랜 na CLAN`")
            else:
                clan_tag = region
                region = 'na'
            if not clan_tag:
                await ctx.send("❌ 사용법: `.워쉽클랜 [리전] [클랜태그]`")
                return
        
        region_lower = region.lower() if region.lower() in WOWS_API_REGIONS else 'na'
        if region_lower not in WOWS_API_REGIONS:
            region_lower = 'na'
        
        api_base_url = WOWS_API_REGIONS[region_lower]
        region_names = {'na': 'NA (북미)', 'eu': 'EU (유럽)', 'asia': 'ASIA (아시아)', 'ru': 'RU (러시아)'}
        region_name = region_names.get(region_lower, 'NA')
        
        loading_msg = await ctx.send(f"🔍 클랜 '{clan_tag}' 검색 중... ({region_name} 서버)")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        async with aiohttp.ClientSession() as session:
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

@bot.command(name='워쉽함선정보')
async def wows_ship_info(ctx, *, ship_name: str):
    """함선 백과사전 정보를 검색하는 명령어"""
    try:
        # 대괄호가 포함된 검색어는 즉시 거부
        if '[' in ship_name or ']' in ship_name:
            await ctx.send("❌ 검색어에 대괄호 `[]`를 포함할 수 없습니다. 대괄호 없이 함선 이름만 입력하세요.\n예시: `.워쉽함선정보 Montana`")
            return
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await ctx.send("❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        loading_msg = await ctx.send(f"🔍 함선 '{ship_name}' 정보 검색 중...")
        
        async with aiohttp.ClientSession() as session:
            # 함선 검색 방법 1: 이름으로 검색 (최소 필드만)
            ships_url = f"{WOWS_API_REGIONS['na']}/wows/encyclopedia/ships/"
            search_params = {
                'application_id': WARGAMING_API_KEY,
                'fields': 'name'  # 먼저 이름만 가져와서 검색
            }
            
            found_ship_id = None
            try:
                # 이름으로 검색 (정확한 매칭 우선, 부분 검색은 보조)
                search_name_lower = ship_name.lower().strip()
                
                # 1단계: 정확한 이름 매칭
                exact_matches = []
                # 2단계: 부분 검색
                partial_matches = []
                
                # 여러 페이지를 순회하며 검색 (최대 10페이지까지)
                page_total = 10  # 최대 페이지 수
                current_page = 1
                
                while current_page <= page_total:
                    page_params = search_params.copy()
                    page_params['page_no'] = current_page
                    page_params['limit'] = 100  # 페이지당 항목 수
                    
                    async with session.get(ships_url, params=page_params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status != 200:
                            if current_page == 1:
                                error_text = await response.text()
                                await loading_msg.edit(content=f"❌ API 요청 실패! (상태: {response.status})")
                                print(f"함선 검색 API 오류: {error_text}")
                                return
                            break
                        
                        ships_data = await response.json()
                        if ships_data.get('status') != 'ok':
                            if current_page == 1:
                                error_msg = ships_data.get('error', {}).get('message', '알 수 없는 오류')
                                await loading_msg.edit(content=f"❌ API 오류: {error_msg}")
                                print(f"API 오류 상세: {ships_data}")
                                return
                            break
                        
                        # 페이지 정보 업데이트
                        meta = ships_data.get('meta', {})
                        actual_page_total = meta.get('page_total', page_total)
                        if current_page == 1:
                            page_total = min(actual_page_total, 10)  # 최대 10페이지까지만
                        
                        # 함선 데이터 확인
                        ship_data_dict = ships_data.get('data', {})
                        if not ship_data_dict:
                            # 더 이상 데이터가 없으면 종료
                            break
                        
                        # 함선 검색
                        for ship_id, ship_data in ship_data_dict.items():
                            ship_name_full = ship_data.get('name', '')
                            if not ship_name_full:
                                continue
                            
                            ship_name_lower = ship_name_full.lower()
                            
                            # 함선 이름에 대괄호가 포함되어 있으면 완전히 제외
                            if '[' in ship_name_full or ']' in ship_name_full:
                                continue
                            
                            # 정확한 매칭
                            if search_name_lower == ship_name_lower:
                                exact_matches.append((ship_id, ship_name_full))
                                found_ship_id = ship_id  # 정확한 매칭을 찾으면 즉시 종료
                                print(f"✅ 정확한 매칭 발견: {ship_name_full} (페이지 {current_page})")
                                break
                            # 부분 검색
                            elif search_name_lower in ship_name_lower:
                                partial_matches.append((ship_id, ship_name_full))
                        
                        # 디버깅: 첫 페이지에서 검색된 함선 수 확인
                        if current_page == 1:
                            print(f"검색어: '{ship_name}', 페이지 {current_page}에서 {len(ship_data_dict)}개 함선 검색, 정확한 매칭: {len(exact_matches)}, 부분 매칭: {len(partial_matches)}")
                        
                        # 정확한 매칭을 찾으면 검색 종료
                        if found_ship_id:
                            break
                        
                        current_page += 1
                
                # 정확한 매칭이 있으면 사용
                if exact_matches:
                    found_ship_id = exact_matches[0][0]
                # 없으면 부분 검색 결과 사용 (대괄호 없는 함선만)
                elif partial_matches:
                    found_ship_id = partial_matches[0][0]
                else:
                    found_ship_id = None
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
                async with session.get(ships_url, params=detail_params, timeout=aiohttp.ClientTimeout(total=20)) as detail_response:
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

@bot.command(name='워쉽비교')
async def wows_compare(ctx, region: str = 'na', *, players: str = None):
    """두 플레이어를 비교하는 명령어"""
    try:
        # 리전과 플레이어명 파싱
        region_lower = region.lower()
        
        # 리전이 지정되지 않은 경우 (첫 번째 인자가 플레이어명)
        if region_lower not in WOWS_API_REGIONS:
            if players is None:
                # 첫 번째 인자가 플레이어명이고, 두 번째 인자가 없음
                await ctx.send("❌ 사용법: `.워쉽비교 [리전] 플레이어1 플레이어2`\n예시: `.워쉽비교 Player1 Player2` 또는 `.워쉽비교 na Player1 Player2`")
                return
            else:
                # 첫 번째 인자가 플레이어명, players가 두 번째 플레이어명
                player_list = [region] + players.split()
                region_lower = 'na'
        else:
            # 리전이 지정된 경우
            if not players:
                await ctx.send("❌ 사용법: `.워쉽비교 [리전] 플레이어1 플레이어2`\n예시: `.워쉽비교 Player1 Player2`")
                return
            player_list = players.split()
        
        if len(player_list) < 2:
            await ctx.send("❌ 두 명의 플레이어 이름을 입력하세요!")
            return
        
        player1_name = player_list[0]
        player2_name = player_list[1]
        api_base_url = WOWS_API_REGIONS[region_lower]
        region_names = {'na': 'NA', 'eu': 'EU', 'asia': 'ASIA', 'ru': 'RU'}
        region_name = region_names.get(region_lower, 'NA')
        
        loading_msg = await ctx.send(f"🔍 '{player1_name}' vs '{player2_name}' 비교 중...")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        async with aiohttp.ClientSession() as session:
            # 두 플레이어 정보 가져오기
            players_data = []
            for player_name in [player1_name, player2_name]:
                search_url = f"{api_base_url}/wows/account/list/"
                search_params = {
                    'application_id': WARGAMING_API_KEY,
                    'search': player_name,
                    'type': 'startswith'
                }
                
                async with session.get(search_url, params=search_params) as response:
                    if response.status != 200:
                        await loading_msg.edit(content=f"❌ '{player_name}' 검색 실패!")
                        return
                    
                    search_data = await response.json()
                    if search_data.get('status') != 'ok' or not search_data.get('data'):
                        await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                        return
                    
                    account_id = search_data['data'][0]['account_id']
                    nickname = search_data['data'][0]['nickname']
                    
                    # 통계 가져오기
                    stats_url = f"{api_base_url}/wows/account/info/"
                    stats_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
                    
                    async with session.get(stats_url, params=stats_params) as stats_response:
                        stats_data = await stats_response.json()
                        if stats_data.get('status') == 'ok' and stats_data.get('data'):
                            player_data = stats_data['data'][str(account_id)]
                            stats = player_data.get('statistics', {}).get('pvp', {})
                            
                            battles = stats.get('battles', 0)
                            wins = stats.get('wins', 0)
                            damage = stats.get('damage_dealt', 0)
                            frags = stats.get('frags', 0)
                            
                            win_rate = (wins / battles * 100) if battles > 0 else 0
                            avg_damage = damage / battles if battles > 0 else 0
                            avg_frags = frags / battles if battles > 0 else 0
                            
                            # PR 계산 (WoWS Numbers 정확한 공식)
                            pr = 0
                            if battles > 0:
                                try:
                                    # 함선별 통계 가져오기
                                    ships_url = f"{api_base_url}/wows/ships/stats/"
                                    ships_params = {'application_id': WARGAMING_API_KEY, 'account_id': account_id}
                                    
                                    async with session.get(ships_url, params=ships_params) as ships_response:
                                        ships_data = await ships_response.json()
                                        
                                        if ships_data.get('status') == 'ok' and ships_data.get('data'):
                                            player_ships = ships_data['data'].get(str(account_id), [])
                                            
                                            if player_ships:
                                                # 실제 값
                                                total_actual_damage = damage
                                                total_actual_wins = wins
                                                total_actual_frags = frags
                                                
                                                # 기댓값 합산
                                                total_expected_damage = 0
                                                total_expected_wins = 0
                                                total_expected_frags = 0
                                                
                                                for ship in player_ships:
                                                    ship_id = ship['ship_id']
                                                    pvp_stats = ship.get('pvp', {})
                                                    ship_battles = pvp_stats.get('battles', 0)
                                                    
                                                    if ship_battles == 0:
                                                        continue
                                                    
                                                    # Expected values 가져오기
                                                    expected = PR_EXPECTED_VALUES.get(str(ship_id))
                                                    if expected and isinstance(expected, dict):
                                                        exp_damage = expected.get('average_damage_dealt', 0)
                                                        exp_frags = expected.get('average_frags', 0)
                                                        exp_wins = expected.get('win_rate', 0) / 100
                                                        
                                                        # 기댓값 합산
                                                        total_expected_damage += exp_damage * ship_battles
                                                        total_expected_wins += exp_wins * ship_battles
                                                        total_expected_frags += exp_frags * ship_battles
                                                
                                                # PR 계산
                                                if total_expected_damage > 0 and total_expected_wins > 0 and total_expected_frags > 0:
                                                    # Step 1: Ratios
                                                    rDmg = total_actual_damage / total_expected_damage
                                                    rFrags = total_actual_frags / total_expected_frags
                                                    rWins = total_actual_wins / total_expected_wins
                                                    
                                                    # Step 2: Normalization
                                                    nDmg = max(0, (rDmg - 0.4) / (1 - 0.4))
                                                    nFrags = max(0, (rFrags - 0.1) / (1 - 0.1))
                                                    nWins = max(0, (rWins - 0.7) / (1 - 0.7))
                                                    
                                                    # Step 3: PR Value
                                                    pr = int(700 * nDmg + 300 * nFrags + 150 * nWins)
                                except Exception as e:
                                    print(f"비교 PR 계산 오류 ({nickname}): {e}")
                                    pr = 0
                            
                            players_data.append({
                                'name': nickname,
                                'battles': battles,
                                'win_rate': win_rate,
                                'avg_damage': avg_damage,
                                'avg_frags': avg_frags,
                                'pr': pr
                            })
            
            if len(players_data) != 2:
                await loading_msg.edit(content="❌ 두 플레이어 정보를 모두 가져올 수 없습니다.")
                return
            
            p1, p2 = players_data[0], players_data[1]
            
            # 승자 판정
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
            
            # 비교 표시
            embed.add_field(
                name=f"👤 {p1['name']}",
                value=f"```\n"
                      f"PR: {p1['pr']:,}\n"
                      f"전투: {p1['battles']:,}\n"
                      f"승률: {p1['win_rate']:.2f}%\n"
                      f"평균 피해: {p1['avg_damage']:,.0f}\n"
                      f"평균 격침: {p1['avg_frags']:.2f}\n"
                      f"```",
                inline=True
            )
            
            embed.add_field(
                name=f"👤 {p2['name']}",
                value=f"```\n"
                      f"PR: {p2['pr']:,}\n"
                      f"전투: {p2['battles']:,}\n"
                      f"승률: {p2['win_rate']:.2f}%\n"
                      f"평균 피해: {p2['avg_damage']:,.0f}\n"
                      f"평균 격침: {p2['avg_frags']:.2f}\n"
                      f"```",
                inline=True
            )
            
            await loading_msg.edit(content="", embed=embed)
            
    except Exception as e:
        await ctx.send(f"❌ 플레이어 비교 중 오류: {str(e)}")
        print(f"워쉽 비교 오류: {e}")

@bot.command(name='워쉽랭크')
async def wows_ranked(ctx, region: str = 'na', *, player_name: str = None):
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
        region_names = {'na': 'NA', 'eu': 'EU', 'asia': 'ASIA', 'ru': 'RU'}
        region_name = region_names.get(region_lower, 'NA')
        
        loading_msg = await ctx.send(f"🔍 '{player_name}' 랭크전 전적 검색 중... ({region_name} 서버)")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        async with aiohttp.ClientSession() as session:
            # 플레이어 검색
            search_url = f"{api_base_url}/wows/account/list/"
            search_params = {
                'application_id': WARGAMING_API_KEY,
                'search': player_name,
                'type': 'startswith'
            }
            
            async with session.get(search_url, params=search_params) as response:
                if response.status != 200:
                    await loading_msg.edit(content="❌ API 요청 실패!")
                    return
                
                search_data = await response.json()
                if search_data.get('status') != 'ok' or not search_data.get('data'):
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                
                account_id = search_data['data'][0]['account_id']
                found_nickname = search_data['data'][0]['nickname']
                
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

@bot.command(name='워쉽업적')
async def wows_achievements(ctx, region: str = 'na', *, player_name: str = None):
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
        region_names = {'na': 'NA', 'eu': 'EU', 'asia': 'ASIA', 'ru': 'RU'}
        region_name = region_names.get(region_lower, 'NA')
        
        loading_msg = await ctx.send(f"🔍 '{player_name}' 업적 검색 중... ({region_name} 서버)")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        async with aiohttp.ClientSession() as session:
            # 플레이어 검색
            search_url = f"{api_base_url}/wows/account/list/"
            search_params = {
                'application_id': WARGAMING_API_KEY,
                'search': player_name,
                'type': 'startswith'
            }
            
            async with session.get(search_url, params=search_params) as response:
                if response.status != 200:
                    await loading_msg.edit(content="❌ API 요청 실패!")
                    return
                
                search_data = await response.json()
                if search_data.get('status') != 'ok' or not search_data.get('data'):
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                
                account_id = search_data['data'][0]['account_id']
                found_nickname = search_data['data'][0]['nickname']
                
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

@bot.command(name='워쉽최근전투')
async def wows_recent_battles(ctx, region: str = 'na', *, player_name: str = None):
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
        region_names = {'na': 'NA', 'eu': 'EU', 'asia': 'ASIA', 'ru': 'RU'}
        region_name = region_names.get(region_lower, 'NA')
        
        loading_msg = await ctx.send(f"🔍 '{player_name}' 최근 전투 기록 검색 중... ({region_name} 서버)")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        # 주의: Wargaming API는 최근 전투 기록을 직접 제공하지 않습니다
        # 대신 마지막 전투 시간과 전체 통계만 제공됨
        await loading_msg.edit(content="⚠️ Wargaming API는 최근 전투 기록을 직접 제공하지 않습니다.\n대신 전체 통계를 확인하려면 `.워쉽전적` 명령어를 사용하세요.")
        
    except Exception as e:
        await ctx.send(f"❌ 최근 전투 검색 중 오류: {str(e)}")
        print(f"워쉽 최근 전투 오류: {e}")

@bot.command(name='워쉽랭킹')
async def wows_ship_ranking(ctx, *, ship_name: str):
    """함선 순위표를 조회하는 명령어"""
    try:
        loading_msg = await ctx.send(f"🔍 함선 '{ship_name}' 순위표 검색 중...")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        # 주의: Wargaming API는 함선별 랭킹을 직접 제공하지 않습니다
        await loading_msg.edit(content="⚠️ Wargaming API는 함선별 랭킹을 직접 제공하지 않습니다.\n대신 해당 함선의 정보를 확인하려면 `.워쉽함선정보 [함선명]` 명령어를 사용하세요.")
        
    except Exception as e:
        await ctx.send(f"❌ 랭킹 검색 중 오류: {str(e)}")
        print(f"워쉽 랭킹 오류: {e}")

@bot.command(name='워쉽티어')
async def wows_tier_stats(ctx, region: str = 'na', *, player_name: str = None):
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
        region_names = {'na': 'NA', 'eu': 'EU', 'asia': 'ASIA', 'ru': 'RU'}
        region_name = region_names.get(region_lower, 'NA')
        
        loading_msg = await ctx.send(f"🔍 '{player_name}' 티어별 통계 검색 중... ({region_name} 서버)")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        async with aiohttp.ClientSession() as session:
            # 플레이어 검색
            search_url = f"{api_base_url}/wows/account/list/"
            search_params = {
                'application_id': WARGAMING_API_KEY,
                'search': player_name,
                'type': 'startswith'
            }
            
            async with session.get(search_url, params=search_params) as response:
                if response.status != 200:
                    await loading_msg.edit(content="❌ API 요청 실패!")
                    return
                
                search_data = await response.json()
                if search_data.get('status') != 'ok' or not search_data.get('data'):
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                
                account_id = search_data['data'][0]['account_id']
                found_nickname = search_data['data'][0]['nickname']
                
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
                    # 모든 함선의 ID 수집
                    ship_ids = [str(ship['ship_id']) for ship in player_ships]
                    
                    # Encyclopedia에서 티어 정보 가져오기 (100개씩 분할 요청)
                    ship_tiers = {}
                    encyclopedia_url = f"{api_base_url}/wows/encyclopedia/ships/"
                    
                    # API 제한으로 인해 100개씩 분할
                    for i in range(0, len(ship_ids), 100):
                        batch_ids = ship_ids[i:i+100]
                        encyclopedia_params = {
                            'application_id': WARGAMING_API_KEY,
                            'ship_id': ','.join(batch_ids),
                            'fields': 'tier'
                        }
                        
                        try:
                            async with session.get(encyclopedia_url, params=encyclopedia_params, timeout=aiohttp.ClientTimeout(total=10)) as enc_response:
                                if enc_response.status == 200:
                                    enc_data = await enc_response.json()
                                    if enc_data.get('status') == 'ok' and enc_data.get('data'):
                                        for sid, ship_info in enc_data['data'].items():
                                            ship_tiers[int(sid)] = ship_info.get('tier', 0)
                        except:
                            pass
                    
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

@bot.command(name='워쉽국가')
async def wows_nation_stats(ctx, region: str = 'na', *, player_name: str = None):
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
        region_names = {'na': 'NA', 'eu': 'EU', 'asia': 'ASIA', 'ru': 'RU'}
        region_name = region_names.get(region_lower, 'NA')
        
        loading_msg = await ctx.send(f"🔍 '{player_name}' 국가별 통계 검색 중... ({region_name} 서버)")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        async with aiohttp.ClientSession() as session:
            # 플레이어 검색
            search_url = f"{api_base_url}/wows/account/list/"
            search_params = {
                'application_id': WARGAMING_API_KEY,
                'search': player_name,
                'type': 'startswith'
            }
            
            async with session.get(search_url, params=search_params) as response:
                if response.status != 200:
                    await loading_msg.edit(content="❌ API 요청 실패!")
                    return
                
                search_data = await response.json()
                if search_data.get('status') != 'ok' or not search_data.get('data'):
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                
                account_id = search_data['data'][0]['account_id']
                found_nickname = search_data['data'][0]['nickname']
                
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
                    # 모든 함선의 ID 수집
                    ship_ids = [str(ship['ship_id']) for ship in player_ships]
                    
                    # 함선 국가 정보 가져오기 (100개씩 분할 요청)
                    ship_nations = {}
                    encyclopedia_url = f"{api_base_url}/wows/encyclopedia/ships/"
                    
                    # API 제한으로 인해 100개씩 분할
                    for i in range(0, len(ship_ids), 100):
                        batch_ids = ship_ids[i:i+100]
                        encyclopedia_params = {
                            'application_id': WARGAMING_API_KEY,
                            'ship_id': ','.join(batch_ids),
                            'fields': 'nation'
                        }
                        
                        try:
                            async with session.get(encyclopedia_url, params=encyclopedia_params, timeout=aiohttp.ClientTimeout(total=10)) as enc_response:
                                if enc_response.status == 200:
                                    enc_data = await enc_response.json()
                                    if enc_data.get('status') == 'ok' and enc_data.get('data'):
                                        for sid, ship_info in enc_data['data'].items():
                                            ship_nations[int(sid)] = ship_info.get('nation', 'Unknown')
                        except:
                            pass
                    
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

@bot.command(name='워쉽타입')
async def wows_type_stats(ctx, region: str = 'na', *, player_name: str = None):
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
        region_names = {'na': 'NA', 'eu': 'EU', 'asia': 'ASIA', 'ru': 'RU'}
        region_name = region_names.get(region_lower, 'NA')
        
        loading_msg = await ctx.send(f"🔍 '{player_name}' 타입별 통계 검색 중... ({region_name} 서버)")
        
        if WARGAMING_API_KEY == 'your_wargaming_api_key_here':
            await loading_msg.edit(content="❌ Wargaming API 키가 설정되지 않았습니다!")
            return
        
        async with aiohttp.ClientSession() as session:
            # 플레이어 검색
            search_url = f"{api_base_url}/wows/account/list/"
            search_params = {
                'application_id': WARGAMING_API_KEY,
                'search': player_name,
                'type': 'startswith'
            }
            
            async with session.get(search_url, params=search_params) as response:
                if response.status != 200:
                    await loading_msg.edit(content="❌ API 요청 실패!")
                    return
                
                search_data = await response.json()
                if search_data.get('status') != 'ok' or not search_data.get('data'):
                    await loading_msg.edit(content=f"❌ '{player_name}' 플레이어를 찾을 수 없습니다.")
                    return
                
                account_id = search_data['data'][0]['account_id']
                found_nickname = search_data['data'][0]['nickname']
                
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
                    # 모든 함선의 ID 수집
                    ship_ids = [str(ship['ship_id']) for ship in player_ships]
                    
                    # 함선 타입 정보 가져오기 (100개씩 분할 요청)
                    ship_types = {}
                    encyclopedia_url = f"{api_base_url}/wows/encyclopedia/ships/"
                    
                    # API 제한으로 인해 100개씩 분할
                    for i in range(0, len(ship_ids), 100):
                        batch_ids = ship_ids[i:i+100]
                        encyclopedia_params = {
                            'application_id': WARGAMING_API_KEY,
                            'ship_id': ','.join(batch_ids),
                            'fields': 'type'
                        }
                        
                        try:
                            async with session.get(encyclopedia_url, params=encyclopedia_params, timeout=aiohttp.ClientTimeout(total=10)) as enc_response:
                                if enc_response.status == 200:
                                    enc_data = await enc_response.json()
                                    if enc_data.get('status') == 'ok' and enc_data.get('data'):
                                        for sid, ship_info in enc_data['data'].items():
                                            ship_types[int(sid)] = ship_info.get('type', 'Unknown')
                        except:
                            pass
                    
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

@bot.command(name='도움말')
async def help_command(ctx):
    """도움말을 출력하는 명령어"""
    help_text = """
**🎮 사용 가능한 명령어들:**

`.랜덤` - 랜덤하게 싹바가지 없이 말한다 
`.점메추` - 오늘 점심 뭐 먹을지 추천해줌
`.이미지 [URL] [제목]` - 이미지를 임베드로 보내기
`.이미지생성 [프롬프트] [옵션]` - Civitai 이미지 생성 (자연어 자동 프롬프트 변환)
`.이미지프리셋` - 등록된 모델/LoRA 이름 프리셋 보기
`.gpt [메시지]` - 핑프년아 니가 검색해(보류)
`.인성진단 [@유저명]` - 채팅 패턴으로 인성 분석 (개재밌음)
`.부검 [검색어]` - 키워드 또는 상황으로 메시지 검색 (개유용함)
`.포켓몬위치 [포켓몬명/도감번호]` - 포켓몬 스칼렛/바이올렛 위치 정보 (개유용함)
`.대화모드 on/off` - 특정 유저 스타일로 대화 모드 (개신기함)
`.터미널명령어 on/off` - 터미널에서 메시지를 채팅창으로 전송하는 모드
`.@유저명 [분]동안 닥쳐` - [시간(분)]만큼 닥쳐
`.@유저명 아봉 해제` - 이 위대한 권문이 특별히 자비를 베풀도록 하지
`.뮤트상태 @유저명` - 유저의 뮤트 상태 확인
`.도움말` - 아 도움 유기함 ㅅㄱ
`.배` - 배 탈 사람 맨션
'.헬다' - SAY HELLO TO THE DEMOCRACY
'.롤' - 개병신정신병게임할사람 모집

**⚓ World of Warships:**
`.워쉽전적 [리전] [플레이어명]` - 플레이어 전체 전적 검색
`.워쉽액터 [리전] [플레이어명]` - 플레이어 판수(전투 수) 통계
`.워쉽함선 [리전] [플레이어명]` - 플레이어의 함선별 전적 (상위 10개)
`.워쉽클랜 [리전] [클랜태그]` - 클랜 정보 검색
`.워쉽함선정보 [함선명]` - 함선 백과사전 정보
`.워쉽비교 [리전] 플레이어1 플레이어2` - 두 플레이어 비교
`.워쉽랭크 [리전] [플레이어명]` - 랭크전 전적
`.워쉽업적 [리전] [플레이어명]` - 업적/배지 조회
`.워쉽티어 [리전] [플레이어명]` - 티어별 통계
`.워쉽타입 [리전] [플레이어명]` - 타입별 통계 (구축함/순양함/전함/항모)
  리전: na (기본), eu, asia, ru
  예시: `.워쉽전적 Flamu` 또는 `.워쉽함선 asia PlayerName`

**🔮 운세 관련 명령어:**
`.가챠운세` - 가챠 전에 확인하는 특별한 운세

**🎰 가챠 시뮬레이터:**
`.워쉽가챠 [1/10]` - 월드 오브 워쉽 × 블루 아카이브 콜라보 가챠
`.림버스 [1/10]` - 림버스 컴퍼니 발푸르기스의 밤 뽑기

**🎯 특별 기능:**
특정 유저가 "ㅇㄲㄴ"을 입력하면 웹훅 임베드로 이미지가 출력됩니다!


```
    """
    await ctx.send(help_text)

@bot.command(name='터미널명령어')
async def terminal_command(ctx, mode: str = None):
    """터미널 입력 모드를 켜거나 끄는 명령어"""
    global terminal_input_active, terminal_channel_id
    
    if mode is None:
        await ctx.send("❌ 사용법: `.터미널명령어 on` 또는 `.터미널명령어 off`")
        return
    
    if mode.lower() == "on":
        if terminal_input_active:
            await ctx.send("❌ 이미 터미널 입력 모드가 활성화되어 있습니다!")
            return
        
        terminal_input_active = True
        terminal_channel_id = ctx.channel.id
        await ctx.send(f"💻 **터미널 입력 모드 ON!**\n이제 터미널에서 입력한 메시지가 이 채널로 전송됩니다.\n터미널에서 'quit'를 입력하면 모드가 종료됩니다.")
        
        # 터미널 입력 스레드 시작
        terminal_thread = threading.Thread(target=terminal_input_handler, daemon=True)
        terminal_thread.start()
        
    elif mode.lower() == "off":
        if not terminal_input_active:
            await ctx.send("❌ 현재 터미널 입력 모드가 켜져있지 않습니다!")
            return
        
        terminal_input_active = False
        terminal_channel_id = None
        await ctx.send("✅ **터미널 입력 모드 OFF!** 터미널에서 메시지 전송이 중단됩니다.")
        
    else:
        await ctx.send("❌ 사용법: `.터미널명령어 on` 또는 `.터미널명령어 off`")

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



@bot.event
async def on_reaction_add(reaction, user):
    """반응이 추가되었을 때 실행되는 이벤트"""
    # 봇이 아닌 사용자가 ❌ 이모지로 반응했을 때
    if user != bot.user and str(reaction.emoji) == "❌":
        # 봇이 보낸 메시지인지 확인
        if reaction.message.author == bot.user:
            try:
                # 메시지 삭제
                await reaction.message.delete()
                print(f"🗑️ {user.name}님이 봇 메시지를 삭제했습니다.")
            except Exception as e:
                print(f"❌ 메시지 삭제 실패: {e}")

# 봇 실행
if __name__ == "__main__":
    # 토큰은 절대 코드에 하드코딩하지 말 것 (.env로 관리)
    TOKEN = os.getenv("DISCORD_TOKEN")
    
    # 토큰 검증
    if not TOKEN:
        print("❌ 오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
        print("📝 .env 파일에 DISCORD_TOKEN=your_actual_token_here 형식으로 추가해주세요.")
        raise RuntimeError("DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
    
    if TOKEN.strip() == "" or TOKEN == "your_discord_bot_token_here":
        print("❌ 오류: DISCORD_TOKEN이 기본값이거나 빈 값입니다.")
        print("📝 .env 파일에 실제 디스코드 봇 토큰을 입력해주세요.")
        raise RuntimeError("DISCORD_TOKEN이 유효하지 않습니다.")
    
    # 토큰이 로드되었는지 확인 (보안상 일부만 표시)
    token_preview = TOKEN[:10] + "..." if len(TOKEN) > 10 else "***"
    print(f"✅ 토큰 로드 완료: {token_preview}")
    print("🚀 디스코드 봇을 시작합니다...")
    
    # 서버 환경 감지 (Railway, Render 등)
    is_server = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RENDER') or os.getenv('DYNO')
    
    # 로컬 환경에서만 터미널 명령어 입력 스레드 시작
    if not is_server:
        terminal_command_thread = threading.Thread(target=terminal_command_handler, daemon=True)
        terminal_command_thread.start()
    else:
        print("☁️ 서버 환경 감지됨 - 터미널 입력 기능 비활성화")
    
    try:
        bot.run(TOKEN)
    except discord.errors.LoginFailure as e:
        print("❌ 디스코드 로그인 실패!")
        print("🔍 가능한 원인:")
        print("   1. .env 파일의 DISCORD_TOKEN이 잘못되었거나 만료되었습니다.")
        print("   2. 봇 토큰이 Discord Developer Portal에서 재발급되었습니다.")
        print("   3. 봇이 삭제되었거나 비활성화되었습니다.")
        print(f"💡 상세 오류: {e}")
        raise 