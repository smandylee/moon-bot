"""Moon Bot 공용 코어 (AI 클라이언트, HTTP, 장기기억).

다른 모듈이 import 시점에 환경변수를 읽으므로 .env를 가장 먼저 로드한다.
"""
from dotenv import load_dotenv

try:
    load_dotenv()
except Exception as e:
    print(f"⚠️ .env 파일 로드 실패: {e}")
    print("환경변수를 직접 설정하거나 .env 파일을 확인해주세요. (UTF-8로 저장돼 있어야 함)")
