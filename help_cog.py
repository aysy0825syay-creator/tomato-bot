"""
ヘルプコマンド
- コマンドが多いため、カテゴリ(Cogごと)に分けて選択式で表示する
"""
import discord
from discord import app_commands
from discord.ext import commands

CATEGORY_LABELS = {
    "FunCog": ("🎉 娯楽系", "サイコロ、おみくじ、しりとりなど遊び系コマンド"),
    "ModerationCog": ("🛡️ モデレーション", "警告・キック・BAN・全チャンネル削除・一括削除など"),
    "AntiSpamCog": ("🚫 スパム対策", "スパムフィルターの設定"),
    "LoggingCog": ("📝 編集・削除ログ", "メッセージの編集・削除を記録"),
    "WelcomeCog": ("👋 歓迎・自動ロール", "歓迎メッセージ・自動ロール付与"),
    "ReactionRoleCog": ("🎭 リアクションロール", "絵文字でロール付与"),
    "TicketCog": ("🎫 チケット", "個別相談チャンネルの作成"),
    "UtilityCog": ("🧰 実用ツール", "翻訳・天気・計算・QRコード・Pingなど"),
    "StickyCog": ("📌 固定メッセージ", "チャンネル最下部への固定表示"),
    "VerifyCog": ("✅ 認証パネル", "ボタン/リアクションで認証しロール付与"),
    "GiveawayCog": ("🎁 抽選(ギブアウェイ)", "プレゼント企画の自動抽選"),
    "WordFilterCog": ("🚱 NGワードフィルター", "指定ワードを含むメッセージを自動削除"),
    "LinkFilterCog": ("🔗 リンク許可リスト", "許可したドメイン以外のリンクを自動削除"),
    "StatsCog": ("📊 サーバー統計", "メンバー数などの統計情報"),
    "BirthdayCog": ("🎂 誕生日", "誕生日登録とお祝い通知"),
    "EventCog": ("📅 予定リマインダー", "指定日時に予定をお知らせ"),
    None: ("⚙️ 基本設定", "入退室ログ・AI応答などの基本設定"),
}


class HelpSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        options = []
        for cog_name, (label, desc) in CATEGORY_LABELS.items():
            options.append(discord.SelectOption(label=label, description=desc, value=str(cog_name)))
        super().__init__(placeholder="カテゴリを選んでください", options=options)

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        commands_list = []
        for cmd in self.bot.tree.walk_commands(guild=interaction.guild):
            cog_name = cmd.binding.__class__.__name__ if cmd.binding else "None"
            if target == "None" and cmd.binding is not None:
                continue
            if target != "None" and cog_name != target:
                continue
            commands_list.append(f"`/{cmd.name}` — {cmd.description}")

        label = CATEGORY_LABELS.get(target if target != "None" else None, ("カテゴリ", ""))[0]
        embed = discord.Embed(
            title=f"{label} のコマンド一覧",
            description="\n".join(commands_list) if commands_list else "コマンドがありません",
            color=discord.Color.orange(),
        )
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=120)
        self.add_item(HelpSelect(bot))


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="ボットのコマンド一覧をカテゴリ別に表示します")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🍅 とまとBot コマンド一覧",
            description="下のメニューからカテゴリを選んでください。",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, view=HelpView(self.bot), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
