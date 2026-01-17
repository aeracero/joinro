import discord
from discord.ext import commands
from discord import ui
import asyncio
from objects import *

# --- 常設用の起動ボタン ---
class Launcher(ui.View):
    def __init__(self, bot_system):
        super().__init__(timeout=None)
        self.bot_system = bot_system # Cog本体と連携

    @ui.button(label="🐺 人狼ゲームの部屋を作成", style=discord.ButtonStyle.primary, custom_id="ww_create_room")
    async def create_room(self, interaction: discord.Interaction, button: ui.Button):
        # ここで直接 create_room_logic を呼び出します（on_interactionは使いません）
        await self.bot_system.create_room_logic(interaction)

# --- 設定モーダル ---
class SettingsModal(ui.Modal, title="ゲーム設定"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        
        self.ww = ui.TextInput(label="人狼", default=str(room.settings["werewolf"]))
        self.seer = ui.TextInput(label="占い", default=str(room.settings["seer"]))
        self.bg = ui.TextInput(label="狩人", default=str(room.settings["bodyguard"]))
        self.fox = ui.TextInput(label="妖狐", default=str(room.settings["fox"]))
        self.mas = ui.TextInput(label="共有者", default=str(room.settings["mason"]))
        
        self.add_item(self.ww)
        self.add_item(self.seer)
        self.add_item(self.bg)
        self.add_item(self.fox)
        self.add_item(self.mas)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.room.settings["werewolf"] = int(self.ww.value)
            self.room.settings["seer"] = int(self.seer.value)
            self.room.settings["bodyguard"] = int(self.bg.value)
            self.room.settings["fox"] = int(self.fox.value)
            self.room.settings["mason"] = int(self.mas.value)
            await interaction.response.send_message("設定を更新しました", ephemeral=True)
            await self.callback()
        except:
            await interaction.response.send_message("数字を入力してください", ephemeral=True)

# --- ゲーム内アクションView ---
class NightActionView(ui.View):
    def __init__(self, room, player, action_type, callback):
        super().__init__(timeout=120)
        self.callback = callback
        self.action_type = action_type
        self.player = player
        
        options = []
        for p in room.get_alive():
            if p.id == player.id: continue
            options.append(discord.SelectOption(label=p.name, value=str(p.id)))
        
        if not options: options.append(discord.SelectOption(label="なし", value="none"))
        
        select = ui.Select(placeholder="対象を選択", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, itx):
        tid = itx.data['values'][0]
        tid = int(tid) if tid != "none" else None
        await self.callback(itx, self.player, self.action_type, tid)

class VoteView(ui.View):
    def __init__(self, room, player, callback):
        super().__init__(timeout=60)
        self.callback = callback
        options = [discord.SelectOption(label=p.name, value=str(p.id)) for p in room.get_alive() if p.id != player.id]
        select = ui.Select(placeholder="投票先", options=options)
        select.callback = self.on_vote
        self.add_item(select)
    
    async def on_vote(self, itx):
        await self.callback(itx, int(itx.data['values'][0]))


# --- Bot本体 ---
class WerewolfSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rooms = {} 
        # on_interaction は削除しました（二重反応防止のため）

    @commands.command()
    async def panel(self, ctx):
        """常設ボタン設置"""
        embed = discord.Embed(
            title="🐺 人狼ゲーム", 
            description="下のボタンを押すと、このチャンネルで参加募集を開始します。",
            color=0x2c2c2c
        )
        await ctx.send(embed=embed, view=Launcher(self))
        try: await ctx.message.delete()
        except: pass

    # ボタンからもコマンドからも呼ばれる処理
    async def create_room_logic(self, interaction_or_ctx):
        # 呼び出し元が Interaction(ボタン) か Context(コマンド) かで分岐
        if isinstance(interaction_or_ctx, discord.Interaction):
            channel = interaction_or_ctx.channel
            # まだ応答していない場合のみ send_message する
            if not interaction_or_ctx.response.is_done():
                await interaction_or_ctx.response.send_message("募集を開始しました", ephemeral=True)
            else:
                # 万が一応答済みの場合は followup を使う
                await interaction_or_ctx.followup.send("募集を開始しました", ephemeral=True)
        else:
            channel = interaction_or_ctx.channel
            await channel.send("募集を開始しました")

        if channel.id in self.rooms:
            # 既に部屋がある場合
            msg = "既に募集中かゲーム中です"
            if isinstance(interaction_or_ctx, discord.Interaction):
                await interaction_or_ctx.followup.send(msg, ephemeral=True)
            else:
                await channel.send(msg)
            return

        # 部屋作成
        room = GameRoom(channel)
        self.rooms[channel.id] = room

        # --- ロビーUI ---
        async def update_panel():
            s = room.settings
            desc = f"🐺:{s['werewolf']} 🔮:{s['seer']} 🛡️:{s['bodyguard']} 🦊:{s['fox']} 🎎:{s['mason']}"
            embed = discord.Embed(title="参加者募集中", description=desc, color=0x00ff00)
            p_names = "\n".join([p.name for p in room.players.values()])
            embed.add_field(name=f"参加者 {len(room.players)}名", value=p_names or "なし")
            
            try: await msg.edit(embed=embed, view=view)
            except: pass

        class LobbyView(ui.View):
            def __init__(self): super().__init__(timeout=None)
            @ui.button(label="参加", style=discord.ButtonStyle.success)
            async def join(self, itx, btn):
                if itx.user.id not in room.players: room.join(itx.user)
                else: room.leave(itx.user)
                await itx.response.send_message("更新しました", ephemeral=True)
                await update_panel()
            @ui.button(label="設定", style=discord.ButtonStyle.secondary)
            async def setting(self, itx, btn):
                await itx.response.send_modal(SettingsModal(room, update_panel))
            @ui.button(label="開始", style=discord.ButtonStyle.danger)
            async def start(self, itx, btn):
                if len(room.players) < 2: 
                    await itx.response.send_message("人数不足です（最低2人）", ephemeral=True)
                    return
                await itx.response.send_message("ゲーム開始！")
                self.stop()
                room.phase = "STARTING"

        view = LobbyView()
        msg = await channel.send(embed=discord.Embed(title="準備中..."), view=view)
        await update_panel()

        # 待機ループ
        while room.phase == "WAITING":
            await asyncio.sleep(1)
            if room.phase == "STARTING": break
        
        await self.run_game(channel.id)

    async def run_game(self, channel_id):
        room = self.rooms[channel_id]
        room.assign_roles()
        
        # --- 役職通知 ---
        masons = [p for p in room.players.values() if p.role == ROLE_MASON]
        mason_names = ", ".join([p.name for p in masons])

        for p in room.players.values():
            user = self.bot.get_user(p.id)
            if not user: continue
            
            text = f"あなたの役職は **{p.role}** です。\n"
            if p.role == ROLE_WEREWOLF:
                mates = [x.name for x in room.players.values() if x.role == ROLE_WEREWOLF and x.id != p.id]
                text += f"仲間の人狼: {', '.join(mates) if mates else 'なし'}"
            elif p.role == ROLE_MASON:
                text += f"共有者たち: {mason_names}"
            elif p.role == ROLE_FOX:
                text += "占われると死亡しますが、最後まで生き残れば勝利です。"

            try: await user.send(text)
            except: pass
        
        await room.channel.send("🌙 ゲーム開始。DMを確認してください。")

        day = 1
        while True:
            # === 夜 ===
            room.phase = "NIGHT"
            room.night_actions = {}
            for p in room.players.values(): p.cursed_death = False

            async def night_cb(itx, player, act, tid):
                target = room.players[tid] if tid else None
                t_name = target.name if target else "なし"
                
                if act == "divine":
                    result = "人狼" if target.is_wolf_side else "人間"
                    if target.role == ROLE_FOX: # 呪殺
                        target.cursed_death = True
                    await itx.response.send_message(f"占い結果: {t_name} は **{result}** です。", ephemeral=True)
                else:
                    room.night_actions[act] = tid
                    await itx.response.send_message(f"{t_name} を選択。", ephemeral=True)

            tasks_list = []
            for p in room.get_alive():
                user = self.bot.get_user(p.id)
                view = None
                if p.role == ROLE_WEREWOLF:
                    view = NightActionView(room, p, "bite", night_cb)
                elif p.role == ROLE_SEER:
                    view = NightActionView(room, p, "divine", night_cb)
                elif p.role == ROLE_BODYGUARD:
                    view = NightActionView(room, p, "guard", night_cb)
                
                if view: tasks_list.append(user.send(f"【{day}日目夜】 行動してください", view=view))
            
            if tasks_list: await asyncio.gather(*tasks_list)
            await asyncio.sleep(20)

            # === 朝 ===
            room.phase = "DAY"
            dead = []
            
            bite_target = room.night_actions.get("bite")
            guard_target = room.night_actions.get("guard")
            if bite_target and bite_target != guard_target:
                dead.append(room.players[bite_target])
            
            for p in room.players.values():
                if p.cursed_death: dead.append(p)
            
            msg = f"🌞 **{day}日目の朝**\n"
            dead = list(set(dead))
            if dead:
                for d in dead: d.is_alive = False
                msg += f"昨晩、**{', '.join([d.name for d in dead])}** が死亡しました。"
            else:
                msg += "昨晩は犠牲者がいませんでした。"
            
            await room.channel.send(msg)

            if room.check_winner():
                await room.channel.send(f"🎉 **{room.check_winner()}** の勝利！")
                break

            # 議論 & 投票
            await room.channel.send(f"議論開始 ({room.settings['discussion_time']}秒)")
            await asyncio.sleep(room.settings['discussion_time'])
            
            room.votes = {}
            async def vote_cb(itx, tid):
                room.votes[itx.user.id] = tid
                await itx.response.send_message("投票済", ephemeral=True)

            vt = []
            for p in room.get_alive():
                u = self.bot.get_user(p.id)
                vt.append(u.send("投票してください", view=VoteView(room, p, vote_cb)))
            await asyncio.gather(*vt)
            await asyncio.sleep(15)

            # 開票
            if room.votes:
                counts = {}
                for tid in room.votes.values(): counts[tid] = counts.get(tid, 0) + 1
                max_v = max(counts.values())
                cands = [k for k,v in counts.items() if v == max_v]
                exec_id = random.choice(cands)
                exec_p = room.players[exec_id]
                exec_p.is_alive = False
                await room.channel.send(f"投票の結果、**{exec_p.name}** が処刑されました。")
            else:
                await room.channel.send("投票なし。処刑見送り。")

            if room.check_winner():
                await room.channel.send(f"🎉 **{room.check_winner()}** の勝利！")
                break
            
            day += 1
        
        del self.rooms[channel_id]

async def setup(bot):
    await bot.add_cog(WerewolfSystem(bot))