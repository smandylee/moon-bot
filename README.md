# 🌙 Moon Bot - 디스코드 봇

**다양한 기능을 갖춘 디스코드 봇입니다!**

## 🚀 주요 기능

### 🎮 기본 기능
- `.랜덤` - 랜덤한 한국어 메시지 출력
- `.롤`, `.헬다`, `.배` - 게임 맨션 명령어
- `.이미지 [URL]` - 이미지 임베드 전송
- `.gpt [메시지]` - ChatGPT API 연동
- `.@유저명 [분]동안 닥쳐` - 뮤트 기능
- `.뮤트상태 @유저명` - 뮤트 상태 확인

### 🔮 운세 기능
- `.가챠운세` - 가챠 전에 확인하는 특별한 운세



## 📋 설치 및 설정

### 1. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 디스코드 봇 생성
1. [Discord Developer Portal](https://discord.com/developers/applications)에 접속
2. "New Application" 클릭하여 새 애플리케이션 생성
3. 왼쪽 메뉴에서 "Bot" 클릭
4. "Add Bot" 클릭하여 봇 생성
5. "Reset Token"을 클릭하여 봇 토큰 복사

### 3. 봇을 서버에 초대
1. "OAuth2" → "URL Generator" 클릭
2. "Scopes"에서 "bot" 체크
3. "Bot Permissions"에서 다음 권한들 체크:
   - Send Messages
   - Read Message History
   - Use Slash Commands
4. 생성된 URL로 접속하여 봇을 서버에 초대

### 4. 환경변수 설정
1. `env_example.txt` 파일을 참고하여 `.env` 파일 생성
2. `.env` 파일에 봇 토큰과 API 키 추가:
```
DISCORD_TOKEN=your_actual_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here  # ChatGPT 기능 사용시
```

### 5. 봇 실행
```bash
python bot.py
```

## 🎮 사용법

### 기본 명령어
디스코드 채널에서 다음 명령어들을 사용할 수 있습니다:

- `.랜덤` - 랜덤한 한국어 메시지 출력
- `.롤`, `.헬다`, `.배` - 게임 맨션
- `.이미지 [URL] [제목]` - 이미지 임베드 전송
- `.gpt [메시지]` - ChatGPT와 대화
- `.@유저명 [분]동안 닥쳐` - 유저 뮤트
- `.@유저명 아봉해제` - 뮤트 해제
- `.뮤트상태 @유저명` - 뮤트 상태 확인
- `.가챠운세` - 가챠 전 특별 운세
- `.도움말` - 도움말 보기



## 🔧 커스터마이징

### 기본 기능 커스터마이징
- `bot.py` 파일의 `random_messages` 리스트를 수정하여 원하는 메시지들을 추가하거나 변경할 수 있습니다.
- `target_user_ids` 리스트를 수정하여 맨션할 유저들을 변경할 수 있습니다.

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 