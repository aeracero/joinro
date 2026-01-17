# main.py
import discord
from discord.ext import commands
import os
import config

# Intentsの設定
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class WerewolfBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=config.PREFIX,
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # Cogsの読み込み
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
        
        # ★ここが重要: 永続的なボタン（View）を再登録する
        # これにより、Bot再起動後も「参加ボタン」などが動き続けます
        from cogs.werewolf import Launcher
        self.add_view(Launcher(None))
        print("All cogs loaded & Views registered.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        await self.change_presence(activity=discord.Game(name="人狼ゲーム"))

bot = WerewolfBot()

if __name__ == '__main__':
    bot.run(config.TOKEN)