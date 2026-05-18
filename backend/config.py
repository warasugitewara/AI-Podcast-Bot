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
DISCORD_TOKEN            = _require("DISCORD_TOKEN")
DISCORD_GUILD_ID         = int(_require("DISCORD_GUILD_ID"))
DISCORD_VOICE_CHANNEL_ID = int(_require("DISCORD_VOICE_CHANNEL_ID"))
# TEXT_CHANNEL未設定時はVCのテキストチャット（同じID）を使用
_text_ch = _get("DISCORD_TEXT_CHANNEL_ID", "0")
DISCORD_TEXT_CHANNEL_ID  = int(_text_ch) if _text_ch and _text_ch != "0" else DISCORD_VOICE_CHANNEL_ID

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

# NVIDIA NIM 無料枠制限
# 1日あたりの最大LLMリクエスト数（超えたら生成停止→BGM/キャッシュで補完）
NIM_MAX_DAILY_REQUESTS = int(_get("NIM_MAX_DAILY_REQUESTS", "150"))
# 自動生成の最小間隔（秒）。手動リクエストはこの制限を受けない
NIM_MIN_INTERVAL_SEC   = int(_get("NIM_MIN_INTERVAL_SEC", "120"))
# LLMに渡すコンテキストの最大文字数（input tokens節約）
NIM_CONTEXT_MAX_CHARS  = int(_get("NIM_CONTEXT_MAX_CHARS", "400"))

# VC 空室時の自動停止タイムアウト（秒）。0 で無効
VC_EMPTY_TIMEOUT_SEC = int(_get("VC_EMPTY_TIMEOUT_SEC", "300"))

# 音量設定（0.0〜2.0、1.0 が原音量）
BGM_VOLUME = float(_get("BGM_VOLUME", "0.8"))
