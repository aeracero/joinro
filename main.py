# main.py
import discord
from discord.ext import commands
import os
import config

# Intentsの設定
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# バージョン情報
BOT_VERSION = "0.1 (Beta)"

class WerewolfBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=config.PREFIX,
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
        
        # ボタンの再登録
        from cogs.werewolf import Launcher
        self.add_view(Launcher(None))
        print("All cogs loaded & Views registered.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        await self.change_presence(activity=discord.Game(name=f"人狼ゲーム v{BOT_VERSION}"))

bot = WerewolfBot()

# ★ここを追加: メンションされた時の反応
@bot.event
async def on_message(message):
    # Bot自身のメッセージは無視
    if message.author.bot:
        return

    # Botがメンションされたかチェック (例: @WerewolfBot こんにちは)
    if bot.user in message.mentions:
        embed = discord.Embed(
            title="🐺 人狼Bot System",
            description="Discordで本格的な人狼ゲームができるBotです。",
            color=0x3498db # 青色
        )
        # バージョン情報
        embed.add_field(name="⚙️ Version", value=BOT_VERSION, inline=False)
        
        # コマンド一覧
        cmd_text = (
            "**`!panel`**\n"
            "募集用の常設ボタンパネルを設置します。（推奨）\n\n"
            "**`!create`**\n"
            "ボタンを使わずに、手動で募集を開始します。"
        )
        embed.add_field(name="📜 コマンド一覧", value=cmd_text, inline=False)
        
        # フッター
        embed.set_footer(text="Developed by You")

        await message.channel.send(embed=embed)

    # ★重要: これがないと他のコマンド(!panelなど)が動かなくなります
    await bot.process_commands(message)

if __name__ == '__main__':
    bot.run(config.TOKEN)