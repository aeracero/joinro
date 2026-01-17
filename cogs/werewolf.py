import discord
from discord.ext import commands
from discord import ui
import asyncio
import random
from objects import *

# バージョン情報
BOT_VERSION = "0.2 (Beta)"

# --- Launcher (常設ボタン) ---
class Launcher(ui.View):
    def __init__(self, bot_system=None):
        super().__init__(timeout=None)
        self.bot_system = bot_system
    
    @ui.button(label="⚔️ オンパロス戦線を作成", style=discord.ButtonStyle.primary, custom_id="ww_create_room")
    async def create_room(self, interaction: discord.Interaction, button: ui.Button):
        system = self.bot_system
        if system is None:
            system = interaction.client.get_cog("WerewolfSystem")
        if system:
            await system.create_room_logic(interaction)
        else:
            await interaction.response.send_message("システムエラー: Botを再起動してください。", ephemeral=True)

# --- GM用: プレイヤー操作View ---
class GMPlayerActionView(ui.View):
    def __init__(self, room, target_player):
        super().__init__(timeout=60)
        self.room = room
        self.target = target_player

    @ui.button(label="📩 DM送信", style=discord.ButtonStyle.primary)
    async def send_dm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(GMDMModal(self.target))

    @ui.button(label="💀 死亡認定", style=discord.ButtonStyle.danger)
    async def kill_player(self, interaction: discord.Interaction, button: ui.Button):
        self.target.is_alive = False
        await interaction.response.send_message(f"💀 **{self.target.name}** を死亡判定にしました。", ephemeral=True)
        await self.room.channel.send(f"💀 GMの判定により、**{self.target.name}** の火種が奪われ、脱落しました。")

    @ui.button(label="🔍 役職透視", style=discord.ButtonStyle.secondary)
    async def check_role(self, interaction: discord.Interaction, button: ui.Button):
        status = []
        if self.target.role == ROLE_MORDIS: status.append(f"復活権:{'有' if self.target.mordis_revive_available else '無'}")
        if self.target.role == ROLE_PHAINON: status.append("x2票")
        status_str = f" ({', '.join(status)})" if status else ""
        msg = f"👤 **{self.target.name}**\n役職: **{self.target.role}**\n状態: {'🟢生存' if self.target.is_alive else '💀死亡'}{status_str}"
        await interaction.response.send_message(msg, ephemeral=True)

class GMDMModal(ui.Modal, title="GMメッセージ送信"):
    def __init__(self, target):
        super().__init__()
        self.target = target
        self.msg = ui.TextInput(label="メッセージ内容", style=discord.TextStyle.paragraph)
        self.add_item(self.msg)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            embed = discord.Embed(title="📩 GMからのメッセージ", description=self.msg.value, color=0xff00ff)
            await self.target.member.send(embed=embed)
            await interaction.response.send_message(f"{self.target.name} に送信しました。", ephemeral=True)
        except: await interaction.response.send_message("送信失敗", ephemeral=True)

class GMPlayerSelectView(ui.View):
    def __init__(self, room):
        super().__init__(timeout=60)
        self.room = room
        options = []
        for p in room.players.values():
            status = "🟢" if p.is_alive else "💀"
            options.append(discord.SelectOption(label=p.name, description=f"{status} {p.role}", value=str(p.id)))
        select = ui.Select(placeholder="操作するプレイヤーを選択...", options=options)
        select.callback = self.on_select
        self.add_item(select)
    async def on_select(self, interaction: discord.Interaction):
        target_id = int(interaction.data['values'][0])
        target = self.room.players.get(target_id)
        if target:
            await interaction.response.send_message(f"対象: **{target.name}**", view=GMPlayerActionView(self.room, target), ephemeral=True)
        else:
            await interaction.response.send_message("プレイヤーが見つかりません。", ephemeral=True)

class GMControlView(ui.View):
    def __init__(self, room):
        super().__init__(timeout=None)
        self.room = room

    @ui.button(label="📋 全体状況", style=discord.ButtonStyle.secondary, row=1)
    async def check_status(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        embed = discord.Embed(title="🕵️ GMダッシュボード", color=0x2b2d31)
        alive_txt, dead_txt = "", ""
        for p in self.room.players.values():
            icon = "🟢" if p.is_alive else "💀"
            line = f"{icon} **{p.name}** : `{p.role}`\n"
            if p.is_alive: alive_txt += line
            else: dead_txt += line
        embed.add_field(name="生存", value=alive_txt or "なし", inline=False)
        if dead_txt: embed.add_field(name="死亡", value=dead_txt, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="👤 プレイヤー操作", style=discord.ButtonStyle.primary, row=1)
    async def manage_player(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_message("対象を選択:", view=GMPlayerSelectView(self.room), ephemeral=True)

    @ui.button(label="💥 強制終了", style=discord.ButtonStyle.danger, row=2)
    async def close_room(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        self.room.phase = "CANCELLED"
        await interaction.response.send_message("部屋を解散しました。", ephemeral=True)
        await self.room.channel.send("🛑 GMによりゲームが強制終了されました。")

    def check_perm(self, interaction):
        if not self.room.gm_user or interaction.user.id != self.room.gm_user.id:
            return False
        return True

# --- 設定モーダル ---
class SettingsModal(ui.Modal, title="設定"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        curr = "1" if room.settings["mode"] == "MANUAL" else "0"
        self.mode_input = ui.TextInput(label="モード (0:自動 / 1:手動GM)", default=curr, max_length=1)
        self.lykos = ui.TextInput(label="ライコス", default=str(room.settings["lykos"]))
        self.tribbie = ui.TextInput(label="トリビー", default=str(room.settings["tribbie"]))
        self.specials = ui.TextInput(label="剣,モ,キ,フ (例:1,0,0,0)", default=f"{room.settings['swordmaster']},{room.settings['mordis']},{room.settings['cyrene']},{room.settings['phainon']}")
        self.add_item(self.mode_input)
        self.add_item(self.lykos)
        self.add_item(self.tribbie)
        self.add_item(self.specials)

    async def on_submit(self, itx):
        try:
            self.room.settings["mode"] = "MANUAL" if self.mode_input.value == "1" else "AUTO"
            self.room.settings["lykos"] = int(self.lykos.value)
            self.room.settings["tribbie"] = int(self.tribbie.value)
            sp = self.specials.value.split(',')
            if len(sp) >= 1: self.room.settings["swordmaster"] = int(sp[0])
            if len(sp) >= 2: self.room.settings["mordis"] = int(sp[1])
            if len(sp) >= 3: self.room.settings["cyrene"] = int(sp[2])
            if len(sp) >= 4: self.room.settings["phainon"] = int(sp[3])
            m_str = "手動GM" if self.room.settings["mode"] == "MANUAL" else "全自動"
            await itx.response.send_message(f"設定更新: {m_str}", ephemeral=True)
            await self.callback()
        except: await itx.response.send_message("エラー", ephemeral=True)

# --- 投票View ---
class VoteView(ui.View):
    def __init__(self, room, player):
        super().__init__(timeout=None)
        self.room = room
        self.player = player
        options = []
        for p in room.get_alive():
            if p.id == player.id: continue
            options.append(discord.SelectOption(label=p.name, value=str(p.id)))
        options.append(discord.SelectOption(label="スキップ (投票放棄)", value="skip", description="誰も処刑したくない場合"))
        select = ui.Select(placeholder="追放する者を選択...", options=options)
        select.callback = self.on_vote
        self.add_item(select)
    
    async def on_vote(self, interaction: discord.Interaction):
        if interaction.user.id in self.room.votes:
            await interaction.response.send_message("⚠️ 既に投票済みです。", ephemeral=True)
            return
        
        val = interaction.data['values'][0]
        if val == "skip":
            self.room.votes[interaction.user.id] = "skip"
            target_name = "スキップ"
        else:
            target_id = int(val)
            self.room.votes[interaction.user.id] = target_id
            target_p = self.room.players.get(target_id)
            target_name = target_p.name if target_p else "不明"

        if self.room.gm_user:
            try: await self.room.gm_user.send(f"🗳️ **{self.player.name}** -> {target_name}")
            except: pass
        
        await interaction.response.edit_message(content=f"✅ **{target_name}** に投票しました。", view=None)

        if len(self.room.votes) >= len(self.room.get_alive()):
            await self.tally_votes()

    async def tally_votes(self):
        channel = self.room.channel
        tally = {}
        for voter_id, target in self.room.votes.items():
            voter = self.room.players.get(voter_id)
            weight = voter.vote_weight if voter else 1
            tally[target] = tally.get(target, 0) + weight

        await channel.send("🗳️ **投票終了**。開票を行います...")
        await asyncio.sleep(2)

        if not tally:
            await channel.send("投票なし。")
            return

        max_votes = max(tally.values())
        candidates = [t for t, count in tally.items() if count == max_votes]

        if "skip" in candidates:
            await channel.send("投票の結果、**スキップ** が多数となりました。\n本日の処刑は見送られます。")
            return
        
        final_target_id = random.choice(candidates)
        executed_player = self.room.players.get(final_target_id)
        
        if executed_player:
            executed_player.is_alive = False
            self.room.last_executed = executed_player
            if executed_player.role == ROLE_CYRENE:
                self.room.cyrene_executed = True
                await channel.send(f"💀 処刑された **{executed_player.name}** は... **{ROLE_CYRENE}** でした！！\n禁忌に触れたため、オンパロス陣営は敗北となります。")
            else:
                await channel.send(f"💀 投票の結果、**{executed_player.name}** が選ばれました。\n火種を奪われ、オンパロスの地より追放されます。")
        
        winner = self.room.check_winner()
        if winner:
            embed = discord.Embed(title="決着", description=f"勝者: **{winner}**", color=0xf1c40f)
            det = ""
            for p in self.room.players.values(): det += f"{p.name}: {p.role} ({'生' if p.is_alive else '死'})\n"
            embed.add_field(name="内訳", value=det)
            await channel.send(embed=embed)


# --- Action View ---
class NightActionView(ui.View):
    def __init__(self, room, player, action_type, callback):
        super().__init__(timeout=120)
        self.room = room
        self.player = player
        self.action_type = action_type
        self.callback = callback
        options = []
        for p in room.get_alive():
            if p.id == player.id: continue
            options.append(discord.SelectOption(label=p.name, value=str(p.id)))
        if not options: options.append(discord.SelectOption(label="なし", value="none"))
        select = ui.Select(placeholder="対象を選択", options=options)
        select.callback = self.on_select
        self.add_item(select)
    
    async def on_select(self, itx):
        tid = int(itx.data['values'][0]) if itx.data['values'][0] != "none" else None
        await self.callback(itx, self.player, self.action_type, tid)


# --- Bot System ---
class WerewolfSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rooms = {}

    @commands.command()
    async def panel(self, ctx):
        room_list = ""
        if self.rooms:
            for ch_id, room in self.rooms.items():
                ch = self.bot.get_channel(ch_id)
                ch_name = ch.name if ch else "不明"
                mode = "手動" if room.settings["mode"] == "MANUAL" else "自動"
                room_list += f"• **{ch_name}**: {len(room.players)}人 ({mode})\n"
        else: room_list = "現在進行中のルームはありません。"
        
        embed = discord.Embed(title="⚔️ オンパロス戦線 ロビー", color=0x8e44ad)
        embed.add_field(name="ルーム一覧", value=room_list, inline=False)
        embed.add_field(name="新規作成", value="下のボタンから作成できます。", inline=False)
        
        await ctx.send(embed=embed, view=Launcher(self))
        try: await ctx.message.delete()
        except: pass

    @commands.command()
    async def wclose(self, ctx):
        if ctx.channel.id in self.rooms:
            self.rooms[ctx.channel.id].phase = "CANCELLED"
            await ctx.send("💥 ルームを解散・削除しました。")
            if ctx.channel.id in self.rooms:
                del self.rooms[ctx.channel.id]
        else:
            await ctx.send("ここにはルームがありません。")

    async def check_gm(self, ctx):
        if ctx.channel.id not in self.rooms: return None
        room = self.rooms[ctx.channel.id]
        if room.settings["mode"] != "MANUAL": return None
        if room.gm_user and ctx.author.id != room.gm_user.id: return None
        return room

    @commands.command()
    async def wstatus(self, ctx):
        room = await self.check_gm(ctx)
        if not room: return
        await ctx.message.delete()
        embed = discord.Embed(title="🕵️ GMステータス", color=0x2b2d31)
        alive_txt, dead_txt = "", ""
        for p in room.players.values():
            line = f"{'🟢' if p.is_alive else '💀'} **{p.name}** : `{p.role}`\n"
            if p.is_alive: alive_txt += line
            else: dead_txt += line
        embed.add_field(name="生存", value=alive_txt or "なし")
        if dead_txt: embed.add_field(name="死亡", value=dead_txt)
        await ctx.author.send(embed=embed)

    @commands.command()
    async def wvote(self, ctx):
        room = await self.check_gm(ctx)
        if not room: return
        await ctx.message.delete()
        await ctx.send("🗳️ **投票フェーズ** を開始します。")
        room.votes = {} 
        tasks = []
        for p in room.get_alive():
            view = VoteView(room, p)
            tasks.append(self.bot.get_user(p.id).send("【投票】 追放する者を選んでください（1回のみ）", view=view))
        await asyncio.gather(*tasks)

    @commands.command()
    async def wnight(self, ctx):
        room = await self.check_gm(ctx)
        if not room: return
        await ctx.message.delete()
        await ctx.send("🌙 **夜のアクション** を開始します。")
        
        async def manual_night_cb(itx, player, act, tid):
            target = room.players[tid] if tid else None
            t_name = target.name if target else "なし"
            if act == "divine":
                res = "ライコス" if target.is_wolf_side else "人間"
                await itx.response.edit_message(content=f"🔮 占い結果: **{t_name}** は **{res}** です。", view=None)
                if room.gm_user: await room.gm_user.send(f"🔮 {player.name} -> {t_name} : {res}")
            else:
                act_str = {"steal":"強奪", "guard":"護衛", "slash":"辻斬り"}.get(act, act)
                await itx.response.edit_message(content=f"✅ **{t_name}** を選択しました。", view=None)
                if room.gm_user: await room.gm_user.send(f"🌙 {player.name} ({player.role}) -> {t_name} ({act_str})")

        tasks = []
        for p in room.get_alive():
            view = None
            msg = ""
            if p.role == ROLE_LYKOS: view = NightActionView(room, p, "steal", manual_night_cb); msg="【強奪】 誰を狙いますか？"
            elif p.role == ROLE_TRIBBIE: view = NightActionView(room, p, "divine", manual_night_cb); msg="【占い】 誰を占いますか？"
            elif p.role == ROLE_SIRENS: view = NightActionView(room, p, "guard", manual_night_cb); msg="【護衛】 誰を守りますか？"
            elif p.role == ROLE_SWORDMASTER: view = NightActionView(room, p, "slash", manual_night_cb); msg="【辻斬り】 誰を狙いますか？"
            if view: tasks.append(self.bot.get_user(p.id).send(msg, view=view))
        await asyncio.gather(*tasks)

    # --- Listener: メンション時の反応 (★新規追加) ---
    @commands.Cog.listener()
    async def on_message(self, message):
        # Bot自身のメッセージは無視
        if message.author.bot: return

        # メンションされた場合
        if self.bot.user in message.mentions:
            # 1. ゲーム進行中のチャンネルの場合 -> 戦況を表示
            if message.channel.id in self.rooms:
                room = self.rooms[message.channel.id]
                
                # 公開情報のみのEmbedを作成
                alive_list = [p.name for p in room.players.values() if p.is_alive]
                dead_list = [p.name for p in room.players.values() if not p.is_alive]
                
                # フェーズ名を日本語化
                phase_map = {"WAITING":"待機中", "STARTING":"開始処理中", "DAY":"昼 (議論)", "NIGHT":"夜 (行動)"}
                phase_ja = phase_map.get(room.phase, room.phase)

                embed = discord.Embed(title=f"📊 現在の戦況 - {phase_ja}", color=0x2ecc71)
                embed.add_field(name=f"🟢 生存者 ({len(alive_list)}名)", value="\n".join(alive_list) or "なし", inline=True)
                embed.add_field(name=f"💀 脱落者 ({len(dead_list)}名)", value="\n".join(dead_list) or "なし", inline=True)
                
                # モード表示
                mode_str = "手動GM" if room.settings["mode"] == "MANUAL" else "全自動"
                embed.set_footer(text=f"Mode: {mode_str}")
                
                await message.channel.send(embed=embed)
            
            # 2. ゲーム外の場合 -> ヘルプを表示
            else:
                embed = discord.Embed(
                    title="⚔️ オンパロス戦線 Bot",
                    description="火種を巡る人狼ゲーム。",
                    color=0x9b59b6
                )
                embed.add_field(name="⚙️ Version", value=BOT_VERSION, inline=False)
                cmd_text = (
                    "**`!panel`**\nロビーパネルを設置します。\n"
                    "**`!wclose`**\n部屋を強制削除します。"
                )
                embed.add_field(name="📜 コマンド", value=cmd_text, inline=False)
                await message.channel.send(embed=embed)

    # --- Logic ---
    async def create_room_logic(self, itx_or_ctx):
        channel = None
        user = None

        if isinstance(itx_or_ctx, discord.Interaction):
            channel = itx_or_ctx.channel
            user = itx_or_ctx.user
            if not itx_or_ctx.response.is_done(): 
                await itx_or_ctx.response.send_message("ロビー作成", ephemeral=True)
        else:
            channel = itx_or_ctx.channel
            user = itx_or_ctx.author
        if channel is None: return

        if channel.id in self.rooms:
            if not isinstance(itx_or_ctx, discord.Interaction):
                await channel.send("既に部屋があります。解散するには `!wclose` してください。")
            return

        room = GameRoom(channel)
        room.gm_user = user
        self.rooms[channel.id] = room

        async def update_panel():
            s = room.settings
            m_txt = "🤖全自動" if s["mode"]=="AUTO" else f"👤手動GM ({room.gm_user.display_name})"
            desc = f"モード: **{m_txt}**\n🐺:{s['lykos']} 🔮:{s['tribbie']} 🛡️:{s['sirens']} ⚔️:{s['swordmaster']}"
            embed = discord.Embed(title="参加者募集中", description=desc, color=0x9b59b6)
            p_names = "\n".join([p.name for p in room.players.values()])
            embed.add_field(name=f"参加者 {len(room.players)}", value=p_names or "なし")
            try: await msg.edit(embed=embed, view=view)
            except: pass

        class LobbyView(ui.View):
            def __init__(self): super().__init__(timeout=None)
            @ui.button(label="参戦/離脱", style=discord.ButtonStyle.success)
            async def join(self, itx, btn):
                if itx.user.id not in room.players: room.join(itx.user)
                else: room.leave(itx.user)
                await itx.response.send_message("更新", ephemeral=True)
                await update_panel()
            @ui.button(label="設定", style=discord.ButtonStyle.secondary)
            async def setting(self, itx, btn):
                room.gm_user = itx.user
                await itx.response.send_modal(SettingsModal(room, update_panel))
            @ui.button(label="💥 解散", style=discord.ButtonStyle.secondary)
            async def cancel(self, itx, btn):
                if itx.user.id != room.gm_user.id:
                    await itx.response.send_message("作成者のみ解散できます", ephemeral=True)
                    return
                room.phase = "CANCELLED"
                await msg.edit(content="💥 解散されました。", embed=None, view=None)
                self.stop()
            @ui.button(label="開戦", style=discord.ButtonStyle.danger)
            async def start(self, itx, btn):
                if room.settings["mode"]=="MANUAL": room.gm_user = itx.user
                if len(room.players)<2:
                    await itx.response.send_message("人数不足", ephemeral=True)
                    return
                await itx.response.send_message("開戦！")
                self.stop()
                room.phase = "STARTING"

        view = LobbyView()
        msg = await channel.send(embed=discord.Embed(title="待機中..."), view=view)
        await update_panel()

        while room.phase == "WAITING":
            await asyncio.sleep(1)
            if room.phase == "CANCELLED":
                if channel.id in self.rooms: del self.rooms[channel.id]
                return
            if room.phase == "STARTING": break
        
        await self.run_game(channel.id)

    async def run_game(self, channel_id):
        room = self.rooms[channel_id]
        room.assign_roles()

        if room.settings["mode"] == "MANUAL":
            await room.channel.send(
                f"👤 **手動GMモード**\nGM: {room.gm_user.mention}\nGMパネルで操作してください。",
                view=GMControlView(room)
            )
            spoiler = "【役職表】\n"
            for p in room.players.values(): spoiler += f"{p.name}: {p.role}\n"
            try: await room.gm_user.send(spoiler)
            except: pass
            
            for p in room.players.values():
                u = self.bot.get_user(p.id)
                if u: 
                    try: await u.send(f"役職: **{p.role}**")
                    except: pass
            
            while True:
                await asyncio.sleep(2)
                if room.phase == "CANCELLED":
                    if channel.id in self.rooms: del self.rooms[channel_id]
                    return
            return

        # === 全自動モード ===
        await room.channel.send("全自動モード開始。")
        for p in room.players.values():
            u = self.bot.get_user(p.id)
            try: await u.send(f"役職: {p.role}")
            except: pass

        day = 1
        while True:
            if room.phase == "CANCELLED": break

            room.phase="NIGHT"; room.night_actions={}
            async def n_cb(itx,p,a,t):
                if a=="divine": await itx.response.edit_message(content=f"判定: {'ライコス' if room.players[t].is_wolf_side else '人間'}", view=None)
                else: room.night_actions[a]=t; await itx.response.edit_message(content="選択済", view=None)
            ts=[]
            for p in room.get_alive():
                v=None
                if p.role==ROLE_LYKOS: v=NightActionView(room,p,"steal",n_cb)
                elif p.role==ROLE_TRIBBIE: v=NightActionView(room,p,"divine",n_cb)
                elif p.role==ROLE_SIRENS: v=NightActionView(room,p,"guard",n_cb)
                elif p.role==ROLE_SWORDMASTER: v=NightActionView(room,p,"slash",n_cb)
                if v: ts.append(self.bot.get_user(p.id).send("行動選択", view=v))
            await asyncio.gather(*ts)
            await asyncio.sleep(20)

            if room.phase == "CANCELLED": break

            room.phase="DAY"
            st,gt,sl = room.night_actions.get("steal"), room.night_actions.get("guard"), room.night_actions.get("slash")
            dead = []
            for t in set([x for x in [st,sl] if x]):
                if t!=gt: dead.append(room.players[t])
            for d in dead: d.is_alive=False
            
            msg = f"🌞 {day}日目の朝\n" + (f"{', '.join([d.name for d in dead])} 死亡" if dead else "犠牲者なし")
            await room.channel.send(msg)
            
            if room.check_winner(): await self.end_game(room, room.check_winner()); break
            
            await room.channel.send(f"議論 {room.settings['discussion_time']}秒")
            await asyncio.sleep(room.settings['discussion_time'])
            
            if room.phase == "CANCELLED": break

            room.votes={}
            # VoteViewに任せる
            ts = []
            for p in room.get_alive():
                ts.append(self.bot.get_user(p.id).send("投票してください", view=VoteView(room, p)))
            await asyncio.gather(*ts)
            
            # 最大3分待機 (全員投票でVoteViewがtallyを呼ぶが、ここでも待つ)
            elapsed = 0
            start_alive = len(room.get_alive())
            while elapsed < 180:
                await asyncio.sleep(1)
                elapsed += 1
                # 誰か死んだら次へ
                if len(room.get_alive()) < start_alive or "last_executed" in dir(room) and room.last_executed:
                   break
            
            if hasattr(room, "last_executed"): del room.last_executed

            if room.check_winner(): await self.end_game(room, room.check_winner()); break
            day+=1

        if channel.id in self.rooms:
            del self.rooms[channel.id]

    async def end_game(self, room, winner):
        embed = discord.Embed(title="決着", description=f"勝者: **{winner}**", color=0xf1c40f)
        det = ""
        for p in room.players.values(): det += f"{p.name}: {p.role} ({'生' if p.is_alive else '死'})\n"
        embed.add_field(name="内訳", value=det)
        await room.channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(WerewolfSystem(bot))