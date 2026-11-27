"""로컬 실행 시 터미널에서 채널로 메시지 보내기."""
import discord
from discord.ext import commands
import asyncio
import threading
import queue
import time


# 터미널 스레드가 쓰는 봇 참조 (start_terminal_console / cog_load에서 설정)
bot = None

# 터미널 입력 관련 전역 변수
terminal_message_queue = queue.Queue()
terminal_input_active = False
terminal_channel_id = None

def terminal_command_handler():
    """터미널에서 봇 명령어를 입력받는 함수"""
    global terminal_input_active, terminal_channel_id
    
    print("💻 터미널 명령어 모드가 활성화되었습니다.")
    print("사용 가능한 명령어:")
    print("  - 'terminal on': 터미널 입력 모드 활성화")
    print("  - 'terminal off': 터미널 입력 모드 비활성화")
    print("  - 'dm': 특정 유저에게 DM 전송")
    print("  - 'quit': 봇 종료")
    print("  - 'help': 도움말 표시")
    
    while True:
        try:
            command = input("봇 명령어> ").strip().lower()
            
            if command == 'terminal on':
                if terminal_input_active:
                    print("❌ 이미 터미널 입력 모드가 활성화되어 있습니다!")
                    continue
                
                # 서버와 채널 선택
                if bot.guilds:
                    guild = bot.guilds[0]
                    text_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]
                    
                    if text_channels:
                        print(f"\n📋 사용 가능한 채널 목록:")
                        for i, channel in enumerate(text_channels, 1):
                            channel_type = "📢 공지" if channel.type == discord.ChannelType.news else "💬 채팅"
                            print(f"  {i}. {channel.name} ({channel_type})")
                        
                        # 채널 선택
                        while True:
                            try:
                                choice = input(f"\n채널 번호를 선택하세요 (1-{len(text_channels)}): ").strip()
                                if choice.isdigit():
                                    channel_index = int(choice) - 1
                                    if 0 <= channel_index < len(text_channels):
                                        selected_channel = text_channels[channel_index]
                                        terminal_channel_id = selected_channel.id
                                        terminal_input_active = True
                                        
                                        channel_type = "📢 공지" if selected_channel.type == discord.ChannelType.news else "💬 채팅"
                                        print(f"\n✅ 터미널 입력 모드가 활성화되었습니다!")
                                        print(f"📡 메시지가 전송될 채널: {selected_channel.name} ({channel_type})")
                                        print("💬 이제 메시지를 입력하세요 (종료하려면 'quit' 입력):")
                                        
                                        # 터미널 입력 스레드 시작
                                        terminal_thread = threading.Thread(target=terminal_input_handler, daemon=True)
                                        terminal_thread.start()
                                        
                                        # 터미널 입력 모드가 활성화된 동안 명령어 입력 루프 일시 중지
                                        while terminal_input_active:
                                            time.sleep(0.1)
                                        
                                        print("🔄 터미널 입력 모드가 종료되었습니다. 명령어 모드로 돌아갑니다.")
                                        break
                                    else:
                                        print(f"❌ 1-{len(text_channels)} 사이의 번호를 입력해주세요.")
                                else:
                                    print("❌ 숫자를 입력해주세요.")
                            except (EOFError, KeyboardInterrupt):
                                print("\n❌ 채널 선택이 취소되었습니다.")
                                break
                    else:
                        print("❌ 텍스트 채널을 찾을 수 없습니다!")
                else:
                    print("❌ 봇이 서버에 연결되지 않았습니다!")
                    
            elif command == 'terminal off':
                if not terminal_input_active:
                    print("❌ 현재 터미널 입력 모드가 켜져있지 않습니다!")
                    continue
                
                terminal_input_active = False
                terminal_channel_id = None
                print("✅ 터미널 입력 모드가 비활성화되었습니다.")
                
            elif command == 'quit':
                print("🛑 봇을 종료합니다...")
                # 봇 종료를 위한 이벤트 루프 중단
                asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
                break
                
            elif command == 'dm':
                # DM 전송 모드
                if bot.guilds:
                    guild = bot.guilds[0]
                    members = [m for m in guild.members if not m.bot]
                    
                    if members:
                        print(f"\n📋 DM 전송 가능한 유저 목록:")
                        for i, member in enumerate(members, 1):
                            print(f"  {i}. {member.name} ({member.display_name})")
                        
                        # 유저 선택
                        try:
                            choice = input(f"\n유저 번호를 선택하세요 (1-{len(members)}): ").strip()
                            if choice.isdigit():
                                user_index = int(choice) - 1
                                if 0 <= user_index < len(members):
                                    selected_user = members[user_index]
                                    print(f"\n✅ {selected_user.display_name}에게 DM 전송 모드")
                                    print("💬 메시지를 입력하세요 (종료하려면 'exit' 입력):")
                                    
                                    # DM 전송 루프
                                    while True:
                                        try:
                                            dm_message = input("DM> ").strip()
                                            if dm_message.lower() == 'exit':
                                                print("📤 DM 전송 모드 종료")
                                                break
                                            if dm_message:
                                                # DM 전송
                                                async def send_dm():
                                                    try:
                                                        await selected_user.send(dm_message)
                                                        print(f"✅ DM 전송 완료: {dm_message[:50]}...")
                                                    except discord.Forbidden:
                                                        print("❌ DM 전송 실패: 유저가 DM을 차단했거나 설정을 꺼놨습니다.")
                                                    except Exception as e:
                                                        print(f"❌ DM 전송 오류: {e}")
                                                
                                                asyncio.run_coroutine_threadsafe(send_dm(), bot.loop)
                                        except (EOFError, KeyboardInterrupt):
                                            print("\n📤 DM 전송 모드 종료")
                                            break
                                else:
                                    print(f"❌ 1-{len(members)} 사이의 번호를 입력해주세요.")
                            else:
                                print("❌ 숫자를 입력해주세요.")
                        except (EOFError, KeyboardInterrupt):
                            print("\n❌ 유저 선택이 취소되었습니다.")
                    else:
                        print("❌ DM 전송 가능한 유저가 없습니다!")
                else:
                    print("❌ 봇이 서버에 연결되지 않았습니다!")
                
            elif command == 'help':
                print("💻 사용 가능한 명령어:")
                print("  - 'terminal on': 터미널 입력 모드 활성화 (채널 선택 가능)")
                print("  - 'terminal off': 터미널 입력 모드 비활성화")
                print("  - 'dm': 특정 유저에게 DM 전송")
                print("  - 'quit': 봇 종료")
                print("  - 'help': 도움말 표시")
                
            elif command:
                print(f"❌ 알 수 없는 명령어: {command}")
                print("'help'를 입력하여 사용 가능한 명령어를 확인하세요.")
                
        except (EOFError, KeyboardInterrupt):
            print("\n🛑 봇을 종료합니다...")
            asyncio.run_coroutine_threadsafe(bot.close(), bot.loop)
            break
        except Exception as e:
            print(f"❌ 명령어 처리 오류: {e}")

def terminal_input_handler():
    """터미널에서 입력을 받아 큐에 넣는 함수"""
    global terminal_input_active
    print("💬 터미널 입력 모드가 활성화되었습니다. 메시지를 입력하세요 (종료하려면 'quit' 입력):")
    
    while terminal_input_active:
        try:
            message = input("> ")
            if message.lower() == 'quit':
                terminal_input_active = False
                print("❌ 터미널 입력 모드를 종료합니다.")
                break
            elif message.strip():  # 빈 메시지가 아닌 경우만 큐에 추가
                terminal_message_queue.put(message)
        except (EOFError, KeyboardInterrupt):
            terminal_input_active = False
            print("❌ 터미널 입력 모드를 종료합니다.")
            break

async def process_terminal_messages():
    """큐에서 메시지를 가져와 채널로 전송하는 함수"""
    global terminal_channel_id
    
    while True:
        try:
            # 큐에서 메시지 가져오기 (non-blocking)
            try:
                message = terminal_message_queue.get_nowait()
            except queue.Empty:
                # 큐가 비어있으면 잠시 대기 후 다시 시도
                await asyncio.sleep(0.5)
                continue
            
            # 채널이 설정되어 있고 봇이 준비된 경우에만 전송
            if terminal_channel_id and bot.is_ready():
                try:
                    channel = bot.get_channel(terminal_channel_id)
                    if channel:
                        await channel.send(message)
                        print(f"✅ 메시지 전송 완료: {message}")
                    else:
                        print(f"❌ 채널을 찾을 수 없습니다: {terminal_channel_id}")
                except Exception as e:
                    print(f"❌ 메시지 전송 실패: {e}")
            
        except Exception as e:
            print(f"❌ 터미널 메시지 처리 오류: {e}")
        
        # 잠시 대기
        await asyncio.sleep(0.1)


def start_terminal_console(target_bot: commands.Bot):
    """로컬 실행 시 터미널 명령어 입력 스레드를 띄운다 (bot.run 전에 호출)."""
    global bot
    bot = target_bot
    threading.Thread(target=terminal_command_handler, daemon=True).start()


class Terminal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue_task = None

    async def cog_load(self):
        global bot
        bot = self.bot
        self.queue_task = asyncio.create_task(process_terminal_messages())

    async def cog_unload(self):
        if self.queue_task is not None:
            self.queue_task.cancel()

    @commands.command(name='터미널명령어')
    async def terminal_command(self, ctx, mode: str = None):
        """터미널 입력 모드를 켜거나 끄는 명령어"""
        global terminal_input_active, terminal_channel_id
    
        if mode is None:
            await ctx.send("❌ 사용법: `.터미널명령어 on` 또는 `.터미널명령어 off`")
            return
    
        if mode.lower() == "on":
            if terminal_input_active:
                await ctx.send("❌ 이미 터미널 입력 모드가 활성화되어 있습니다!")
                return
        
            terminal_input_active = True
            terminal_channel_id = ctx.channel.id
            await ctx.send(f"💻 **터미널 입력 모드 ON!**\n이제 터미널에서 입력한 메시지가 이 채널로 전송됩니다.\n터미널에서 'quit'를 입력하면 모드가 종료됩니다.")
        
            # 터미널 입력 스레드 시작
            terminal_thread = threading.Thread(target=terminal_input_handler, daemon=True)
            terminal_thread.start()
        
        elif mode.lower() == "off":
            if not terminal_input_active:
                await ctx.send("❌ 현재 터미널 입력 모드가 켜져있지 않습니다!")
                return
        
            terminal_input_active = False
            terminal_channel_id = None
            await ctx.send("✅ **터미널 입력 모드 OFF!** 터미널에서 메시지 전송이 중단됩니다.")
        
        else:
            await ctx.send("❌ 사용법: `.터미널명령어 on` 또는 `.터미널명령어 off`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Terminal(bot))
