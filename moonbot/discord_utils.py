"""여러 Cog에서 같이 쓰는 디스코드 헬퍼."""
import discord
from discord.ext import commands


def is_bot_mentioned(bot: commands.Bot, message: discord.Message) -> bool:
    """봇을 직접 불렀는지 (@everyone 제외). 이런 메시지는 AI 대화가 받고 다른 반응은 쉰다."""
    return bot.user is not None and bot.user.mentioned_in(message) and not message.mention_everyone


def strip_bot_mention(bot: commands.Bot, content: str) -> str:
    return content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
