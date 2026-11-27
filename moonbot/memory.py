"""장기기억(bot_memory.json) 저장/로드와 유저별 기억."""
import datetime
import json
import os
import time


# ==================== 장기기억 시스템 ====================
MEMORY_FILE = 'bot_memory.json'

# 메모리 데이터 구조
bot_memory = {
    'learned_users': {},      # 학습된 유저 스타일
    'active_persona': None,   # 현재 활성화된 페르소나 유저 ID
    'user_memories': {},      # 유저별 기억 {user_id: [{fact, timestamp}, ...]}
    'server_facts': [],       # 서버 관련 기억
    'conversation_summaries': {},  # 채널별 대화 요약
    'burger_count': 3         # 햄버거/배달 시킨 횟수
}

MEMORY_SAVE_MIN_INTERVAL = 10  # 초
_memory_last_save = 0.0
_memory_dirty = False


def save_memory(force: bool = False):
    """메모리를 파일에 저장.

    기억 하나 추가될 때마다 JSON 전체를 다시 쓰던 걸, 최소 간격을 두고 묶어서
    쓰도록 바꿨다. force=True면 간격을 무시하고 즉시 쓴다.
    """
    global _memory_last_save, _memory_dirty

    _memory_dirty = True
    if not force and time.time() - _memory_last_save < MEMORY_SAVE_MIN_INTERVAL:
        return

    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(bot_memory, f, ensure_ascii=False, indent=2)
        _memory_last_save = time.time()
        _memory_dirty = False
        print("💾 메모리 저장 완료")
    except Exception as e:
        print(f"❌ 메모리 저장 실패: {e}")

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


def load_memory():
    """파일에서 메모리 로드 (학습 페르소나 복원은 cogs.ai_chat에서 한다)."""
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                bot_memory.update(json.load(f))
            print("✅ 메모리 로드 완료")
        else:
            print("📝 메모리 파일 없음, 새로 시작")
    except Exception as e:
        print(f"❌ 메모리 로드 실패: {e}")


def flush_memory():
    """아직 안 쓴 변경이 있으면 즉시 저장 (봇 종료 시)."""
    if _memory_dirty:
        save_memory(force=True)


load_memory()
