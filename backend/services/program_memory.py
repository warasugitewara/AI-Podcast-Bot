"""
番組メモリ: ラジオ番組の継続性を管理する

- 直近トピック・BGMジャンル・エピソード数を追跡
- LLMに「前の流れ」を渡すことで文脈のある会話を生成
- 曲導入理由をルールベースで生成（NIM消費なし）
- 直近使用BGMクエリを追跡して同じ曲の繰り返しを防ぐ
"""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field

_JST = ZoneInfo("Asia/Tokyo")


@dataclass
class ProgramMemory:
    recent_topics:    list[str] = field(default_factory=list)  # 直近20トピック
    recent_genres:    list[str] = field(default_factory=list)  # 直近3BGMジャンル
    used_bgm_queries: list[str] = field(default_factory=list)  # 直近15BGMクエリ
    episode_count:    int       = 0
    _last_topic:      str       = ""

    _TOPIC_MAX     = 20
    _GENRE_MAX     = 3
    _BGM_QUERY_MAX = 15

    def add_topic(self, topic: str) -> None:
        if not topic:
            return
        self.recent_topics.append(topic)
        self.recent_topics = self.recent_topics[-self._TOPIC_MAX:]
        self._last_topic   = topic
        self.episode_count += 1

    def add_genre(self, query: str) -> None:
        """BGMクエリ文字列からジャンル概要を登録"""
        if not query:
            return
        short = " ".join(query.split()[:3])
        self.recent_genres.append(short)
        self.recent_genres = self.recent_genres[-self._GENRE_MAX:]

    def add_bgm_query(self, query: str) -> None:
        """使用済みBGMクエリを登録（ループ防止）"""
        if not query:
            return
        key = query.lower().strip()
        if key in self.used_bgm_queries:
            self.used_bgm_queries.remove(key)
        self.used_bgm_queries.append(key)
        self.used_bgm_queries = self.used_bgm_queries[-self._BGM_QUERY_MAX:]

    def is_recent_bgm_query(self, query: str) -> bool:
        """クエリが最近使われたものかどうかを返す"""
        return query.lower().strip() in self.used_bgm_queries

    def avoid_topics_hint(self) -> str:
        """LLMへの「これらのトピックを避けるよう」指示用テキスト（直近10件）"""
        if not self.recent_topics:
            return ""
        return "、".join(self.recent_topics[-10:])

    @property
    def current_mood(self) -> str:
        h = datetime.now(_JST).hour
        if   0 <= h <  6: return "深夜"
        elif 6 <= h < 10: return "朝"
        elif 10 <= h < 13: return "昼前"
        elif 13 <= h < 17: return "午後"
        elif 17 <= h < 21: return "夕方"
        else:              return "夜"

    def context_summary(self) -> str:
        """LLMプロンプトに渡す番組コンテキスト文字列"""
        parts: list[str] = [f"現在の時間帯: {self.current_mood}"]
        if self.recent_topics:
            parts.append(f"直近の話題: {', '.join(self.recent_topics[-3:])}")
        if self.recent_genres:
            parts.append(f"直近のBGMジャンル: {', '.join(self.recent_genres)}")
        if self.episode_count > 0:
            parts.append(f"今回の放送は{self.episode_count}セグメント目")
        return "\n".join(parts)

    def bgm_reason(self) -> str:
        """曲導入理由をルールベースで生成（LLM不使用）"""
        mood_phrases = {
            "深夜": "深夜なのでゆったりした曲を",
            "朝":   "朝なので爽やかな感じで",
            "昼前": "少しリラックスした曲で",
            "午後": "午後の気分に合わせて",
            "夕方": "夕方らしい雰囲気の曲を",
            "夜":   "夜なのでリラックスできる曲を",
        }
        topic_part = f"さっき{self._last_topic}の話をしたので、" if self._last_topic else ""
        mood_part  = mood_phrases.get(self.current_mood, "")
        if topic_part and mood_part:
            return topic_part + mood_part
        return mood_part


# モジュールレベルシングルトン
program_memory = ProgramMemory()
