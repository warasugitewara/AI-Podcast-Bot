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
    # ─── 既存キャラ ─────────────────────────────────────────
    "haru": Character(
        id="haru", name="ハル", role="MC・進行役",
        style=(
            "明るく積極的なMC。好奇心旺盛で視聴者目線の質問が得意。"
            "テンポよく話を進め、話題を掘り下げる質問を自然に投げかける。"
        ),
        speaker_id=8, speaker_name="春日部つむぎ",
    ),
    "ao": Character(
        id="ao", name="アオ", role="解説役",
        style=(
            "冷静で論理的な解説者。難しい内容を噛み砕いてわかりやすく伝える。"
            "背景知識や具体例を交えて丁寧に説明する。感情より事実を重視する。"
        ),
        speaker_id=13, speaker_name="青山龍星",
    ),
    "yuki": Character(
        id="yuki", name="ユキ", role="コメンテーター",
        style=(
            "鋭い視点と辛口コメントが持ち味のコメンテーター。"
            "建前より本音を言い、短くキレよく話す。反論や疑問を躊躇なく出す。"
        ),
        speaker_id=2, speaker_name="四国めたん",
    ),
    "sora": Character(
        id="sora", name="ソラ", role="フリートーカー",
        style=(
            "自由奔放で予想外の発想が得意なフリートーカー。"
            "突拍子もない例えや脱線が持ち味で場の空気を和ませる。話がどこへ飛ぶかわからない。"
        ),
        speaker_id=3, speaker_name="ずんだもん",
    ),
    "rei": Character(
        id="rei", name="レイ", role="まとめ役",
        style=(
            "穏やかで共感力が高いまとめ役。話の流れを整理して締める。"
            "他のキャラの発言を受け止めて要点をまとめ、聴いている人への配慮を忘れない。"
        ),
        speaker_id=10, speaker_name="雨晴はう",
    ),
    # ─── 追加キャラ ─────────────────────────────────────────
    "ken": Character(
        id="ken", name="ケン", role="熱血コメンテーター",
        style=(
            "情熱的で感情をストレートに表す熱血漢。テンションが高くノリが良い。"
            "驚いたり感動したりする場面で場を一気に盛り上げる。"
        ),
        speaker_id=39, speaker_name="玄野武宏[喜び]",
    ),
    "nana": Character(
        id="nana", name="ナナ", role="応援・ポジティブ担当",
        style=(
            "とにかくポジティブで応援が得意な元気キャラ。"
            "どんな話題も前向きな方向に引っ張り、聴いている人を励ます。"
        ),
        speaker_id=79, speaker_name="もち子さん[喜び]",
    ),
    "zona": Character(
        id="zona", name="ゾナ", role="実況・テンポ担当",
        style=(
            "実況スタイルでテンポよくテーマを展開するエネルギッシュなキャラ。"
            "情報をテンポ速く伝えて聴取者を引き込む。話に勢いをつけるのが得意。"
        ),
        speaker_id=81, speaker_name="青山龍星[熱血]",
    ),
    "sayo": Character(
        id="sayo", name="サヨ", role="クール・哲学担当",
        style=(
            "クールでミステリアスな観察者。感情を見せず哲学的な発言が多い。"
            "他のキャラとは違う切り口で話題の本質に切り込む。深掘りが得意。"
        ),
        speaker_id=46, speaker_name="小夜/SAYO",
    ),
    "shiro": Character(
        id="shiro", name="シロ", role="天然・ボケ担当",
        style=(
            "天然ボケとズレた発言で場を和ませるトリックスター。"
            "わかったつもりで見当違いなことを言い、他のキャラのツッコミを引き出す。"
        ),
        speaker_id=40, speaker_name="玄野武宏[ツンギレ]",
    ),
    "nia": Character(
        id="nia", name="ニア", role="不思議・詩的担当",
        style=(
            "不思議ちゃんで詩的な表現が得意。独特な感性でトピックに反応する。"
            "意外な例えや比喩で新鮮な視点を提供し、場に独特の空気をもたらす。"
        ),
        speaker_id=4, speaker_name="四国めたん[セクシー]",
    ),
    "maron": Character(
        id="maron", name="マロン", role="癒し・聞き上手担当",
        style=(
            "癒し系で聞き上手な優しいキャラ。他のキャラの話を引き出すのが上手。"
            "場の空気を柔らかくして会話を繋ぎ、みんなの意見を大切にする。"
        ),
        speaker_id=1, speaker_name="ずんだもん[あまあま]",
    ),
    "nurse": Character(
        id="nurse", name="ナース", role="分析・データ担当",
        style=(
            "データと論理を重視する理系分析キャラ。感情より事実と数値で話す。"
            "感情的な議論に冷静なファクトや統計を投入し、議論を整理する。"
        ),
        speaker_id=41, speaker_name="玄野武宏[悲しみ]",
    ),
}


# ─── キャスト定義 (キャラの組み合わせ) ─────────────────────────
# 「古参 × 新人」「テーマ別」「雰囲気別」の多様な組み合わせ
CASTS: dict[str, dict] = {
    # ── 古参メイン ──────────────────────────────────────────────
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
        "label": "古参フルキャスト",
        "chars": ["haru", "ao", "yuki", "sora"],
        "desc":  "古参全員集合・盛り上がり重視",
    },
    # ── 新人メイン ──────────────────────────────────────────────
    "hype": {
        "label": "ハイテンションコンビ",
        "chars": ["ken", "zona"],
        "desc":  "熱血と実況でとにかく盛り上がる",
    },
    "analysis": {
        "label": "分析クァルテット",
        "chars": ["ao", "nurse", "yuki", "sayo"],
        "desc":  "データと論理で冷静に深掘り",
    },
    "healing": {
        "label": "癒し系トリオ",
        "chars": ["maron", "rei", "nia"],
        "desc":  "穏やかで聴きやすい癒し系放送",
    },
    "chaos": {
        "label": "カオストリオ",
        "chars": ["shiro", "sora", "zona"],
        "desc":  "天然×自由奔放×実況で予測不能",
    },
    "midnight": {
        "label": "深夜ラジオコンビ",
        "chars": ["sayo", "yuki"],
        "desc":  "クールで辛口な大人の深夜放送風",
    },
    "morning": {
        "label": "朝番組トリオ",
        "chars": ["haru", "nana", "maron"],
        "desc":  "明るくポジティブで元気が出る朝放送",
    },
    "allstars": {
        "label": "オールスターズ",
        "chars": ["haru", "ao", "yuki", "ken", "sora"],
        "desc":  "5人で豪華なラジオ番組",
    },
    # ── 古参×新人クロスオーバー ────────────────────────────────
    "newcomer_rush": {
        "label": "古参MC×新人2人",
        "chars": ["haru", "sayo", "shiro"],
        "desc":  "ハルが新人のサヨ・シロと初対面トーク。クール×天然×明るいMCの化学反応",
    },
    "senpai_kouhai": {
        "label": "先輩後輩ラジオ",
        "chars": ["ao", "rei", "nana", "maron"],
        "desc":  "落ち着いた古参2人と元気な新人2人。知識×癒しの融合",
    },
    "fire_and_ice": {
        "label": "火と氷コンビ",
        "chars": ["ken", "sayo"],
        "desc":  "熱血ケン×クールサヨの正反対コンビ。真逆の視点が面白い",
    },
    "chaos_senior": {
        "label": "混沌コンビ",
        "chars": ["sora", "shiro", "nia"],
        "desc":  "自由奔放×天然×不思議ちゃん。脱線必至の予測不能トーク",
    },
    "knowledge_war": {
        "label": "知識バトルトリオ",
        "chars": ["ao", "nurse", "sayo"],
        "desc":  "論理×データ×哲学。3つの「知」が激突する深掘り放送",
    },
    "energy_squad": {
        "label": "エナジースクワッド",
        "chars": ["ken", "nana", "zona"],
        "desc":  "熱血×応援×実況の超ハイテンション新人トリオ",
    },
    "night_lounge": {
        "label": "夜のラウンジ",
        "chars": ["yuki", "sayo", "maron"],
        "desc":  "辛口×ミステリアス×癒し。大人の夜ラジオ",
    },
    "rainbow_squad": {
        "label": "レインボー隊",
        "chars": ["haru", "sora", "shiro", "nia"],
        "desc":  "明るいMC・自由人・天然・不思議ちゃん。賑やか混合4人組",
    },
    "grand_slam": {
        "label": "グランドスラム",
        "chars": ["haru", "ao", "yuki", "sayo", "ken"],
        "desc":  "古参3人+新人2人の豪華5人。対話の密度最高峰",
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
