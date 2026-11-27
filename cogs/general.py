"""도움말, 멤버목록, 공통 에러 처리."""
import sys
import traceback

from discord.ext import commands


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='멤버목록')
    async def member_list(self, ctx):
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

    @commands.command(name='도움말')
    async def help_command(self, ctx):
        """도움말을 출력하는 명령어"""
        help_text = """
**🎮 사용 가능한 명령어들:**

`.랜덤` - 랜덤하게 싹바가지 없이 말한다 
`.점메추` - 오늘 점심 뭐 먹을지 추천해줌
`.햄버거` - 권문 햄버거/배달 시킨 횟수랑 총액 정산
`.명언` - 메시지에 답장하면서 치면 명언 짤로 만들어줌 (우클릭 → 앱 → 명언 만들기 도 됨)
`.이미지 [URL] [제목]` - 이미지를 임베드로 보내기
`.gpt [메시지]` - 핑프년아 니가 검색해(보류)
`.부검 [검색어]` - 키워드 또는 상황으로 메시지 검색 (개유용함)
`.스팀아이디 [프로필URL/바니티ID/SteamID64]` - 감시용 SteamID64 조회
`.스팀가격 [게임명]` - 스팀 게임 한국 가격/할인율 조회 (줄임말 OK: 사펑, 발더스, 헬다)
`.스팀감시상태` - Steam 감시 설정 상태 확인
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

**🎯 특별 기능:**
특정 유저가 "ㅇㄲㄴ"을 입력하면 웹훅 임베드로 이미지가 출력됩니다!


```
    """
        await ctx.send(help_text)
    @commands.Cog.listener()
    async def on_ready(self):
        print(f"🎯 {self.bot.user}가 로그인했습니다!")
        print(f"📡 {len(self.bot.guilds)}개 서버에 연결됨")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return  # '...' 같은 평범한 채팅
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ 진정해. {error.retry_after:.0f}초 뒤에 다시 써", delete_after=5)
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"사용법: `.{ctx.command.qualified_name} {ctx.command.signature}`")
            return
        if isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            await ctx.send("❌ 그런 유저 없음. `@멘션`으로 해줘")
            return
        # 나머지는 discord.py 기본 동작처럼 콘솔에 트레이스백을 남긴다
        print(f"명령어 오류 (.{ctx.command}):", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
