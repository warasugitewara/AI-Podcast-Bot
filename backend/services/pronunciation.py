"""
発音前処理: 英語・固有名詞 → VOICEVOX が読めるカタカナに変換する

TTS に渡す前に preprocess() を呼ぶことで
「Mrs. GREEN APPLE」→「ミセスグリーンアップル」のように変換する。
"""
from __future__ import annotations
import re

# ─── 変換辞書（長いものから順に適用）────────────────────────
_DICT: dict[str, str] = {
    # ─ J-POPアーティスト
    "Mrs. GREEN APPLE":          "ミセスグリーンアップル",
    "Official HIGE DANdism":     "オフィシャルヒゲダンディズム",
    "Official髭男dism":          "オフィシャルヒゲダンディズム",
    "YOASOBI":                   "ヨアソビ",
    "RADWIMPS":                  "ラッドウィンプス",
    "BTS":                       "ビーティーエス",
    "BLACKPINK":                 "ブラックピンク",
    "TWICE":                     "トゥワイス",
    "aespa":                     "エスパ",
    "NewJeans":                  "ニュージーンズ",
    "IVE":                       "アイブ",
    "LE SSERAFIM":               "ルセラフィム",
    "SEVENTEEN":                 "セブンティーン",
    "Stray Kids":                "ストレイキッズ",
    "Perfume":                   "パフューム",
    "ONE OK ROCK":               "ワンオクロック",
    "EXILE":                     "エグザイル",
    "E-girls":                   "イーガールズ",
    "DA PUMP":                   "ダパンプ",
    "w-inds.":                   "ウィンズ",
    "globe":                     "グローブ",
    "Dreams Come True":          "ドリームズカムトゥルー",
    "Mr.Children":               "ミスターチルドレン",
    "B'z":                       "ビーズ",
    "X JAPAN":                   "エックスジャパン",
    "L'Arc-en-Ciel":             "ラルクアンシエル",
    "Do As Infinity":            "ドゥーアズインフィニティ",
    "Dragon Ash":                "ドラゴンアッシュ",
    "THE ORAL CIGARETTES":       "ジオーラルシガレッツ",
    "the GazettE":               "ガゼット",
    "SixTONES":                  "ストーンズ",
    "Snow Man":                  "スノーマン",
    "King & Prince":             "キングアンドプリンス",
    "Sexy Zone":                 "セクシーゾーン",
    "Hey! Say! JUMP":            "ヘイセイジャンプ",
    "Kis-My-Ft2":                "キスマイフットツー",
    "ARASHI":                    "アラシ",
    "Ado":                       "アド",
    "Vaundy":                    "バウンディ",
    "imase":                     "イマセ",
    "fujii kaze":                "藤井風",
    "Fujii Kaze":                "藤井風",
    "Kenshi Yonezu":             "米津玄師",
    "Yorushika":                 "ヨルシカ",
    # ─ テクノロジー
    "ChatGPT":                   "チャットジーピーティー",
    "OpenAI":                    "オープンエーアイ",
    "NVIDIA":                    "エヌビディア",
    "JavaScript":                "ジャバスクリプト",
    "TypeScript":                "タイプスクリプト",
    "Python":                    "パイソン",
    "GitHub":                    "ギットハブ",
    "YouTube":                   "ユーチューブ",
    "Discord":                   "ディスコード",
    "Instagram":                 "インスタグラム",
    "TikTok":                    "ティックトック",
    "LinkedIn":                  "リンクトイン",
    "Netflix":                   "ネットフリックス",
    "Spotify":                   "スポティファイ",
    "Amazon":                    "アマゾン",
    "Microsoft":                 "マイクロソフト",
    "Windows":                   "ウィンドウズ",
    "Android":                   "アンドロイド",
    "iPhone":                    "アイフォン",
    "iPad":                      "アイパッド",
    "MacBook":                   "マックブック",
    "Bitcoin":                   "ビットコイン",
    "blockchain":                "ブロックチェーン",
    "Blockchain":                "ブロックチェーン",
    "metaverse":                 "メタバース",
    "Metaverse":                 "メタバース",
    "VOICEVOX":                  "ボイスボックス",
    # ─ 略語（大文字）
    "ChatGPT":                   "チャットジーピーティー",
    "AI":                        "エーアイ",
    "VR":                        "ブイアール",
    "AR":                        "エーアール",
    "MR":                        "エムアール",
    "XR":                        "エックスアール",
    "GPU":                       "ジーピーユー",
    "CPU":                       "シーピーユー",
    "USB":                       "ユーエスビー",
    "BGM":                       "ビージーエム",
    "DJ":                        "ディージェー",
    "MC":                        "エムシー",
    "CM":                        "シーエム",
    "SNS":                       "エスエヌエス",
    "NFT":                       "エヌエフティー",
    "NFTs":                      "エヌエフティーズ",
    "IT":                        "アイティー",
    "PC":                        "ピーシー",
    "TV":                        "テレビ",
    "FM":                        "エフエム",
    "AM":                        "エーエム",
    "OK":                        "オーケー",
    "NG":                        "エヌジー",
    "Wi-Fi":                     "ワイファイ",
    "GitHub":                    "ギットハブ",
    "Twitter":                   "ツイッター",
    "LINE":                      "ライン",
}

# 長い順で適用（部分マッチを防ぐ）
_SORTED = sorted(_DICT.items(), key=lambda x: len(x[0]), reverse=True)
# 全角・半角混在を吸収するパターンはシンプルに re.escape で対応
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(re.escape(src)), dst)
    for src, dst in _SORTED
]


def preprocess(text: str) -> str:
    """英語・固有名詞をVOICEVOXが読めるカタカナに変換する。"""
    for pat, dst in _PATTERNS:
        text = pat.sub(dst, text)
    return text
