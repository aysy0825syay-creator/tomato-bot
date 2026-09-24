"""
サーバー(ギルド)ごとの設定を config.json に保存・読み込みするモジュール。
"""
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
        return {**DEFAULT_GUILD_CONFIG, **data.get(str(guild_id), {})}


def update_guild_config(guild_id: int, **kwargs) -> dict:
    """指定ギルドの設定を更新して保存する。更新後の設定を返す。"""
    with _lock:
        data = _load_all()
        current = {**DEFAULT_GUILD_CONFIG, **data.get(str(guild_id), {})}
        current.update(kwargs)
        data[str(guild_id)] = current
        _save_all(data)
        return current
