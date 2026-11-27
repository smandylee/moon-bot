"""명언 짤 만들기 (우클릭 → 앱 → 명언 만들기, 또는 답장으로 .명언)."""
import asyncio
import io
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from quote_card import clean_quote_text, render_quote_card

QUOTE_REMOVE_CUSTOM_ID = 'moonbot:quote:remove'
_QUOTE_FILENAME = re.compile(r'quote_(\d+)_(\d+)\.png')


class QuoteRemoveView(discord.ui.View):
    """명언 짤 삭제 버튼. 재시작 후에도 동작하도록 고정 custom_id를 쓰고,
    누가 지울 수 있는지는 첨부파일 이름(quote_<당사자>_<만든사람>.png)에서 읽는다."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='명언 삭제', emoji='🗑️', style=discord.ButtonStyle.danger,
                       custom_id=QUOTE_REMOVE_CUSTOM_ID)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed_ids = set()
        for attachment in interaction.message.attachments:
            match = _QUOTE_FILENAME.fullmatch(attachment.filename)
            if match:
                allowed_ids.update(int(group) for group in match.groups())

        perms = getattr(interaction.user, 'guild_permissions', None)
        can_manage = bool(perms and perms.manage_messages)
        if interaction.user.id not in allowed_ids and not can_manage:
            await interaction.response.send_message(
                "명언 당사자나 만든 사람만 지울 수 있어 ㅋㅋ", ephemeral=True)
            return

        await interaction.message.delete()


async def build_quote_file(target: discord.Message, invoker_id: int) -> Optional[discord.File]:
    """메시지로 명언 짤 파일을 만든다. 글자가 없으면 None."""
    text = clean_quote_text(target.clean_content)
    if not text:
        return None

    author = target.author
    try:
        avatar_bytes = await author.display_avatar.replace(size=512, format='png').read()
    except Exception as avatar_error:
        print(f"명언 아바타 로드 실패: {avatar_error}")
        avatar_bytes = None

    # Pillow 렌더링은 CPU 작업이라 이벤트 루프를 막지 않게 스레드에서 돌린다
    png = await asyncio.to_thread(
        render_quote_card, text, author.display_name, author.name, avatar_bytes)
    return discord.File(io.BytesIO(png), filename=f'quote_{author.id}_{invoker_id}.png')


def _quote_caption(target: discord.Message) -> str:
    return f"[원본 메시지]({target.jump_url})"


async def make_quote_context(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(thinking=True)
    try:
        quote_file = await build_quote_file(message, interaction.user.id)
    except Exception as render_error:
        print(f"명언 생성 오류: {render_error}")
        await interaction.followup.send("❌ 명언 짤 만들다가 오류났어", ephemeral=True)
        return

    if quote_file is None:
        await interaction.followup.send("글자가 있는 메시지만 명언으로 만들 수 있어", ephemeral=True)
        return

    await interaction.followup.send(
        _quote_caption(message), file=quote_file, view=QuoteRemoveView(),
        allowed_mentions=discord.AllowedMentions.none())


class Quote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 컨텍스트 메뉴는 Cog 메서드로 못 만들어서 따로 등록/해제한다
        self.context_menu = app_commands.ContextMenu(name='명언 만들기', callback=make_quote_context)

    async def cog_load(self):
        self.bot.tree.add_command(self.context_menu)
        # 재시작 후에도 예전 명언 짤의 삭제 버튼이 동작하도록 등록
        self.bot.add_view(QuoteRemoveView())

    async def cog_unload(self):
        self.bot.tree.remove_command(self.context_menu.name, type=self.context_menu.type)

    @commands.command(name='명언')
    async def make_quote_command(self, ctx):
        """답장한 메시지를 명언 짤로 만든다."""
        ref = ctx.message.reference
        if ref is None or ref.message_id is None:
            await ctx.send("명언으로 만들 메시지에 **답장**하면서 `.명언` 쳐줘\n(메시지 우클릭 → 앱 → 명언 만들기 도 됨)")
            return

        target = ref.resolved if isinstance(ref.resolved, discord.Message) else None
        if target is None:
            try:
                target = await ctx.channel.fetch_message(ref.message_id)
            except discord.NotFound:
                await ctx.send("원본 메시지를 못 찾겠어 (삭제됐나?)")
                return

        async with ctx.typing():
            quote_file = await build_quote_file(target, ctx.author.id)

        if quote_file is None:
            await ctx.send("글자가 있는 메시지만 명언으로 만들 수 있어")
            return

        await ctx.send(
            _quote_caption(target), file=quote_file, view=QuoteRemoveView(),
            allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(Quote(bot))
