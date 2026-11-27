# =============================================================================
# Moon Bot — main entry point
#
# 기능은 cogs/ 아래 파일별로 나뉘어 있고, 공용 코어(AI/HTTP/기억)는 moonbot/ 에 있다.
# 새 기능을 추가하려면 cogs/에 파일을 만들고 EXTENSIONS에 이름을 넣으면 된다.
# =============================================================================
import os

import moonbot  # noqa: F401  (.env를 제일 먼저 로드)

import discord
from discord.ext import commands

from moonbot.memory import flush_memory
from moonbot.net import close_http_session

EXTENSIONS = [
    'cogs.general',
    'cogs.ai_chat',
    'cogs.ai_tools',
    'cogs.fun',
    'cogs.quote',
    'cogs.moderation',
    'cogs.steam',
    'cogs.wows',
    'cogs.terminal',
]

intents = discord.Intents.default()
intents.message_content = True  # 메시지 내용 읽기
intents.members = True          # 멤버 목록 보기


class MoonBot(commands.Bot):
    async def setup_hook(self):
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        print(f"✅ 기능 {len(EXTENSIONS)}개 로드, 명령어 {len(self.commands)}개")

        # '명언 만들기' 우클릭 메뉴 등록 (전역 동기화라 처음엔 반영까지 시간이 걸릴 수 있음)
        try:
            synced = await self.tree.sync()
            print(f"✅ 앱 커맨드 {len(synced)}개 동기화 완료")
        except Exception as sync_error:
            print(f"⚠️ 앱 커맨드 동기화 실패: {sync_error}")

    async def close(self):
        flush_memory()
        await close_http_session()
        await super().close()


bot = MoonBot(command_prefix='.', intents=intents)


def _read_token() -> str:
    # 토큰은 절대 코드에 하드코딩하지 말 것 (.env로 관리)
    token = (os.getenv("DISCORD_TOKEN") or "").strip()
    if not token:
        print("❌ 오류: DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
        print("📝 .env 파일에 DISCORD_TOKEN=your_actual_token_here 형식으로 추가해주세요.")
        raise RuntimeError("DISCORD_TOKEN 환경 변수가 설정되지 않았습니다.")
    if token == "your_discord_bot_token_here":
        print("❌ 오류: DISCORD_TOKEN이 기본값입니다.")
        print("📝 .env 파일에 실제 디스코드 봇 토큰을 입력해주세요.")
        raise RuntimeError("DISCORD_TOKEN이 유효하지 않습니다.")
    return token


if __name__ == "__main__":
    TOKEN = _read_token()
    print("✅ 토큰 로드 완료")
    print("🚀 디스코드 봇을 시작합니다...")

    # 로컬 환경에서만 터미널 명령어 입력 스레드 시작 (Railway, Render 등 서버에선 끔)
    is_server = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RENDER') or os.getenv('DYNO')
    if not is_server:
        from cogs.terminal import start_terminal_console
        start_terminal_console(bot)
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
