"""
娯楽系コマンド集(20個)
- おみくじ、じゃんけん、サイコロ、クイズ、しりとり、数当てゲーム、投票、
  リマインダー、レベル(XP)システム、相性診断、駄洒落 など
"""
import json
import os
import random
import asyncio
import datetime
import hashlib

import discord
from discord import app_commands
from discord.ext import commands

DATA_PATH = os.path.join(os.path.dirname(__file__), "fun_data.json")

# ─────────────────────────────
# データ保存(XP・レベル用)
# ─────────────────────────────
def _load_data() -> dict:
    if not os.path.exists(DATA_PATH):
        return {}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_data(data: dict) -> None:
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_xp(guild_id: int, user_id: int, amount: int = 1) -> int:
    """XPを加算し、加算後の合計XPを返す"""
    data = _load_data()
    key = f"{guild_id}:{user_id}"
    data[key] = data.get(key, 0) + amount
    _save_data(data)
    return data[key]


def get_xp(guild_id: int, user_id: int) -> int:
    data = _load_data()
    return data.get(f"{guild_id}:{user_id}", 0)


def get_ranking(guild_id: int, limit: int = 5) -> list[tuple[int, int]]:
    data = _load_data()
    prefix = f"{guild_id}:"
    entries = [
        (int(k.split(":")[1]), v) for k, v in data.items() if k.startswith(prefix)
    ]
    entries.sort(key=lambda x: x[1], reverse=True)
    return entries[:limit]


def xp_to_level(xp: int) -> int:
    # 30XPごとに1レベルアップ
    return xp // 30 + 1


# ─────────────────────────────
# 固定データ(おみくじ・クイズ・名言など)
# ─────────────────────────────
OMIKUJI = [
    ("🍅大大吉", "とんでもなくいい1日になりそう!"),
    ("大吉", "何をやってもうまくいく予感"),
    ("中吉", "まずまず順調な1日"),
    ("小吉", "ちょっといいことがあるかも"),
    ("吉", "いつも通り、平和な1日"),
    ("末吉", "焦らずゆっくりいきましょう"),
    ("凶", "今日は無理せず、早めに休もう"),
]

EIGHT_BALL_ANSWERS = [
    "間違いなくYES", "たぶんYES", "可能性は高い", "今は何とも言えない",
    "うーん、微妙", "たぶんNO", "残念ながらNO", "聞き直してみて",
    "とまとに聞いてみて🍅", "時が来ればわかるはず",
]

QUIZZES = [
    ("世界で一番小さい国はどこ?", "バチカン市国"),
    ("トマトは野菜?果物?", "植物学的には果物(果実)"),
    ("1日は何時間?", "24時間"),
    ("日本の首都は?", "東京"),
    ("虹は何色?", "7色"),
    ("光の速さは約何km/秒?", "約30万km/秒"),
    ("人間の骨は何本?", "約206本"),
]

QUOTES = [
    "「今日という日は、残りの人生の最初の日である」",
    "「失敗は成功のもと」",
    "「継続は力なり」",
    "「千里の道も一歩から」",
    "「案ずるより産むが易し」",
    "「雨降って地固まる」",
]

WOULD_YOU_RATHER = [
    ("一生トマトしか食べられない", "一生トマトを二度と食べられない"),
    ("空を飛べる", "水中で呼吸できる"),
    ("過去に戻れる", "未来を覗ける"),
    ("お金持ちだが友達が少ない", "貧乏だが友達が多い"),
    ("毎日同じ服", "毎日同じ食事"),
]

DAJARE = [
    "とまと、いつも「まと」外さない🍅",
    "布団が吹っ飛んだ",
    "アルミ缶の上にあるミカン",
    "電話に出んわ",
    "とまとが飛んでっ「TOMATO」",
    "イカ丸ごと如何ですか",
]


class FunCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # チャンネルごとの進行中ゲーム状態
        self.shiritori_state: dict[int, dict] = {}
        self.guess_state: dict[int, dict] = {}

    # ───────── メッセージ監視(しりとり・数当て・XP加算) ─────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        # XP加算(1メッセージにつき1〜3XP)
        new_total = add_xp(message.guild.id, message.author.id, random.randint(1, 3))

        # しりとり進行中なら判定
        state = self.shiritori_state.get(message.channel.id)
        if state:
            await self._handle_shiritori(message, state)

        # 数当てゲーム進行中なら判定
        guess = self.guess_state.get(message.channel.id)
        if guess and message.content.strip().lstrip("-").isdigit():
            await self._handle_guess(message, guess)

    async def _handle_shiritori(self, message: discord.Message, state: dict):
        word = message.content.strip()
        if not word or len(word) < 1:
            return
        last_char = state["last_word"][-1]
        # 「ー」は直前の音とみなして少し許容
        if word[0] not in (last_char,):
            return
        if word in state["used"]:
            await message.channel.send(f"⚠️ 「{word}」はもう使われています!")
            return
        if word.endswith("ん"):
            await message.channel.send(
                f"💥 「ん」で終わりました…!{message.author.mention} の負けです。しりとり終了!"
            )
            del self.shiritori_state[message.channel.id]
            return
        state["used"].add(word)
        state["last_word"] = word
        await message.add_reaction("✅")

    async def _handle_guess(self, message: discord.Message, state: dict):
        try:
            num = int(message.content.strip())
        except ValueError:
            return
        target = state["target"]
        if num == target:
            await message.reply(f"🎉 正解!答えは {target} でした!")
            del self.guess_state[message.channel.id]
        elif num < target:
            await message.add_reaction("🔼")
        else:
            await message.add_reaction("🔽")

    # ───────── ① サイコロ ─────────
    @app_commands.command(name="dice", description="サイコロを振ります")
    @app_commands.describe(sides="サイコロの面数(既定:6)", count="振る個数(既定:1)")
    async def dice(self, interaction: discord.Interaction, sides: int = 6, count: int = 1):
        count = max(1, min(count, 20))
        sides = max(2, min(sides, 1000))
        rolls = [random.randint(1, sides) for _ in range(count)]
        await interaction.response.send_message(
            f"🎲 {sides}面サイコロ×{count}: {rolls}(合計 {sum(rolls)})"
        )

    # ───────── ② コイントス ─────────
    @app_commands.command(name="coinflip", description="コインを投げます")
    async def coinflip(self, interaction: discord.Interaction):
        result = random.choice(["🪙 表!", "🪙 裏!"])
        await interaction.response.send_message(result)

    # ───────── ③ じゃんけん ─────────
    @app_commands.command(name="janken", description="ボットとじゃんけんします")
    @app_commands.choices(hand=[
        app_commands.Choice(name="グー", value="グー"),
        app_commands.Choice(name="チョキ", value="チョキ"),
        app_commands.Choice(name="パー", value="パー"),
    ])
    async def janken(self, interaction: discord.Interaction, hand: app_commands.Choice[str]):
        bot_hand = random.choice(["グー", "チョキ", "パー"])
        you = hand.value
        if you == bot_hand:
            result = "あいこ!"
        elif (you, bot_hand) in [("グー", "チョキ"), ("チョキ", "パー"), ("パー", "グー")]:
            result = "あなたの勝ち!🎉"
        else:
            result = "あなたの負け…"
        await interaction.response.send_message(f"あなた: {you} / とまとBot: {bot_hand}\n{result}")

    # ───────── ④ おみくじ ─────────
    @app_commands.command(name="omikuji", description="今日の運勢を占います")
    async def omikuji(self, interaction: discord.Interaction):
        result, desc = random.choice(OMIKUJI)
        await interaction.response.send_message(f"🍅 **{result}**\n{desc}")

    # ───────── ⑤ 8ball ─────────
    @app_commands.command(name="8ball", description="質問に運命の答えをもらいます")
    @app_commands.describe(question="占いたい質問")
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        answer = random.choice(EIGHT_BALL_ANSWERS)
        await interaction.response.send_message(f"🎱 Q: {question}\nA: {answer}")

    # ───────── ⑥ ランダム選択 ─────────
    @app_commands.command(name="choose", description="カンマ区切りの選択肢からランダムに1つ選びます")
    @app_commands.describe(options="例: ラーメン,カレー,寿司")
    async def choose(self, interaction: discord.Interaction, options: str):
        items = [o.strip() for o in options.split(",") if o.strip()]
        if len(items) < 2:
            await interaction.response.send_message("⚠️ カンマ区切りで2つ以上の選択肢を入力してください")
            return
        await interaction.response.send_message(f"🎯 選ばれたのは… **{random.choice(items)}**!")

    # ───────── ⑦ クイズ ─────────
    @app_commands.command(name="trivia", description="ランダムなクイズを出題します")
    async def trivia(self, interaction: discord.Interaction):
        q, a = random.choice(QUIZZES)
        await interaction.response.send_message(f"❓ {q}\n答え: ||{a}||")

    # ───────── ⑧ しりとり開始 ─────────
    @app_commands.command(name="shiritori_start", description="このチャンネルでしりとりを始めます")
    @app_commands.describe(first_word="最初の単語(省略可)")
    async def shiritori_start(self, interaction: discord.Interaction, first_word: str = "とまと"):
        self.shiritori_state[interaction.channel_id] = {
            "last_word": first_word,
            "used": {first_word},
        }
        await interaction.response.send_message(
            f"🍅 しりとりスタート!最初の単語は「{first_word}」\n"
            f"「{first_word[-1]}」から始まる言葉をこのチャンネルに送ってください!"
        )

    @app_commands.command(name="shiritori_stop", description="しりとりを終了します")
    async def shiritori_stop(self, interaction: discord.Interaction):
        if self.shiritori_state.pop(interaction.channel_id, None):
            await interaction.response.send_message("🛑 しりとりを終了しました")
        else:
            await interaction.response.send_message("今、しりとりは行われていません")

    # ───────── ⑨ 数当てゲーム ─────────
    @app_commands.command(name="guessnumber_start", description="数当てゲームを始めます")
    @app_commands.describe(max_number="上限の数字(既定:100)")
    async def guessnumber_start(self, interaction: discord.Interaction, max_number: int = 100):
        max_number = max(10, min(max_number, 1000))
        self.guess_state[interaction.channel_id] = {
            "target": random.randint(1, max_number),
            "max": max_number,
        }
        await interaction.response.send_message(
            f"🔢 1〜{max_number}の数字を思い浮かべました!数字を送って当ててみてください"
        )

    # ───────── ⑩ 投票作成 ─────────
    @app_commands.command(name="poll", description="投票を作成します(最大5択)")
    @app_commands.describe(question="質問文", options="カンマ区切りの選択肢(最大5つ)")
    async def poll(self, interaction: discord.Interaction, question: str, options: str):
        items = [o.strip() for o in options.split(",") if o.strip()][:5]
        if len(items) < 2:
            await interaction.response.send_message("⚠️ カンマ区切りで2つ以上の選択肢を入力してください")
            return
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        body = "\n".join(f"{emojis[i]} {item}" for i, item in enumerate(items))
        embed = discord.Embed(title=f"📊 {question}", description=body, color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)
        sent = await interaction.original_response()
        for i in range(len(items)):
            await sent.add_reaction(emojis[i])

    # ───────── ⑪ アイコン表示 ─────────
    @app_commands.command(name="avatar", description="ユーザーのアイコンを表示します")
    @app_commands.describe(user="表示したいユーザー(省略で自分)")
    async def avatar(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"{user.display_name} のアイコン", color=discord.Color.orange())
        embed.set_image(url=user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ───────── ⑫ ユーザー情報 ─────────
    @app_commands.command(name="userinfo", description="ユーザーの情報を表示します")
    @app_commands.describe(user="調べたいユーザー(省略で自分)")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"{user.display_name} の情報", color=discord.Color.orange())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="アカウント作成日", value=user.created_at.strftime("%Y-%m-%d"))
        embed.add_field(name="サーバー参加日", value=user.joined_at.strftime("%Y-%m-%d") if user.joined_at else "不明")
        embed.add_field(name="ロール数", value=str(len(user.roles) - 1))
        await interaction.response.send_message(embed=embed)

    # ───────── ⑬ サーバー情報 ─────────
    @app_commands.command(name="serverinfo", description="サーバーの情報を表示します")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        embed = discord.Embed(title=f"{g.name} の情報", color=discord.Color.orange())
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="メンバー数", value=str(g.member_count))
        embed.add_field(name="作成日", value=g.created_at.strftime("%Y-%m-%d"))
        embed.add_field(name="ブースト数", value=str(g.premium_subscription_count))
        await interaction.response.send_message(embed=embed)

    # ───────── ⑭ リマインダー ─────────
    @app_commands.command(name="remind", description="指定分後にリマインドします")
    @app_commands.describe(minutes="何分後か", text="リマインド内容")
    async def remind(self, interaction: discord.Interaction, minutes: int, text: str):
        minutes = max(1, min(minutes, 1440))
        await interaction.response.send_message(f"⏰ {minutes}分後にお知らせします:「{text}」")

        async def _job():
            await asyncio.sleep(minutes * 60)
            await interaction.channel.send(f"⏰ {interaction.user.mention} リマインド: {text}")

        self.bot.loop.create_task(_job())

    # ───────── ⑮ カウントダウン ─────────
    @app_commands.command(name="countdown", description="指定秒後にお知らせします")
    @app_commands.describe(seconds="何秒後か", label="ラベル(何のカウントダウンか)")
    async def countdown(self, interaction: discord.Interaction, seconds: int, label: str = "タイマー"):
        seconds = max(5, min(seconds, 3600))
        await interaction.response.send_message(f"⏳ 「{label}」を{seconds}秒でセットしました")

        async def _job():
            await asyncio.sleep(seconds)
            await interaction.channel.send(f"🔔 「{label}」の時間になりました!")

        self.bot.loop.create_task(_job())

    # ───────── ⑯ 名言 ─────────
    @app_commands.command(name="quote", description="ランダムな名言を表示します")
    async def quote(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"💬 {random.choice(QUOTES)}")

    # ───────── ⑰ 相性診断 ─────────
    @app_commands.command(name="aisho", description="2人の相性を診断します")
    @app_commands.describe(user1="1人目", user2="2人目(省略で自分)")
    async def aisho(self, interaction: discord.Interaction, user1: discord.Member, user2: discord.Member = None):
        user2 = user2 or interaction.user
        seed = f"{min(user1.id, user2.id)}-{max(user1.id, user2.id)}"
        score = int(hashlib.md5(seed.encode()).hexdigest(), 16) % 101
        await interaction.response.send_message(
            f"💘 {user1.display_name} × {user2.display_name} の相性: **{score}%**"
        )

    # ───────── ⑱ レベル確認 ─────────
    @app_commands.command(name="level", description="自分(または指定ユーザー)のレベルを確認します")
    @app_commands.describe(user="調べたいユーザー(省略で自分)")
    async def level(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user
        xp = get_xp(interaction.guild_id, user.id)
        lvl = xp_to_level(xp)
        await interaction.response.send_message(f"🍅 {user.display_name} は **Lv.{lvl}**(XP: {xp})")

    # ───────── ⑲ ランキング ─────────
    @app_commands.command(name="ranking", description="サーバー内の発言ランキングTOP5を表示します")
    async def ranking(self, interaction: discord.Interaction):
        top = get_ranking(interaction.guild_id, 5)
        if not top:
            await interaction.response.send_message("まだランキングデータがありません")
            return
        lines = []
        for i, (uid, xp) in enumerate(top, start=1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"ID:{uid}"
            lines.append(f"{i}位: {name}(Lv.{xp_to_level(xp)} / XP {xp})")
        await interaction.response.send_message("🏆 発言ランキング\n" + "\n".join(lines))

    # ───────── ⑳ 駄洒落 ─────────
    @app_commands.command(name="dajare", description="ランダムな駄洒落を言います")
    async def dajare(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🍅 {random.choice(DAJARE)}")

    # ───────── おまけ:究極の選択 ─────────
    @app_commands.command(name="wouldyourather", description="究極の二択質問をします")
    async def wouldyourather(self, interaction: discord.Interaction):
        a, b = random.choice(WOULD_YOU_RATHER)
        await interaction.response.send_message(f"🤔 究極の選択!\nA: {a}\nB: {b}")


async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))
