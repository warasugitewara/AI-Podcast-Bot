"""
VOICEVOXサービス層: audio_query + synthesis でWAV生成
"""
import asyncio
import hashlib
import logging
from pathlib import Path
import aiohttp

from config import VOICEVOX_URL, VOICEVOX_SPEAKER_ID, TTS_CACHE_DIR

log = logging.getLogger("voicevox")

# VOICEVOXはシングルスレッド処理のため並列リクエストで500エラーが発生する。
# モジュールレベルのセマフォで全リクエストを直列化する。
_vv_sem = asyncio.Semaphore(1)


class VoicevoxService:
    def __init__(self, url: str = VOICEVOX_URL, speaker_id: int = VOICEVOX_SPEAKER_ID):
        self.url = url.rstrip("/")
        self.speaker_id = speaker_id
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, text: str, speaker_id: int) -> Path:
        key = hashlib.md5(f"{speaker_id}:{text}".encode()).hexdigest()
        return TTS_CACHE_DIR / f"{key}.wav"

    async def synthesize(
        self,
        text: str,
        speaker_id: int | None = None,
        speed: float = 1.0,
        pitch: float = 0.0,
        _retries: int = 3,
    ) -> Path:
        """テキストをWAVファイルに変換してPathを返す。キャッシュヒット時は即座に返す。
        500エラー時は最大 _retries 回リトライする（1秒間隔）。"""
        sid = speaker_id or self.speaker_id
        cached = self._cache_path(text, sid)
        if cached.exists():
            log.debug(f"TTSキャッシュヒット: {cached.name}")
            return cached

        last_err: Exception | None = None
        for attempt in range(_retries):
            try:
                async with _vv_sem:
                    async with aiohttp.ClientSession() as session:
                        # Step1: audio_query
                        async with session.post(
                            f"{self.url}/audio_query",
                            params={"text": text, "speaker": sid},
                        ) as resp:
                            resp.raise_for_status()
                            query = await resp.json()

                        query["speedScale"] = speed
                        query["pitchScale"] = pitch

                        # Step2: synthesis
                        async with session.post(
                            f"{self.url}/synthesis",
                            params={"speaker": sid},
                            json=query,
                            headers={"Content-Type": "application/json"},
                        ) as resp:
                            resp.raise_for_status()
                            wav_data = await resp.read()

                cached.write_bytes(wav_data)
                log.info(f"TTS生成完了: {len(text)}文字 → {cached.name}")
                return cached

            except Exception as e:
                last_err = e
                if attempt < _retries - 1:
                    log.warning(f"VOICEVOX 500 retry {attempt + 1}/{_retries} (speaker={sid}): {e}")
                    await asyncio.sleep(1.0)

        raise last_err  # type: ignore

    async def get_speakers(self) -> list[dict]:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.url}/speakers") as resp:
                resp.raise_for_status()
                return await resp.json()
