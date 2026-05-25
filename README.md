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
- `.워쉽가챠 [count]` - Warships gacha simulation
- `.림버스 [count]` - Limbus Company gacha simulation
- `.점메추` - Lunch recommendations

### ⚓ World of Warships
- `.워쉽전적 [플레이어명]` - Search player stats on WoWS US server

### 🎯 Advanced Features
- `.인성진단 @유저명` - Personality analysis of users
- `.부검 [query]` - Search through message history
- `.포켓몬위치 [name]` - Find Pokemon locations
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
- `.워쉽가챠 [count]` - Simulate Warships gacha pulls
- `.림버스 [count]` - Simulate Limbus Company gacha pulls
- `.점메추` - Get lunch recommendations
- `.인성진단 @유저명` - Analyze user's personality
- `.부검 [query]` - Search message history
- `.포켓몬위치 [name]` - Find Pokemon locations

### World of Warships Commands
- `.워쉽전적 [player_name]` - Look up player statistics on WoWS US server
  - Displays: Win rate, battles, damage, survival rate, etc.

### Advanced Features
- `.대화모드 [on/off]` - Toggle AI conversation mode
- `.멤버목록` - Display server member list

## 🔧 Customization

### Basic Feature Customization
- Modify the `random_messages` list in `bot.py` to add or change random messages
- Update the `target_user_ids` list to change mentioned users
- Customize game mention messages in the respective command functions

### API Integration
- The bot supports both OpenAI GPT and Google Gemini AI (Vertex: `gemini-3.5-flash` by default via `VERTEX_MODEL`)
- Configure API keys in the `.env` file for full functionality

## 📁 Project Structure

```
moon_bot/
├── bot.py                 # Main bot file
├── pokemon_data.py        # Pokemon data and functions
├── requirements.txt       # Python dependencies
├── env_example.txt       # Environment variables template
├── README.md             # This file
└── render.yaml           # Deployment configuration
```

## 🛠️ Dependencies

- `discord.py==2.3.2` - Discord API wrapper
- `python-dotenv==1.0.0` - Environment variable management
- `openai==1.3.7` - OpenAI API integration
- `google-generativeai` - Google Gemini AI integration
- `requests==2.31.0` - HTTP requests
- `aiohttp==3.9.1` - Async HTTP client

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