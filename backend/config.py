import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val or val.startswith("your_"):
        raise ValueError(f"環境変数 {key} が未設定です。.envを確認してください。")
    return val

def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)

# Discord
DISCORD_TOKEN          = _require("DISCORD_TOKEN")
DISCORD_GUILD_ID       = int(_require("DISCORD_GUILD_ID"))
DISCORD_VOICE_CHANNEL_ID = int(_require("DISCORD_VOICE_CHANNEL_ID"))
DISCORD_TEXT_CHANNEL_ID  = int(_require("DISCORD_TEXT_CHANNEL_ID"))

# LLM
LLM_API_BASE  = _get("LLM_API_BASE", "https://api.openai.com/v1")
LLM_API_KEY   = _require("LLM_API_KEY")
LLM_MODEL     = _get("LLM_MODEL", "gpt-4o-mini")

# VOICEVOX
VOICEVOX_URL        = _get("VOICEVOX_URL", "http://localhost:50021")
VOICEVOX_SPEAKER_ID = int(_get("VOICEVOX_SPEAKER_ID", "3"))

# パス
DATA_DIR   = Path(_get("DATA_DIR",   "/mnt/data/ai-podcast/data"))
LOGS_DIR   = Path(_get("LOGS_DIR",   "/mnt/data/ai-podcast/logs"))
CONFIG_DIR = Path(_get("CONFIG_DIR", "/mnt/data/ai-podcast/config"))

BGM_CACHE_DIR = DATA_DIR / "bgm_cache"
TTS_CACHE_DIR = DATA_DIR / "tts_cache"

# Web
BACKEND_API_PORT = int(_get("BACKEND_API_PORT", "8080"))
