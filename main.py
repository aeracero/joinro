# main.py
import discord
from discord.ext import commands
import os
import config

# Intentsの設定
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# ★バージョン更新
BOT_VERSION = "0.6.0"

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
        
        # Launcherのビューを永続化（再起動後もボタンが動くように）
        from cogs.werewolf import Launcher
        self.add_view(Launcher(None))
        print("All cogs loaded & Views registered.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        # アクティビティを「人狼ゲーム」に変更
        await self.change_presence(activity=discord.Game(name=f"人狼ゲーム v{BOT_VERSION}"))

bot = WerewolfBot()

if __name__ == '__main__':
    bot.run(config.TOKEN)