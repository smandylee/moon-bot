# 🌙 Moon Bot - 디스코드 봇

랜덤 메시지를 출력하는 재미있는 디스코드 봇입니다!

## 🚀 기능

- `!랜덤` - 랜덤한 한국어 메시지 출력
- `!random` - 랜덤한 영어 메시지 출력  
- `!도움말` - 사용 가능한 명령어 목록 보기

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
2. `.env` 파일에 봇 토큰 추가:
```
DISCORD_TOKEN=your_actual_bot_token_here
```

### 5. 봇 실행
```bash
python bot.py
```

## 🎮 사용법

디스코드 채널에서 다음 명령어들을 사용할 수 있습니다:

- `!랜덤` - 랜덤한 한국어 메시지 출력
- `!random` - 랜덤한 영어 메시지 출력
- `!도움말` - 도움말 보기

## 🔧 커스터마이징

`bot.py` 파일의 `random_messages` 리스트를 수정하여 원하는 메시지들을 추가하거나 변경할 수 있습니다.

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 