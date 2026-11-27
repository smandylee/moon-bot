"""뮤트(타임아웃)와 봇 메시지 삭제."""
import datetime
import re

import discord
from discord.ext import commands

from moonbot.discord_utils import is_bot_mentioned

# 장난용이라 누구나 쓸 수 있되, 길이는 제한한다
MUTE_MAX_MINUTES = 10
_MUTE_PATTERN = re.compile(r'<@!?(\d+)>\s*(\d+)\s*분\s*동안\s*닥쳐')
_UNMUTE_PATTERN = re.compile(r'<@!?(\d+)>\s*아봉해제')
# 예전 방식(역할 부여)으로 뮤트된 사람을 풀어주기 위해 남겨둔다
LEGACY_MUTE_ROLE_NAME = "뮤트"


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """반응이 추가되었을 때 실행되는 이벤트"""
        # 봇이 아닌 사용자가 ❌ 이모지로 반응했을 때
        if user != self.bot.user and str(reaction.emoji) == "❌":
            # 봇이 보낸 메시지인지 확인
            if reaction.message.author == self.bot.user:
                try:
                    # 메시지 삭제
                    await reaction.message.delete()
                    print(f"🗑️ {user.name}님이 봇 메시지를 삭제했습니다.")
                except Exception as e:
                    print(f"❌ 메시지 삭제 실패: {e}")
    @commands.Cog.listener('on_message')
    async def on_mute_phrase(self, message: discord.Message):
        """'@유저 N분동안 닥쳐' → 디스코드 타임아웃, '@유저 아봉해제' → 해제."""
        if message.guild is None or message.author == self.bot.user:
            return
        if message.content.startswith('.') or is_bot_mentioned(self.bot, message):
            return

        mute_match = _MUTE_PATTERN.match(message.content)
        if mute_match:
            await self._mute(message, int(mute_match.group(1)), int(mute_match.group(2)))
            return
        unmute_match = _UNMUTE_PATTERN.match(message.content)
        if unmute_match:
            await self._unmute(message, int(unmute_match.group(1)))

    async def _mute(self, message: discord.Message, user_id: int, minutes: int):
        target = message.guild.get_member(user_id)
        if target is None:
            return
        if minutes < 1:
            await message.channel.send("❌ 1분 이상으로 해줘")
            return
        note = ""
        if minutes > MUTE_MAX_MINUTES:
            minutes = MUTE_MAX_MINUTES
            note = f" (최대 {MUTE_MAX_MINUTES}분이라 줄였음)"

        try:
            # 타임아웃은 디스코드가 알아서 풀어주고, 채팅·음성 말하기를 모두 막는다
            await target.timeout(datetime.timedelta(minutes=minutes),
                                 reason=f"{message.author} 요청: {minutes}분 닥쳐")
        except discord.Forbidden:
            await message.channel.send(f"❌ {target.display_name}은(는) 봇보다 높아서 못 닥치게 함 (관리자/상위 역할)")
            return
        except discord.HTTPException as e:
            await message.channel.send(f"❌ 뮤트 중 오류가 발생했습니다: {e}")
            return
        await message.channel.send(f"🔇 {target.mention}을(를) {minutes}분간 닥치게 했습니다.{note}")

    async def _unmute(self, message: discord.Message, user_id: int):
        target = message.guild.get_member(user_id)
        if target is None:
            return
        legacy_role = discord.utils.get(message.guild.roles, name=LEGACY_MUTE_ROLE_NAME)
        has_legacy_role = legacy_role is not None and legacy_role in target.roles
        if not target.is_timed_out() and not has_legacy_role:
            await message.channel.send(f"❌ {target.mention}은(는) 뮤트 상태가 아닙니다.")
            return
        try:
            if target.is_timed_out():
                await target.timeout(None, reason="아봉해제")
            if has_legacy_role:
                await target.remove_roles(legacy_role, reason="아봉해제")
        except discord.HTTPException as e:
            await message.channel.send(f"❌ 언뮤트 중 오류가 발생했습니다: {e}")
            return
        await message.channel.send(f"🔊 {target.mention}의 뮤트가 해제되었습니다.")

    @commands.command(name='뮤트상태')
    async def mute_status(self, ctx, user: discord.Member):
        """유저의 뮤트(타임아웃) 상태를 확인하는 명령어"""
        if user.is_timed_out():
            until = discord.utils.format_dt(user.timed_out_until, 'R')
            await ctx.send(f"🔇 **{user.display_name}** 뮤트 중 — {until} 풀림")
        else:
            await ctx.send(f"🔊 **{user.display_name}** 뮤트 안 됨")


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
