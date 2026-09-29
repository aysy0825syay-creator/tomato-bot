"""
サーバー(ギルド)ごとの設定を config.json に保存・読み込みするモジュール。
"""
import copy
import json
import os
import threading

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
_lock = threading.Lock()

DEFAULT_GUILD_CONFIG = {
    "log_enabled": False,      # 入退室ログを記録するか
    "join_channel_id": None,   # 入室ログを送るチャンネルID
    "leave_channel_id": None,  # 退室ログを送るチャンネルID
    "ai_enabled": False,       # AI応答を有効にするか
    "ai_channel_id": None,     # AI応答するチャンネルID
    "modlog_enabled": False,       # メッセージ編集・削除ログ
    "modlog_channel_id": None,
    "welcome_enabled": False,      # 歓迎メッセージ
    "welcome_channel_id": None,
    "welcome_message": "🍅 {user} さん、ようこそ **{server}** へ!",
    "autorole_id": None,            # 入室時に自動付与するロール
    "antispam_enabled": False,      # スパムフィルター
    "ticket_category_id": None,     # チケットチャンネルを作成するカテゴリ
    "ticket_staff_role_id": None,   # チケットを見られるスタッフロール
    "ngword_enabled": False,        # NGワードフィルター
    "linkfilter_enabled": False,    # リンク許可リスト
    "birthday_channel_id": None,    # 誕生日お祝い通知チャンネル
    "protect_log_channel_id": None,      # 荒らし対策の通知チャンネル
    "protect_min_account_days": 0,       # 新規アカウント制限(0=無効)
    "protect_join_raid_limit": 0,        # 大量参加の検知人数(0=無効)
    "protect_anti_nuke": False,          # チャンネル大量作成・削除の検知
    "protect_mass_mention_limit": 0,     # メンション乱用の検知件数(0=無効)
    "protect_block_bots": False,         # オーナー以外のBot追加をキック
    "punish_log_channel_id": None,       # 処罰ログを送るチャンネル
    "botspam_enabled": False,            # Botスパム対策
    "botspam_limit": 6,                  # 8秒間に何通でBotスパムとみなすか
    "botlink_enabled": False,            # Botから送られるリンクの対策
    "botlink_whitelist": [],             # Botスパム/Botリンク対策の対象外にするBotのID
    "linkfilter_excluded_channels": [],  # リンク対策の対象外にするチャンネルID
    "antispam_excluded_channels": [],    # スパム対策(人間)の対象外にするチャンネルID
    "botspam_excluded_channels": [],     # Botスパム対策の対象外にするチャンネルID
    "botlink_excluded_channels": [],     # Botリンク対策の対象外にするチャンネルID
}


def _load_all() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_all(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_guild_config(guild_id: int) -> dict:
    """指定ギルドの設定を取得する。存在しなければデフォルトを返す。"""
    with _lock:
        data = _load_all()
        merged = copy.deepcopy(DEFAULT_GUILD_CONFIG)
        merged.update(data.get(str(guild_id), {}))
        return merged


def update_guild_config(guild_id: int, **kwargs) -> dict:
    """指定ギルドの設定を更新して保存する。更新後の設定を返す。"""
    with _lock:
        data = _load_all()
        current = copy.deepcopy(DEFAULT_GUILD_CONFIG)
        current.update(data.get(str(guild_id), {}))
        current.update(kwargs)
        data[str(guild_id)] = current
        _save_all(data)
        return current
