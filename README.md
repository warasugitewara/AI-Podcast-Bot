# 🎙️ AI Podcast Bot

Discord VC に自動配信するセルフホスト型 AI ラジオシステム。  
LLM が台本を書き、VOICEVOX キャラクターが喋り、BGM が流れる、ほぼ全自動のポッドキャスト Bot です。

> **English summary:** A self-hosted AI radio bot for Discord. LLM generates dialogue scripts, VOICEVOX synthesizes multi-character voices, and yt-dlp plays BGM — all automatically. Includes health monitoring with Uptime Kuma push integration and a real-time Web UI.

---

## ✨ 主な機能

| 機能 | 詳細 |
|------|------|
| 🤖 **LLM 台本生成** | NVIDIA NIM (Llama-3.3-70B) で複数キャラの対話台本を自動生成 |
| 🎤 **マルチキャラ TTS** | VOICEVOX 13キャラ対応。複数キャストから番組ごとに選択可能 |
| 🎵 **Auto DJ** | YouTube Music トレンド・時間帯別・プリセットプールから自動選曲 |
| 📰 **ニュース連動** | RSS/API で取得した最新情報を [FACTS] として LLM に注入（ハルシネーション抑制）|
| 🕐 **時間帯認識** | JST 時刻を常時参照し、朝・昼・夕・夜でトーク内容と BGM を自動調整 |
| 🔤 **英語発音辞書** | 英語アーティスト名・技術用語を自動でカタカナ変換してから TTS に投入 |
| 🧠 **番組メモリ** | 直近トピック・BGM クエリを記録してループ・繰り返しを自動回避 |
| 🎚️ **話速 per モード** | ニュース=0.93倍（落ち着き）/ 雑談=1.05倍（テンポよく）を自動切り替え |
| 🌡️ **temperature per モード** | ニュース=0.4 / 雑談=0.8 / 曲振り=0.6 で hallucination と面白さを両立 |
| 🎤 **曲アナウンス** | 曲前にキャラが曲名を紹介。30%確率で曲後コメントも挿入 |
| 🔇 **BGM フィルタリング** | AI生成曲・ゲームBGM総集編・効果音・インスト等を除外して選曲品質を維持 |
| 🚶 **無人自動停止** | VC が空室になった後、一定時間で放送を自動一時停止（`VC_EMPTY_TIMEOUT_SEC` で調整）|
| 🎧 **BGM スキップ** | `/skip` コマンドで再生中のBGMだけをスキップ（トークは中断しない）|
| 🔗 **nowplaying** | `/nowplaying` で現在再生中の曲名と YouTube URL を表示 |
| 🖥️ **Web UI** | Bun/Hono + SSE によるリアルタイム管理画面（手動リクエスト・キャスト切り替え等）|
| 🌡️ **ヘルス監視** | 6サブシステム並列監視（`GET /health`）+ Uptime Kuma Push 統合 |
| 🌐 **Cloudflare Tunnel** | ポート開放不要でブラウザから外部アクセス可能 |

---

## 🏗️ アーキテクチャ

```
Discord VCユーザー
      │
      ▼
[Discord Bot (discord.py)]
      │
      ├─── SpeechWorker ──→ LLM (NVIDIA NIM) ──→ tts_queue
      │         │                                      │
      │    ContentScheduler                       TtsWorker
      │    (番組進行管理)                         (VOICEVOX TTS)
      │                                               │
      ├─── BgmWorker ─────→ yt-dlp (BGM取得) ──┐     │
      │    (トレンド/時間帯/                    ▼     ▼
      │     プリセット選曲)             playback_queue
      │                                       │
      ├─────────────────────────────── PlaybackWorker
      │                                 (ffmpeg → Discord VC)
      │
      ├─── HealthManager ──→ 6サブシステム並列監視
      │                      │
      └─── UptimeWorker ─────┘──→ Uptime Kuma Push
```

**4キュー並列処理**（asyncio）:
`tts_queue` → `playback_queue` ← `bgm_prefetch_queue` ← `status_queue`

---

## 🎮 スラッシュコマンド

| コマンド | 説明 |
|---------|------|
| `/start` | 放送を開始する |
| `/stop` | 現在の再生を停止する |
| `/skip` | 再生中の BGM をスキップ（トークは中断しない） |
| `/topic <text>` | 指定したトピックでトークを即座に生成 |
| `/music <query>` | 曲名・アーティスト名でリクエスト（キュー追加） |
| `/nowplaying` | 現在再生中の曲名と YouTube URL を表示（`/np` でも可） |
| `/volume [0-200]` | BGM 音量を変更（省略で現在値表示）|
| `/cast [name]` | キャストを変更（省略で現在キャスト表示）|
| `/casts` | 利用可能なキャスト一覧を表示 |
| `/chars` | キャラクター一覧を表示 |
| `/shuffle` | ランダムにキャストを変更 |
| `/otp` | Web UI アクセス用ワンタイムパスワードを DM で送信 |

> ⚠️ `/music` でリクエストした曲はキューに追加されます。トークの合間に通常どおり流れます（即時割り込みなし）。

---

## 🌡️ ヘルス監視

`GET /health` エンドポイントで 6 サブシステムの状態を JSON で返します。

```json
{
  "status": "up",
  "score": "6/6",
  "discord":   { "ok": true, "detail": "VC connected" },
  "voicevox":  { "ok": true, "detail": "vlatest" },
  "nim":       { "ok": true, "detail": "last ok 2m ago" },
  "queue":     { "ok": true, "detail": "tts=3 playback=1" },
  "playback":  { "ok": true, "detail": "last 0m ago" },
  "storage":   { "ok": true, "detail": "0.8% (/mnt/data/ai-podcast/data)" },
  "timestamp": "2026-06-03T03:48:27.562519+00:00"
}
```

[Uptime Kuma](https://github.com/louislam/uptime-kuma) の Push Monitor に対応しており、  
`.env` の `UPTIME_KUMA_PUSH_URL` を設定するだけで 60 秒ごとに自動通知します。  
Web UI のヘルスパネルからも 30 秒ごとにリアルタイム確認できます。

---

## 🎭 キャラクター一覧（13名）

| ID | 名前 | 役割 | 声優 (VOICEVOX) |
|----|------|------|----------------|
| haru | ハル | MC・進行役 | 春日部つむぎ |
| ao | アオ | 解説役 | 青山龍星 |
| yuki | ユキ | コメンテーター | 四国めたん |
| sora | ソラ | フリートーカー | ずんだもん |
| rei | レイ | まとめ役 | 雨晴はう |
| ken | ケン | 熱血コメンテーター | 玄野武宏（喜び）|
| nana | ナナ | 応援・ポジティブ | もち子さん（喜び）|
| zona | ゾナ | 実況・テンポ担当 | 青山龍星（熱血）|
| sayo | サヨ | クール・哲学担当 | 小夜/SAYO |
| shiro | シロ | 天然・ボケ担当 | 玄野武宏（ツンギレ）|
| nia | ニア | 不思議・詩的担当 | 四国めたん（セクシー）|
| maron | マロン | 癒し・聞き上手 | ずんだもん（あまあま）|
| nurse | ナース | クール・理知的 | 玄野武宏（悲しみ）|

複数キャラを「キャスト」として組み合わせ、Web UI でリアルタイム切り替え可能。

---

## 🎵 BGM 選曲ロジック

曲リクエストがない場合、以下の比率でランダム選曲:

```
10% — YouTube Music トレンド（日本）
10% — YouTube Music トレンド（US / KR / GB）
15% — 時間帯別クエリ（朝=元気系、夜=chill系、深夜=ambient等）
65% — プリセットプール（約100クエリ、ジャンル多様）
        ※ 直近15件を除外してリピート回避
```

---

## 🖥️ ハードウェア構成

| パーツ | スペック |
|--------|---------|
| CPU | Intel Xeon E3-1225 v5 |
| RAM | 12 GB |
| GPU | NVIDIA Quadro P600 (VOICEVOX GPU アクセラレーション) |
| SSD | 48 GB — OS・Docker・ソースコード |
| HDD | 512 GB — BGM/TTS キャッシュ・ログ |

Proxmox VE 上の単一 VM で長期安定稼働。Kubernetes 不要のシンプル構成。

---

## 📁 ディレクトリ構成

```
~/ai-podcast/                        # SSD（ソースコード）
├── backend/
│   ├── main.py                      # エントリポイント・全ワーカー起動
│   ├── config.py                    # 環境変数ローダー
│   ├── discord_bot.py               # Discord イベントハンドラ・スラッシュコマンド
│   ├── api_server.py                # REST API (aiohttp) + GET /health
│   ├── services/
│   │   ├── voicevox.py              # VOICEVOX TTS（セマフォ直列化・リトライ）
│   │   ├── llm.py                   # NVIDIA NIM 呼び出し・台本生成・日次カウンター
│   │   ├── health_manager.py        # 6サブシステム並列ヘルス監視
│   │   ├── character_manager.py     # 13キャラ・キャスト管理
│   │   ├── program_memory.py        # 番組メモリ（トピック/BGMループ防止・JST時刻）
│   │   ├── pronunciation.py         # 英語→カタカナ発音辞書
│   │   ├── news_fetcher.py          # ニュース取得（RSS/API）
│   │   ├── ytdlp_service.py         # yt-dlp ラッパー（BGMフィルタリング含む）
│   │   └── ytmusic_service.py       # YouTube Music トレンド取得
│   └── workers/
│       ├── speech_worker.py         # メインループ・LLM→TTS 投入
│       ├── tts_worker.py            # VOICEVOX WAV 生成（発音前処理付き）
│       ├── bgm_worker.py            # BGM 取得・曲アナウンス・曲後コメント
│       ├── playback_worker.py       # ffmpeg → Discord VC 再生
│       └── uptime_worker.py         # Uptime Kuma Push（60秒ごと）
├── frontend/                        # Bun/Hono + SSE Web UI（ヘルスパネル含む）
│   └── src/
├── docker-compose.yml               # VOICEVOX コンテナ定義
└── .env                             # 環境変数（要作成）

/mnt/data/ai-podcast/                # HDD（大容量データ）
├── data/bgm_cache/                  # yt-dlp ダウンロード済み音声
├── data/tts_cache/                  # VOICEVOX 生成済み WAV
└── logs/                            # サービスログ
```

---

## ⚙️ セットアップ

### 1. 環境変数を設定

```bash
cp .env.example .env
```

`.env` に以下を記述:

```env
# Discord
DISCORD_TOKEN=your_discord_bot_token
DISCORD_GUILD_ID=123456789
DISCORD_VOICE_CHANNEL_ID=123456789
DISCORD_TEXT_CHANNEL_ID=0              # 省略時は VOICE_CHANNEL_ID と同じ

# LLM (NVIDIA NIM または OpenAI 互換 API)
LLM_API_BASE=https://integrate.api.nvidia.com/v1
LLM_API_KEY=your_nim_api_key
LLM_MODEL=meta/llama-3.3-70b-instruct
NIM_MAX_DAILY_REQUESTS=150             # 無料枠制限
NIM_MIN_INTERVAL_SEC=120               # 最小生成間隔(秒)

# VOICEVOX
VOICEVOX_URL=http://localhost:50021

# データ保存先（SSD/HDD 分離）
DATA_DIR=/mnt/data/ai-podcast/data
LOGS_DIR=/mnt/data/ai-podcast/logs
CONFIG_DIR=/mnt/data/ai-podcast/config

# Web UI
BACKEND_API_PORT=8080
DASHBOARD_URL=https://your-tunnel.trycloudflare.com

# VC 無人自動停止（秒）
VC_EMPTY_TIMEOUT_SEC=300

# BGM 音量（0.0〜2.0）
BGM_VOLUME=0.8

# Uptime Kuma Push Monitor URL（省略可）
# 例: https://your-uptime-kuma.example.com/api/push/xxxxx
UPTIME_KUMA_PUSH_URL=
```

### 2. VOICEVOX 起動

```bash
docker compose up -d
```

### 3. Python 環境構築

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. バックエンド起動

```bash
# 開発時
python main.py

# 本番（systemd）
sudo systemctl enable --now ai-podcast-backend
```

### 5. フロントエンド起動

```bash
cd frontend
bun install
bun run src/index.ts
```

---

## 🔊 音声パイプライン

```
LLM 台本 → 英語発音変換 → VOICEVOX WAV → playback_queue
                                                  │
BGM (yt-dlp) ──────────────────────────────────→ │
                                                  ▼
                                          PlaybackWorker
                                          (ffmpeg PCM → Discord VC)
```

- TTS と BGM は `playback_queue` で順序管理。同時再生なし。
- VOICEVOX は `asyncio.Semaphore(1)` で直列化 + 3 回自動リトライ。

---

## 📜 ライセンス

MIT

