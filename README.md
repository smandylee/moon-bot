# 🌙 Moon Bot - Discord Bot

**A feature-rich Discord bot with various entertainment and utility functions!**

## 🚀 Key Features

### 🎮 Basic Commands
- `.랜덤` - Output random Korean messages
- `.롤`, `.헬다`, `.배` - Game mention commands
- `.이미지 [URL]` - Send image embeds
- `.gpt [message]` - ChatGPT API integration
- `.@유저명 [분]동안 닥쳐` - Mute functionality
- `.뮤트상태 @유저명` - Check mute status

### 🔮 Fortune & Entertainment
- `.가챠운세` - Special fortune before gacha pulls
- `.점메추` - Lunch recommendations

### ⚓ World of Warships
- `.워쉽전적 [플레이어명]` - Search player stats on WoWS US server

### 🎯 Advanced Features
- `.부검 [query]` - Search through message history
- `.대화모드` - AI conversation mode
- `.멤버목록` - Display server member list

## 📋 Installation & Setup

### 1. Install Required Packages
```bash
pip install -r requirements.txt
```

### 2. Create Discord Bot
1. Visit [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" to create a new application
3. Go to "Bot" in the left menu
4. Click "Add Bot" to create a bot
5. Click "Reset Token" to copy the bot token

### 3. Invite Bot to Server
1. Go to "OAuth2" → "URL Generator"
2. Check "bot" in "Scopes"
3. Select the following permissions in "Bot Permissions":
   - Send Messages
   - Read Message History
   - Use Slash Commands
   - Manage Messages
   - Add Reactions
4. Use the generated URL to invite the bot to your server

### 4. Environment Variables Setup
1. Create a `.env` file based on `env_example.txt`
2. Add your bot token and API keys to the `.env` file:
```
DISCORD_TOKEN=your_actual_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here  # For ChatGPT functionality
GEMINI_API_KEY=your_gemini_api_key_here  # For Gemini AI functionality
WARGAMING_API_KEY=your_wargaming_api_key_here  # For WoWS stats (Get it from https://developers.wargaming.net/)
```

### 5. Run the Bot
```bash
python bot.py
```

## 🎮 Usage

### Basic Commands
Use these commands in your Discord channel:

- `.랜덤` - Output random Korean messages
- `.롤`, `.헬다`, `.배` - Game mentions
- `.이미지 [URL] [title]` - Send image embeds
- `.gpt [message]` - Chat with ChatGPT
- `.@유저명 [분]동안 닥쳐` - Mute a user
- `.@유저명 아봉해제` - Unmute a user
- `.뮤트상태 @유저명` - Check mute status
- `.가챠운세` - Special fortune before gacha
- `.도움말` - Show help menu

### Entertainment Commands
- `.점메추` - Get lunch recommendations
- `.부검 [query]` - Search message history

### World of Warships Commands
- `.워쉽전적 [player_name]` - Look up player statistics on WoWS US server
  - Displays: Win rate, battles, damage, survival rate, etc.

### Advanced Features
- `.대화모드 [on/off]` - Toggle AI conversation mode
- `.멤버목록` - Display server member list

## 🔧 Customization

### Basic Feature Customization
- Random messages: `random_messages` in `cogs/fun.py`
- Keyword reactions: `EXACT_REPLIES` / `CONTAINS_REPLIES` tables in `cogs/fun.py`
- Mute length limit: `MUTE_MAX_MINUTES` in `cogs/moderation.py`
- New feature: add a file under `cogs/` with an `async def setup(bot)` and list it in `EXTENSIONS` in `bot.py`

### API Integration
- The bot supports both OpenAI GPT and Google Gemini AI (Vertex: `gemini-3.8-flash` by default via `VERTEX_MODEL`)
- Configure API keys in the `.env` file for full functionality

## 📁 Project Structure

```
moon-bot/
├── bot.py              # Entry point: creates the bot and loads the cogs
├── moonbot/            # Shared core
│   ├── ai.py           #   Vertex AI (Gemini) / OpenAI clients, async helpers
│   ├── memory.py       #   Long-term memory (bot_memory.json)
│   ├── net.py          #   Shared aiohttp session, parallel channel scan
│   └── discord_utils.py
├── cogs/               # One file per feature area
│   ├── ai_chat.py      #   Mention replies, .ai, .서치챗, persona/learning, chat mode
│   ├── ai_tools.py     #   .gpt, .부검, .재판
│   ├── fun.py          #   Random lines, game pings, 점메추, 가챠운세, burger counter, keyword reactions
│   ├── quote.py        #   Quote images (right-click → Apps → 명언 만들기, or .명언)
│   ├── moderation.py   #   "@user N분동안 닥쳐" timeouts, ❌ to delete bot messages
│   ├── steam.py        #   Steam watch / price / ID lookup
│   ├── wows.py         #   World of Warships stats
│   ├── general.py      #   .도움말, .멤버목록, command error handling
│   └── terminal.py     #   Local terminal → channel messaging
├── quote_card.py       # Quote image renderer (Pillow)
├── fonts/              # Noto Sans KR (SIL OFL) for quote images
└── pr.json             # WoWS PR expected values
```

Run `.도움말` in Discord for the full command list.

## 🛠️ Dependencies

See `requirements.txt` (discord.py, google-genai, openai, aiohttp, Pillow, python-dotenv).

## 🚀 Deployment

The bot can be deployed on various platforms:
- **Local**: Run `python bot.py`
- **Cloud**: Use the provided `render.yaml` for Render deployment
- **VPS**: Upload files and run with `python bot.py`

## 📝 License

This project is distributed under the MIT License.

## 🤝 Contributing

Feel free to contribute to this project by:
1. Forking the repository
2. Creating a feature branch
3. Making your changes
4. Submitting a pull request

## 📞 Support

If you encounter any issues or have questions, please check the code comments or create an issue in the repository. 