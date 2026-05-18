"""
キャラクター・キャスト管理

各キャラクターは「名前・役割・話し方スタイル・VOICEVOXスピーカー」を持つ。
キャストはキャラクターの組み合わせ（2〜4人）。
"""
from __future__ import annotations
from dataclasses import dataclass
import random
import logging

log = logging.getLogger("character_manager")


# ─── キャラクター定義 ─────────────────────────────────────────
@dataclass(frozen=True)
class Character:
    id:           str
    name:         str
    role:         str   # 進行役など
    style:        str   # LLMプロンプトに渡す話し方の指示
    speaker_id:   int   # VOICEVOX スピーカーID
    speaker_name: str   # 表示用スピーカー名


CHARACTERS: dict[str, Character] = {
    "haru": Character(
        id="haru", name="ハル", role="MC・進行役",
        style=(
            "明るく積極的なMC。好奇心旺盛で視聴者目線の質問が得意。"
            "テンポよく進行し「〜ですね！」「面白い！」「それってどういうこと？」をよく使う。"
        ),
        speaker_id=8, speaker_name="春日部つむぎ",
    ),
    "ao": Character(
        id="ao", name="アオ", role="解説役",
        style=(
            "冷静で論理的な解説者。難しい内容を噛み砕く。"
            "「実は〜」「つまりこういうことで」「技術的には〜」が口癖。"
        ),
        speaker_id=13, speaker_name="青山龍星",
    ),
    "yuki": Character(
        id="yuki", name="ユキ", role="コメンテーター",
        style=(
            "鋭い視点と辛口コメントが持ち味のコメンテーター。"
            "「でも〜」「正直〜」「それって〜じゃないですか？」が口癖。短くキレよく話す。"
        ),
        speaker_id=2, speaker_name="四国めたん",
    ),
    "sora": Character(
        id="sora", name="ソラ", role="フリートーカー",
        style=(
            "自由奔放で予想外の発想が得意なフリートーカー。"
            "「なんか〜みたいな？」「え、それってさ〜」で場を和ませる。突拍子もない例えが持ち味。"
        ),
        speaker_id=3, speaker_name="ずんだもん",
    ),
    "rei": Character(
        id="rei", name="レイ", role="まとめ役",
        style=(
            "穏やかで共感力が高いまとめ役。話の流れを整理して締める。"
            "「〜ということですね」「なるほど〜」「聴いているみなさんも〜」をよく使う。"
        ),
        speaker_id=10, speaker_name="雨晴はう",
    ),
}


# ─── キャスト定義 (キャラの組み合わせ) ─────────────────────────
CASTS: dict[str, dict] = {
    "standard": {
        "label": "定番コンビ",
        "chars": ["haru", "ao"],
        "desc":  "MCと解説者の王道スタイル",
    },
    "debate": {
        "label": "議論トリオ",
        "chars": ["haru", "ao", "yuki"],
        "desc":  "3人で多角的に深掘り",
    },
    "casual": {
        "label": "バラエティコンビ",
        "chars": ["haru", "sora"],
        "desc":  "軽めでテンポよく",
    },
    "serious": {
        "label": "深掘りトリオ",
        "chars": ["rei", "ao", "yuki"],
        "desc":  "落ち着いてしっかり分析",
    },
    "variety": {
        "label": "バラエティトリオ",
        "chars": ["haru", "sora", "yuki"],
        "desc":  "賑やかで予想外の展開",
    },
    "full": {
        "label": "フルキャスト",
        "chars": ["haru", "ao", "yuki", "sora"],
        "desc":  "全員集合・盛り上がり重視",
    },
}


# ─── マネージャー ────────────────────────────────────────────
class CharacterManager:
    def __init__(self):
        name = random.choice(list(CASTS.keys()))
        self._cast_name   = name
        self._cast        = CASTS[name]
        self._custom: list[Character] | None = None
        log.info(
            f"初期キャスト: {self._cast['label']} "
            f"[{', '.join(CHARACTERS[c].name for c in self._cast['chars'])}]"
        )

    # ─ 取得 ──────────────────────────────────────────────────
    def active(self) -> list[Character]:
        """現在アクティブなキャラクター一覧を返す"""
        if self._custom is not None:
            return self._custom
        return [CHARACTERS[c] for c in self._cast["chars"]]

    def speaker_id_for(self, name: str) -> int | None:
        """キャラクター名からスピーカーIDを返す"""
        for c in self.active():
            if c.name == name:
                return c.speaker_id
        return None

    @property
    def cast_name(self) -> str:
        return self._cast_name

    # ─ 変更 ──────────────────────────────────────────────────
    def shuffle(self) -> dict:
        """現在と異なるキャストをランダム選択"""
        others = [k for k in CASTS if k != self._cast_name]
        return self.set_cast(random.choice(others or list(CASTS.keys())))

    def set_cast(self, name: str) -> dict | None:
        if name not in CASTS:
            return None
        self._cast_name = name
        self._cast      = CASTS[name]
        self._custom    = None
        chars = [CHARACTERS[c].name for c in self._cast["chars"]]
        log.info(f"キャスト変更: {self._cast['label']} {chars}")
        return self._cast

    def set_custom(self, char_ids: list[str]) -> list[Character] | None:
        """任意のキャラ組み合わせを設定"""
        chars = []
        for cid in char_ids:
            if cid not in CHARACTERS:
                return None
            chars.append(CHARACTERS[cid])
        self._custom    = chars
        self._cast_name = "custom"
        log.info(f"カスタムキャスト: {[c.name for c in chars]}")
        return chars

    def override_speaker(self, char_id: str, speaker_id: int) -> bool:
        """特定キャラのスピーカーIDを上書き（再起動でリセット）"""
        if char_id not in CHARACTERS:
            return False
        # frozenなのでオブジェクト置き換え
        original = CHARACTERS[char_id]
        CHARACTERS[char_id] = Character(  # type: ignore[index]
            id=original.id, name=original.name,
            role=original.role, style=original.style,
            speaker_id=speaker_id, speaker_name=f"カスタム(ID:{speaker_id})",
        )
        log.info(f"{original.name} のスピーカーを ID:{speaker_id} に変更")
        return True

    # ─ 表示 ──────────────────────────────────────────────────
    def status_embed(self) -> str:
        chars = self.active()
        cast_label = self._cast.get("label", "カスタム")
        lines = [f"🎭 **キャスト: {cast_label}**"]
        for c in chars:
            lines.append(f"  **{c.name}**（{c.role}）— {c.speaker_name} (ID:{c.speaker_id})")
        return "\n".join(lines)

    @staticmethod
    def list_casts_text() -> str:
        lines = ["📋 **利用可能なキャスト**"]
        for key, cast in CASTS.items():
            chars = " + ".join(CHARACTERS[c].name for c in cast["chars"])
            lines.append(f"  `{key}` — **{cast['label']}**: {chars}\n    └ {cast['desc']}")
        return "\n".join(lines)

    @staticmethod
    def list_chars_text() -> str:
        lines = ["👤 **キャラクター一覧**"]
        for c in CHARACTERS.values():
            lines.append(
                f"  `{c.id}` — **{c.name}**（{c.role}）\n"
                f"    🗣 {c.speaker_name} (ID:{c.speaker_id})\n"
                f"    💬 {c.style[:40]}…"
            )
        return "\n".join(lines)


# シングルトン
character_manager = CharacterManager()
