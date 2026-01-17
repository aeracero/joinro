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
BOT_VERSION = "0.2 (Beta)"

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
        
        # ボタンの再登録 (永続化)
        from cogs.werewolf import Launcher
        self.add_view(Launcher(None))
        print("All cogs loaded & Views registered.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        await self.change_presence(activity=discord.Game(name=f"オンパロス戦線 v{BOT_VERSION}"))

bot = WerewolfBot()

@bot.event
async def on_message(message):
    if message.author.bot: return

    if bot.user in message.mentions:
        embed = discord.Embed(
            title="⚔️ オンパロス戦線 Bot",
            description="Discordで遊ぶ、火種を巡る人狼ゲーム。",
            color=0x9b59b6
        )
        embed.add_field(name="⚙️ Version", value=BOT_VERSION, inline=False)
        cmd_text = (
            "**`!panel`**\n"
            "ロビーパネルを設置します。（推奨）\n\n"
            "**`!wclose`**\n"
            "現在のチャンネルの部屋を強制削除します。"
        )
        embed.add_field(name="📜 コマンド一覧", value=cmd_text, inline=False)
        embed.set_footer(text="Developed by You")
        await message.channel.send(embed=embed)

    await bot.process_commands(message)

if __name__ == '__main__':
    bot.run(config.TOKEN)