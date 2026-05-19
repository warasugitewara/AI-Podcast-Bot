"""
LLMサービス: NVIDIA NIM (meta/llama-3.3-70b-instruct) + キャラクター対話生成

NIM無料枠対策:
- 日次リクエストカウンター (NIM_MAX_DAILY_REQUESTS)
- generate_bgm_query() を廃止 → 事前定義リストで代替
- max_tokens削減・システムプロンプト圧縮
"""
from __future__ import annotations
import logging
import random
import time
from datetime import date
from openai import AsyncOpenAI
from config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL, NIM_MAX_DAILY_REQUESTS

log = logging.getLogger("llm")

_client = AsyncOpenAI(base_url=LLM_API_BASE, api_key=LLM_API_KEY)

# ─── 日次リクエストカウンター ──────────────────────────────
_counter_date: date = date.today()
_counter_count: int = 0

def _can_request() -> bool:
    global _counter_date, _counter_count
    today = date.today()
    if today != _counter_date:
        _counter_date  = today
        _counter_count = 0
    if _counter_count >= NIM_MAX_DAILY_REQUESTS:
        log.warning(f"NIM日次上限到達 ({NIM_MAX_DAILY_REQUESTS}件/日)。生成をスキップします。")
        return False
    return True

def _inc_counter():
    global _counter_count
    _counter_count += 1
    remaining = NIM_MAX_DAILY_REQUESTS - _counter_count
    log.info(f"NIM使用: {_counter_count}/{NIM_MAX_DAILY_REQUESTS} (残{remaining}件)")

def get_daily_usage() -> dict:
    return {
        "used": _counter_count,
        "limit": NIM_MAX_DAILY_REQUESTS,
        "remaining": NIM_MAX_DAILY_REQUESTS - _counter_count,
        "date": str(_counter_date),
    }


# ─── BGMクエリプール（LLM不使用）──────────────────────────
# "official audio" を付けることでカラオケ・cover版が上位に来にくくする
_BGM_POOL = [
    # Lo-fi / Chill
    "lofi hip hop radio beats to relax study official audio",
    "lofi jazz cafe background music official",
    "chill lofi beats no copyright free music",
    "lofi hip hop mix study concentration official",
    "lo-fi chill music playlist official audio",
    "lofi beats cozy night official audio",
    "chillhop music cafe official audio",
    "lofi beats rainy day official audio",
    "lofi hip hop afternoon chill official",
    "chill beats no copyright background official",
    # Jazz / Bossa Nova
    "smooth jazz background music official audio",
    "bossa nova cafe jazz official audio",
    "jazz coffee shop background music official",
    "jazz bar night music official audio",
    "bossa nova morning cafe official",
    "jazz piano relaxing official audio",
    "funky jazz instrumental official audio",
    "acid jazz background music official",
    "cool jazz relaxing instrumental official",
    "latin jazz background music official audio",
    # Classical / Piano
    "classical piano background music official",
    "piano lofi beats relaxing official",
    "solo piano calm music official audio",
    "classical music focus study official",
    "piano ambient background official audio",
    "baroque classical music studying official",
    "piano impressionism music relax official",
    # Electronic / Synth
    "ambient electronic chill background music official",
    "synthwave lo-fi no copyright official audio",
    "chillwave background music official audio",
    "synthwave driving music official audio",
    "ambient electronic deep focus official",
    "vaporwave aesthetic music official audio",
    "future bass chill official audio",
    "dreamwave synth background official audio",
    "darksynth instrumental chill official",
    "outrun synthwave music official audio",
    # Acoustic / Indie
    "acoustic guitar background chill official audio",
    "indie pop chill music official audio",
    "acoustic folk background music official",
    "indie acoustic guitar relax official",
    "folk indie singer songwriter background official",
    "coffeehouse acoustic background official audio",
    # Japanese / J-pop / City pop
    "city pop japanese style official audio",
    "j-pop official audio BGM",
    "japanese city pop 80s official audio",
    "japanese lofi city pop official",
    "j-city pop chill official audio",
    "japanese jazz funk official audio",
    "japanese ambient music official",
    "japanese indie pop background official audio",
    "japanese funk groove official audio",
    "japanese neo soul official audio",
    "japanese shoegaze background official",
    "japanese electronic ambient official audio",
    # Neo soul / R&B
    "neo soul background music official",
    "neo soul r&b instrumental official audio",
    "soul jazz background official audio",
    "r&b smooth instrumental official audio",
    "funk soul groove background official",
    # Upbeat / Pop
    "upbeat background music no copyright official",
    "happy background music official audio",
    "feel good indie pop official audio",
    "uplifting background music official",
    "sunshine pop background official audio",
    "summer pop background chill official",
    # Study / Focus
    "study music concentration official audio",
    "deep focus music for work official",
    "concentration music alpha waves official",
    "focus music productivity official audio",
    "binaural beats focus study official",
    # Ambient / Nature
    "ambient music relaxing nature official audio",
    "calm ambient background official",
    "meditation ambient music official audio",
    "space ambient background music official",
    "dark ambient background official audio",
    # Electronic / Dance (mellow)
    "chillstep music official audio",
    "downtempo electronic music official",
    "trip hop background music official audio",
    "nu jazz electronic official audio",
    "liquid dnb chill official audio",
    "deep house background chill official",
    # Reggae / Dub
    "reggae background music chill official audio",
    "dub reggae instrumental background official",
    "roots reggae relaxing official audio",
    # Blues / Soul
    "blues background music chill official audio",
    "electric blues instrumental official audio",
    "blues jazz fusion background official",
    # World Music
    "world music background chill official audio",
    "african jazz background official audio",
    "celtic folk background music official",
    "flamenco guitar background official audio",
    "middle eastern ambient music official",
    # Game / Anime BGM style
    "video game background music chill official",
    "rpg game ost background official audio",
    "anime bgm instrumental relaxing official",
    "game music ambient official audio",
]
# シャッフル済みインデックスリスト（同じ曲が近くに来ないようにする）
_bgm_pool_order: list[int] = []
_bgm_pool_pos:   int = 0

def _ensure_bgm_order():
    global _bgm_pool_order
    if not _bgm_pool_order:
        import random as _r
        _bgm_pool_order = list(range(len(_BGM_POOL)))
        _r.shuffle(_bgm_pool_order)

def pick_bgm_query() -> str:
    global _bgm_pool_pos
    _ensure_bgm_order()
    idx = _bgm_pool_order[_bgm_pool_pos % len(_bgm_pool_order)]
    _bgm_pool_pos += 1
    # 一周したらシャッフルし直す
    if _bgm_pool_pos % len(_bgm_pool_order) == 0:
        import random as _r
        _r.shuffle(_bgm_pool_order)
    return _BGM_POOL[idx]


# ─── トピックプール（多様なジャンル）──────────────────────
_TOPIC_POOL = [
    # テクノロジー
    "最新AIと機械学習トレンド",
    "スマートフォン・ガジェットの最新情報",
    "ゲーム業界の最新ニュース",
    "宇宙開発とロケット技術の話",
    "サイバーセキュリティの最新動向",
    "電気自動車と自動運転技術",
    "メタバース・VR/ARの現在と未来",
    "スマートホームとIoT技術",
    "量子コンピュータって何がすごいの？",
    "3Dプリンタが変える製造業の未来",
    # サイエンス
    "宇宙と天文学の不思議な話",
    "最新の科学的発見や研究",
    "生物・動物の驚きの生態",
    "地球環境と気候変動の最前線",
    "人体と医療の最新科学",
    "深海の謎と未知の生物",
    "睡眠と夢の科学",
    "食べ物と脳の関係",
    # エンタメ・カルチャー
    "最近話題のアニメ・漫画",
    "音楽トレンドとおすすめアーティスト",
    "映画・ドラマのおすすめ・感想",
    "日本のポップカルチャーが世界に与える影響",
    "eスポーツの盛り上がりと大会情報",
    "ストリーミングサービスが変えたエンタメ消費",
    "ゲーム実況とVTuberカルチャー",
    "インターネットミームと文化の広がり",
    # 生活・食
    "日本のB級グルメと世界のおもしろ料理",
    "旅行・観光のおすすめスポット",
    "健康的な生活習慣とフィットネストレンド",
    "コーヒー・お茶・飲み物のこだわり話",
    "料理と科学の意外な関係",
    "発酵食品と健康の話",
    "都市農業と食の未来",
    # 社会・経済
    "仮想通貨・ブロックチェーンの現状",
    "働き方改革・リモートワークの変化",
    "若者のライフスタイルと消費トレンド",
    "サブスクサービスが変えた生活",
    "SNSと社会の変化",
    "Z世代とミレニアル世代の価値観の違い",
    # 面白・雑学
    "人類の歴史で最もインパクトがあった発明",
    "10年後の未来はどうなっている？",
    "もし〇〇が存在しなかったら…という妄想話",
    "世界の奇妙な法律・文化の違い",
    "言語と方言の面白い話",
    "色と人間の心理の関係",
    "音楽が気分に与える科学的な影響",
    "都市伝説と実際の科学的説明",
    # スポーツ
    "サッカー・野球・バスケの最新情報",
    "日本のスポーツ界のホットな話題",
    "オリンピックとスポーツの歴史",
    "eスポーツは本当にスポーツか？という議論",
    # 心理・人間関係
    "心理学から見た人間の行動パターン",
    "コミュニケーションと人間関係のコツ",
    "ストレスと現代社会の生き方",
    "創造性と発想力を高める方法",
    # 音楽・芸術
    "音楽の歴史と現代音楽のつながり",
    "プロデューサーとアーティストの役割の変化",
    "街と音楽のカルチャーの関係",
    # 日本文化
    "日本の伝統文化が現代に与える影響",
    "祭りと地域コミュニティの話",
    "日本語の面白い言葉・表現の話",
    # 追加: バラエティ・トレンド
    "最近バズったSNSトレンドの話",
    "推し活・ファンカルチャーの話",
    "ひとり時間の過ごし方トレンド",
    "進化する日本のコンビニ文化",
    "インフルエンサーと広告の変化",
    "AIが変える仕事の未来",
    "ペットと暮らすライフスタイルの変化",
    "マンガ・アニメのグローバル展開",
    "お笑いと笑いの科学",
    "音楽フェスと野外イベント文化",
    "サウナブームと健康志向の話",
    "自転車・アウトドアブームの話",
    "ガジェットオタクの最新こだわり",
    "ファッションとサステナビリティ",
    "読書・電子書籍・オーディオブックの変化",
    "ポッドキャスト・音声コンテンツの台頭",
    "日本のゲームが世界に与えた影響",
    "リアル脱出ゲームと体験型エンタメ",
    "スポーツ観戦とスタジアム文化の進化",
    "食べ歩きと観光フードカルチャー",
    "深夜ラジオと音声エンタメの歴史",
    "話題の映画・ドラマの裏話や制作秘話",
    "バーチャルアイドルとデジタルタレント",
    "日本語ラップとヒップホップカルチャー",
    "テクノロジーが変えるスポーツ観戦体験",
    "宇宙ビジネスと民間ロケットの今",
]

# シャッフル済みインデックスリスト（BGMプールと同じ方式でサイクル管理）
_topic_order: list[int] = []
_topic_pos:   int = 0

def _ensure_topic_order():
    global _topic_order
    if not _topic_order:
        _topic_order = list(range(len(_TOPIC_POOL)))
        random.shuffle(_topic_order)

def pick_random_topic(avoid: list[str] | None = None) -> str:
    """シャッフルサイクルでトピックを選ぶ。全件使い切るまで同じトピックが出ない。
    avoid リストに含まれるトピックはスキップし、次の候補を探す。"""
    global _topic_pos
    _ensure_topic_order()
    avoid_lower = {t.lower() for t in avoid} if avoid else set()

    # サイクル順にavoidを除いた最初の候補を返す
    for _ in range(len(_TOPIC_POOL)):
        idx = _topic_order[_topic_pos % len(_topic_order)]
        _topic_pos += 1
        # 一周したらシャッフルし直す
        if _topic_pos % len(_topic_order) == 0:
            random.shuffle(_topic_order)
        topic = _TOPIC_POOL[idx]
        if not avoid_lower or not any(
            topic.lower() in av or av in topic.lower() for av in avoid_lower
        ):
            return topic

    # 全件がavoid対象（理論上起きないが念のため）
    return _TOPIC_POOL[0]


# ─── システムプロンプト ────────────────────────────────────
_SOLO_SYSTEM = (
    "あなたはAIポッドキャストDJ。明るく自然な日本語で5〜8文のトークを生成。"
    "具体例・エピソード・数字を交えて話を膨らませ、リスナーが「へえ！」と思える内容にする。"
    "途中で自分の意見や感想を入れる。捏造は禁止。"
)


def _build_dialogue_system(chars: list, has_context: bool) -> str:
    char_desc = "\n".join(
        f"  ・{c.name}（{c.role}）: {c.style}" for c in chars
    )
    n      = len(chars)
    # 2人→10〜14ターン、3人→12〜18ターン、4人以上→16〜24ターン
    turns  = n * 5
    max_t  = n * 7
    first  = chars[0].name
    last   = chars[-1].name
    ctx_rule = (
        "提供された参考情報を土台にしつつ、各キャラが自分の視点・意見・ツッコミを必ず入れる。"
    ) if has_context else (
        "テーマについて各キャラが自由に持論・体験・例え話を展開してよい。事実の捏造は禁止。"
    )

    return (
        f"あなたはAIラジオ番組の台本ライター。以下のキャラクターで会話台本を書く。\n"
        f"登場人物:\n{char_desc}\n\n"
        f"出力ルール:\n"
        f"  - 「名前: セリフ」の形式のみ。それ以外のテキスト（ト書き・説明・コメント）は一切不要。\n"
        f"  - {turns}〜{max_t}行を目安に（少なすぎると没）。\n"
        f"  - 1セリフは20〜120字。短すぎも長すぎも避ける。\n"
        f"  - 最初の発言は{first}から始める。最後は{first}か{last}が締める。\n"
        f"  - 各キャラのstyleを厳守しながら、互いに反応・ツッコミ・驚き・反論・共感を入れる。\n"
        f"  - セリフは自然な日本語で書く。口癖は全体で1〜2回まで、毎回同じ表現を繰り返さない。\n"
        f"  - 会話の中盤でひとつ意外な視点や豆知識・エピソードを盛り込む。\n"
        f"  - 全体として「起承転結」の流れを作り、聴衆が飽きないよう盛り上がりのピークを作る。\n"
        f"  - 提供された[FACTS]ブロックの情報を改変・誇張しない。感情・意見・ツッコミはOKだが、新しい事実を創作しない。\n"
        f"\n{ctx_rule}"
    )


# ─── 生成関数 ─────────────────────────────────────────────

async def generate_talk(topic: str, context: str = "", avoid: list[str] | None = None) -> tuple[str, str]:
    """ソロトーク生成。戻り値: (テキスト, 使用トピック)"""
    if not _can_request():
        return "", ""
    from services.program_memory import program_memory as _pm
    resolved = topic.strip() or pick_random_topic(avoid=avoid or _pm.recent_topics)
    user_content = f"トピック: {resolved}"
    if context:
        user_content += f"\n【参考情報】{context}"

    _inc_counter()
    resp = await _client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _SOLO_SYSTEM},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=400,
        temperature=0.85,
    )
    return resp.choices[0].message.content.strip(), resolved


async def generate_dialogue(
    topic: str,
    context: str = "",
    chars: list | None = None,
    memory_ctx: str = "",
    mode: str = "chat",  # "chat"(0.8) | "news"(0.4) | "transition"(0.6)
) -> tuple[list[dict], str]:
    """
    キャラクター対話台本を生成。
    戻り値: ([{"speaker": "ハル", "text": "..."}, ...], resolved_topic)
    日次上限超過時は ([], "") を返す（呼び出し側でBGMにフォールバック）。
    mode で temperature を切り替え:
      chat       → 0.8  (雑談・バラエティ系)
      news       → 0.4  (ニュース・事実系、ハルシネーション抑制)
      transition → 0.6  (曲振り・話題転換)
    """
    _TEMP = {"chat": 0.8, "news": 0.4, "transition": 0.6}
    temperature = _TEMP.get(mode, 0.8)
    if not _can_request():
        return [], ""

    from services.character_manager import character_manager
    from services.program_memory import program_memory as _pm
    if chars is None:
        chars = character_manager.active()

    # トピック未指定→直近の話題を避けてランダム選択
    resolved_topic = topic.strip() or pick_random_topic(avoid=_pm.recent_topics)
    user_content = f"テーマ: {resolved_topic}"
    if memory_ctx:
        user_content += f"\n【番組コンテキスト】\n{memory_ctx}"
    # 直近10件のトピックを「避けること」として追加指示
    avoid_hint = _pm.avoid_topics_hint()
    if avoid_hint:
        user_content += f"\n【注意】次の話題と内容が被らないようにする: {avoid_hint}"
    if context:
        # 事実ブロック形式で渡す（LLMに改変させない）
        user_content += f"\n[FACTS]\n{context}\n[/FACTS]\n※上記の事実のみを使用し、新しい事実を創作しない。"

    log.info(f"対話生成: topic={resolved_topic!r} cast={[c.name for c in chars]}")
    _inc_counter()
    resp = await _client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _build_dialogue_system(chars, bool(context))},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=1500,
        temperature=temperature,
    )
    raw = resp.choices[0].message.content.strip()
    log.info(f"対話生成完了: {len(raw)}文字")

    valid_names = {c.name for c in chars}
    lines = _parse_dialogue(raw, valid_names)
    if not lines:
        log.warning(f"パース失敗。raw:\n{raw[:300]}")
    return lines, resolved_topic


def _parse_dialogue(raw: str, valid_names: set[str]) -> list[dict]:
    lines = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        for name in valid_names:
            for sep in (": ", "： ", ":"):
                if line.startswith(name + sep):
                    text = line[len(name + sep):].strip()
                    if text:
                        lines.append({"speaker": name, "text": text})
                    break
    return lines

