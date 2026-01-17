# config.py
import os
from dotenv import load_dotenv

# ローカルで .env ファイルがある場合は読み込む（Railway上では無視されます）
load_dotenv()

# Railwayの環境変数 'DISCORD_TOKEN' を読み込む
TOKEN = os.getenv('DISCORD_TOKEN')

# トークンが設定されていない場合のエラーハンドリング
if TOKEN is None:
    raise ValueError("トークンが見つかりません。RailwayのVariables設定を確認してください。")

PREFIX = '!'