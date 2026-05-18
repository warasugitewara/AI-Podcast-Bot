# AI Podcast Bot

A self-hosted AI podcast system that streams to Discord voice channels and can be controlled in real-time via Web UI.

## Features

- **AI Talk Generation** — LLM (OpenAI-compatible) with news/stock context injection to prevent hallucination
- **VOICEVOX TTS** — GPU-accelerated synthesis (Quadro P600 / NVIDIA Container Toolkit)
- **Auto DJ** — Automatic BGM selection from YouTube via yt-dlp
- **Discord Voice** — Direct streaming to voice channels via discord.py
- **Web UI** — Real-time control panel (Bun/Hono + SSE)
- **Cloudflare Tunnel** — Secure external access without opening inbound ports

## Hardware

| Component | Spec |
|-----------|------|
| CPU  | Xeon E3-1225 v5 |
| RAM  | 12GB |
| GPU  | NVIDIA Quadro P600 |
| SSD  | 48GB — OS, Docker, source code |
| HDD  | 512GB — cache, logs, audio files |

## Design Philosophy

- Single VM on Proxmox VE, low-resource & long-running stable operation
- No over-engineering (no Kubernetes, no Kafka)
- 4-queue parallel processing via `asyncio.Queue`
- Strict SSD/HDD write separation

## Directory Structure

```
~/ai-podcast/                   # SSD (source code)
├── backend/                    # Python: Discord, LLM, TTS, queues
│   ├── main.py
│   ├── config.py
│   ├── discord_bot.py
│   ├── api_server.py
│   ├── services/
│   │   ├── voicevox.py
│   │   ├── llm.py
│   │   ├── news_fetcher.py
│   │   └── ytdlp_service.py
│   └── workers/
│       ├── speech_worker.py
│       ├── tts_worker.py
│       ├── playback_worker.py
│       └── bgm_worker.py
├── frontend/                   # Bun/Hono: Web UI + API Gateway
│   └── src/
└── docker-compose.yml

/mnt/data/ai-podcast/           # HDD (data, large writes)
├── data/bgm_cache/
├── data/tts_cache/
└── logs/
```

## Setup

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env: set DISCORD_TOKEN, LLM_API_KEY, etc.

# 2. Start VOICEVOX container
docker compose up -d

# 3. Python virtual environment
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Start backend
python main.py

# 5. Start frontend (separate terminal)
cd ../frontend
bun install
bun run src/index.ts
```

## Audio Pipeline

```
LLM Text → VOICEVOX WAV → ffmpeg PCM → Discord Voice Channel
```

## License

MIT
