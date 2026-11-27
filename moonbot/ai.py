"""Vertex AI(Gemini) / OpenAI 클라이언트와 비동기 호출 헬퍼."""
import os
import base64
import json
import asyncio
import threading


# Gemini (Vertex AI, VERTEX_MODEL 공통) 설정
try:
    from google import genai
    from google.genai import types as genai_types
except Exception:
    genai = None
    genai_types = None

# OpenAI API 설정
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
_openai_client = None


def get_openai_client():
    """OpenAI 클라이언트를 한 번만 만들어 재사용 (예전엔 호출마다 새로 생성)."""
    global _openai_client
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or api_key == 'your_openai_api_key_here':
        return None
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# Vertex AI 초기화 (google-genai SDK, Vertex 모드)
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "alphavertex-486307")
GCP_LOCATION = os.getenv("GCP_LOCATION", "global")  # Gemini 3.8 Flash 권장: global
VERTEX_MODEL = os.getenv("VERTEX_MODEL", "gemini-3.8-flash")  # Vertex/Gemini 모델 ID (전 기능 공통)

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

# 대화 기록으로 되돌려 보낼 최대 항목 수 (user/model 각각 1개씩 = 10턴)
HISTORY_MAX_ENTRIES = 20


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
            response = self._model.generate_content(message, history=self.history)
            self.history.append({"role": "user", "text": message})
            self.history.append({"role": "model", "text": response.text})
            self._trim()
            return response

        def _stream_gen():
            full_text = ""
            try:
                response_stream = self._model._client.models.generate_content_stream(
                    **self._model._request_kwargs(message, self.history)
                )
                for chunk in response_stream:
                    chunk_text = getattr(chunk, "text", "") or ""
                    if chunk_text:
                        full_text += chunk_text
                        yield _CompatChunk(chunk_text)
            finally:
                self.history.append({"role": "user", "text": message})
                self.history.append({"role": "model", "text": full_text})
                self._trim()

        return _stream_gen()

    def _trim(self):
        del self.history[:-HISTORY_MAX_ENTRIES]


class GenerativeModel:
    def __init__(self, model_name: str, system_instruction=None, client=None):
        self.model_name = model_name
        self._client = client
        if isinstance(system_instruction, list):
            self.system_instruction = "\n".join([str(s) for s in system_instruction if s])
        else:
            self.system_instruction = str(system_instruction or "")

    def _build_contents(self, prompt: str, history=None):
        """대화 기록을 role별 contents 리스트로 만든다.

        예전에는 전체를 문자열 하나로 뭉쳐서 보냈다. 그러면 role 구분이 사라지고
        요청마다 접두부가 달라져 프리픽스 캐싱도 걸리지 않는다.
        """
        contents = []
        for item in (history or [])[-HISTORY_MAX_ENTRIES:]:
            text = item.get("text", "")
            if not text:
                continue
            role = "model" if item.get("role") == "model" else "user"
            contents.append({"role": role, "parts": [{"text": text}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        return contents

    def _request_kwargs(self, prompt: str, history=None) -> dict:
        contents = self._build_contents(prompt, history)
        kwargs = {"model": self.model_name, "contents": contents}
        if self.system_instruction:
            if genai_types is not None:
                kwargs["config"] = genai_types.GenerateContentConfig(
                    system_instruction=self.system_instruction
                )
            else:
                # types를 못 쓰는 환경에서는 첫 메시지에 붙여서라도 전달한다
                contents.insert(0, {
                    "role": "user",
                    "parts": [{"text": f"[System]\n{self.system_instruction}"}],
                })
        return kwargs

    def generate_content(self, prompt: str, history=None):
        if not self._client:
            raise RuntimeError("AI client is not initialized")
        response = self._client.models.generate_content(
            **self._request_kwargs(prompt, history)
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
        print(
            f"✅ Vertex AI 초기화 완료 (google-genai, 모델: {VERTEX_MODEL}, "
            f"프로젝트: {GCP_PROJECT_ID}, 리전: {GCP_LOCATION})"
        )
    except Exception as e:
        print(f"❌ Vertex AI 초기화 실패: {e}")
        gemini_model = None
else:
    if genai is None:
        print("⚠️ google-genai 패키지를 찾지 못해 Vertex AI를 비활성화합니다.")
    else:
        print("⚠️ Vertex AI 비활성화: GCP 인증 정보가 없습니다.")
    gemini_model = None

# =============================================================================
# 비동기 실행 헬퍼
# google-genai SDK 호출은 동기라서, 그대로 await 없이 부르면 응답이 끝날 때까지
# 이벤트 루프 전체가 멈춘다(다른 유저 명령·디스코드 하트비트 포함).
# 아래 헬퍼로 항상 스레드에 넘겨서 실행한다.
# =============================================================================
_AI_STREAM_DONE = object()


async def ai_generate(model, prompt: str):
    """동기 generate_content를 스레드에서 실행."""
    return await asyncio.to_thread(model.generate_content, prompt)


async def ai_send(chat_session, message: str):
    """동기 send_message(비스트리밍)를 스레드에서 실행."""
    return await asyncio.to_thread(chat_session.send_message, message)


async def ai_stream(chat_session, message: str):
    """동기 스트리밍 제너레이터를 스레드에서 돌리고 청크를 async로 넘긴다."""
    chunk_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _worker():
        try:
            for chunk in chat_session.send_message(message, stream=True):
                loop.call_soon_threadsafe(chunk_queue.put_nowait, chunk)
        except Exception as exc:  # 예외도 큐로 넘겨 호출부에서 다시 던진다
            loop.call_soon_threadsafe(chunk_queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(chunk_queue.put_nowait, _AI_STREAM_DONE)

    threading.Thread(target=_worker, daemon=True).start()

    while True:
        item = await chunk_queue.get()
        if item is _AI_STREAM_DONE:
            return
        if isinstance(item, BaseException):
            raise item
        yield item
