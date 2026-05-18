# AIラジオ Discord & WebUI統合システム

Discordのボイスチャンネルを配信基盤とし、Web UIからリアルタイムにコントロール可能なセルフホスト型のAIラジオシステムです。

## 機能

- **AIトーク生成** — LLM（OpenAI互換）+ ニュース・株価コンテキスト注入によるハルシネーション対策
- **VOICEVOX TTS** — GPU加速（Quadro P600 / NVIDIA Container Toolkit）
- **Auto DJ** — yt-dlpでYouTubeから自動BGM選曲・セームレス曲振り
- **Discord Voice** — discord.py でボイスチャンネルへ直接ストリーミング
- **Web UI** — Bun/Hono + SSEでリアルタイムコントロール
- **Cloudflare Tunnel** — インバウンドポート不要で安全に外部公開

## ハードウェア構成

| 項目 | スペック |
|------|---------|
| CPU  | Xeon E3-1225 v5 |
| RAM  | 12GB |
| GPU  | NVIDIA Quadro P600 |
| SSD  | 48GB（OS・Docker・ソースコード） |
| HDD  | 512GB（キャッシュ・ログ・音声ファイル） |

## 設計思想

- Proxmox VE上の単一VM、低リソース・長期安定稼働
- Over-engineering排除（Kubernetes・Kafka等は使わない）
- `asyncio.Queue` による4キュー並列処理
- SSD/HDD書き込み先の厳格な分離

## ディレクトリ構成

```
~/ai-radio/                     # SSD（ソースコード）
├── backend/                    # Python: Discord, LLM, TTS, Queue
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

/mnt/data/ai-radio/             # HDD（データ・大容量書き込み）
├── data/bgm_cache/
├── data/tts_cache/
└── logs/
```

## セットアップ

```bash
# 1. 環境変数設定
cp .env.example .env
# .envを編集してDISCORD_TOKEN, LLM_API_KEY等を設定

# 2. VOICEVOXコンテナ起動
docker compose up -d

# 3. Python仮想環境
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. バックエンド起動
python main.py

# 5. フロントエンド（別ターミナル）
cd ../frontend
bun install
bun run src/index.ts
```

## オーディオパイプライン

```
LLM Text → VOICEVOX WAV → ffmpeg PCM → Discord Voice Channel
```

## ライセンス

MIT
