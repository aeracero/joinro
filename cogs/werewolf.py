import discord
from discord.ext import commands
from discord import ui
import asyncio
import random
import unicodedata
from objects import *

# --- Launcher ---
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

# --- GM Actions ---
class GMPlayerActionView(ui.View):
    def __init__(self, room, target_player, system):
        super().__init__(timeout=60)
        self.room = room
        self.target = target_player
        self.system = system

    @ui.button(label="📩 DM送信", style=discord.ButtonStyle.primary)
    async def send_dm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(GMDMModal(self.target))

    @ui.button(label="💀 死亡認定", style=discord.ButtonStyle.danger)
    async def kill_player(self, interaction: discord.Interaction, button: ui.Button):
        await self.system.kill_player_logic(self.room, self.target)
        await interaction.response.send_message(f"💀 **{self.target.name}** を死亡判定にしました。", ephemeral=True)

    @ui.button(label="😇 蘇生", style=discord.ButtonStyle.success)
    async def revive_player(self, interaction: discord.Interaction, button: ui.Button):
        await self.system.revive_player_logic(self.room, self.target)
        await interaction.response.send_message(f"😇 **{self.target.name}** を蘇生しました。", ephemeral=True)

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
    def __init__(self, room, system):
        super().__init__(timeout=60)
        self.room = room
        self.system = system
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
            await interaction.response.send_message(f"対象: **{target.name}**", view=GMPlayerActionView(self.room, target, self.system), ephemeral=True)
        else:
            await interaction.response.send_message("プレイヤーが見つかりません。", ephemeral=True)

class GMControlView(ui.View):
    def __init__(self, room, system):
        super().__init__(timeout=None)
        self.room = room
        self.system = system

    @ui.button(label="📋 全体状況", style=discord.ButtonStyle.secondary, row=1)
    async def check_status(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        embed = discord.Embed(title="🕵️ GMダッシュボード", color=0x2b2d31)
        alive_txt = "\n".join([f"🟢 {p.name} ({p.role})" for p in self.room.players.values() if p.is_alive])
        dead_txt = "\n".join([f"💀 {p.name} ({p.role})" for p in self.room.players.values() if not p.is_alive])
        embed.add_field(name="生存", value=alive_txt or "なし", inline=False)
        if dead_txt: embed.add_field(name="死亡", value=dead_txt, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="👤 プレイヤー操作", style=discord.ButtonStyle.secondary, row=1)
    async def manage_player(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_message("対象を選択:", view=GMPlayerSelectView(self.room, self.system), ephemeral=True)

    @ui.button(label="🌙 夜フェーズ開始", style=discord.ButtonStyle.primary, row=2)
    async def start_night(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_message("🌙 夜のアクションを開始します。", ephemeral=True)
        await self.system.start_night_logic(self.room)

    @ui.button(label="🗳️ 投票フェーズ開始", style=discord.ButtonStyle.primary, row=2)
    async def start_vote(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_message("🗳️ 投票フェーズを開始します。", ephemeral=True)
        await self.system.start_vote_logic(self.room)

    @ui.button(label="💥 強制終了", style=discord.ButtonStyle.danger, row=3)
    async def close_room(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        self.room.phase = "CANCELLED"
        await interaction.response.send_message("部屋を解散しました。", ephemeral=True)

    def check_perm(self, interaction):
        if not self.room.gm_user or interaction.user.id != self.room.gm_user.id:
            return False
        return True

# --- Settings (全役職対応版) ---
class SettingsModal(ui.Modal, title="配役設定"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        
        # 現在の設定を取得 (まだ弄ってなければ推奨設定)
        s = room.get_recommended_settings(len(room.players)) if not room.custom_settings else room.settings

        # 1. モード設定
        curr_mode = "1" if s["mode"] == "MANUAL" else "0"
        self.inp_mode = ui.TextInput(label="モード (0:自動 / 1:手動GM)", default=curr_mode, max_length=1)
        
        # 2. 人狼・狂人
        def_wolves = f"{s.get('lykos',0)}, {s.get('caeneus',0)}"
        self.inp_wolves = ui.TextInput(label="人狼陣営: ライコス, カイニス", default=def_wolves, placeholder="例: 2, 1")
        
        # 3. 村役職 (占い, 騎士, 霊媒)
        def_power = f"{s.get('tribbie',0)}, {s.get('sirens',0)}, {s.get('castorice',0)}"
        self.inp_power = ui.TextInput(label="村役職: トリビー, セイレンス, キャストリス", default=def_power, placeholder="例: 1, 1, 1")
        
        # 4. 特殊・第三 (剣士, モーディス)
        def_special = f"{s.get('swordmaster',0)}, {s.get('mordis',0)}"
        self.inp_special = ui.TextInput(label="特殊: 黒衣の剣士, モーディス", default=def_special, placeholder="例: 1, 0")
        
        # 5. 固有 (キュレネ, ファイノン)
        def_unique = f"{s.get('cyrene',0)}, {s.get('phainon',0)}"
        self.inp_unique = ui.TextInput(label="固有: キュレネ, ファイノン", default=def_unique, placeholder="例: 0, 0")

        self.add_item(self.inp_mode)
        self.add_item(self.inp_wolves)
        self.add_item(self.inp_power)
        self.add_item(self.inp_special)
        self.add_item(self.inp_unique)

    def normalize(self, text):
        return unicodedata.normalize('NFKC', text)

    def parse_list(self, text, count):
        """カンマ区切りテキストを整数のリストにする"""
        text = self.normalize(text)
        for sep in ['、', ' ', '　']:
            text = text.replace(sep, ',')
        parts = [p.strip() for p in text.split(',') if p.strip()]
        result = []
        for i in range(count):
            try:
                val = int(parts[i])
                result.append(val)
            except:
                result.append(0)
        return result

    async def on_submit(self, itx):
        try:
            # モード設定
            mode_val = self.normalize(self.inp_mode.value)
            self.room.settings["mode"] = "MANUAL" if mode_val == "1" else "AUTO"
            
            # 各役職のパース
            wolves = self.parse_list(self.inp_wolves.value, 2)
            power = self.parse_list(self.inp_power.value, 3)
            special = self.parse_list(self.inp_special.value, 2)
            unique = self.parse_list(self.inp_unique.value, 2)
            
            # 設定反映
            s = self.room.settings
            s["lykos"], s["caeneus"] = wolves[0], wolves[1]
            s["tribbie"], s["sirens"], s["castorice"] = power[0], power[1], power[2]
            s["swordmaster"], s["mordis"] = special[0], special[1]
            s["cyrene"], s["phainon"] = unique[0], unique[1]
            
            # カスタムフラグON
            self.room.custom_settings = True
            
            # 合計チェック
            total_roles = sum([
                s["lykos"], s["caeneus"], s["tribbie"], s["sirens"], s["castorice"],
                s["swordmaster"], s["mordis"], s["cyrene"], s["phainon"]
            ])
            player_count = len(self.room.players)
            citizen_count = player_count - total_roles
            
            warn = ""
            if citizen_count < 0:
                warn = f"\n⚠️ 注意: 役職数({total_roles})が参加者({player_count})を超えています！"
            
            m_str = "手動GM" if s["mode"] == "MANUAL" else "全自動"
            await itx.response.send_message(f"✅ 設定更新: {m_str} (カスタム配役)\n市民枠: {citizen_count}名{warn}", ephemeral=True)
            await self.callback()
            
        except Exception as e:
            await itx.response.send_message(f"⚠️ エラー: {e}", ephemeral=True)

# --- Vote/Action Views ---
class VoteView(ui.View):
    def __init__(self, room, player, system):
        super().__init__(timeout=None)
        self.room = room
        self.player = player
        self.system = system 
        options = []
        for p in room.get_alive():
            if p.id == player.id: continue
            options.append(discord.SelectOption(label=p.name, value=str(p.id)))
        options.append(discord.SelectOption(label="スキップ (投票放棄)", value="skip"))
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
        if hasattr(self.room, "vote_finished") and self.room.vote_finished: return
        self.room.vote_finished = True

        target_ch = self.room.main_ch if self.room.main_ch else self.room.lobby_channel
        await target_ch.send("🗳️ **投票終了**。全員の投票が完了しました。\n開票を行います...")
        await asyncio.sleep(3)

        tally = {}
        for voter_id, target in self.room.votes.items():
            voter = self.room.players.get(voter_id)
            weight = voter.vote_weight if voter else 1
            tally[target] = tally.get(target, 0) + weight

        if not tally:
            await target_ch.send("投票がありませんでした。")
            self.room.vote_finished = False 
            return

        max_votes = max(tally.values())
        candidates = [t for t, count in tally.items() if count == max_votes]

        if "skip" in candidates:
            await target_ch.send("投票の結果、**スキップ** が多数となりました。\n本日の処刑は見送られます。")
        else:
            final_target_id = random.choice(candidates)
            executed_player = self.room.players.get(final_target_id)
            
            if executed_player:
                await self.system.kill_player_logic(self.room, executed_player)
                self.room.last_executed = executed_player
                if executed_player.role == ROLE_CYRENE:
                    self.room.cyrene_executed = True
                    await target_ch.send(f"⚠️ 処刑された **{executed_player.name}** は... **{ROLE_CYRENE}** でした！！\n禁忌に触れたため、オンパロス陣営は敗北となります。")
            else:
                await target_ch.send("エラー: 対象が見つかりません。")

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

    async def setup_venue(self, room):
        guild = room.lobby_channel.guild
        cat_ov = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        if room.gm_user:
            cat_ov[room.gm_user] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            cat_name = f"⚔️ オンパロス戦線-{random.randint(100,999)}"
            room.category = await guild.create_category(cat_name, overwrites=cat_ov)
            
            main_ov = cat_ov.copy()
            for p in room.players.values():
                main_ov[p.member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            room.main_ch = await room.category.create_text_channel("🌞議論-day", overwrites=main_ov)
            
            grave_ov = cat_ov.copy()
            room.grave_ch = await room.category.create_text_channel("🪦墓場-graveyard", overwrites=grave_ov)
            
            await room.main_ch.send(f"{len(room.players)}名の英雄たちよ、ここが戦場だ。\n火種を奪われた者はここでの発言権を失い、墓場へ送られる。")
        except Exception as e:
            await room.lobby_channel.send(f"⚠️ 会場作成エラー: {e}")
            room.phase = "CANCELLED"

    async def cleanup_venue(self, room):
        try:
            if room.main_ch: await room.main_ch.delete()
        except: pass
        try:
            if room.grave_ch: await room.grave_ch.delete()
        except: pass
        try:
            if room.category: await room.category.delete()
        except: pass

    async def kill_player_logic(self, room, player):
        if not player.is_alive: return
        player.is_alive = False
        if room.main_ch and room.grave_ch:
            await room.main_ch.set_permissions(player.member, read_messages=True, send_messages=False)
            await room.grave_ch.set_permissions(player.member, read_messages=True, send_messages=True)
            await room.main_ch.send(f"💀 **{player.name}** が脱落しました。")
            await room.grave_ch.send(f"🪦 **{player.name}** が火種を失い、ここに辿り着きました。")

    async def revive_player_logic(self, room, player):
        if player.is_alive: return
        player.is_alive = True
        if room.main_ch and room.grave_ch:
            await room.main_ch.set_permissions(player.member, read_messages=True, send_messages=True)
            await room.grave_ch.set_permissions(player.member, overwrite=None)
            await room.main_ch.send(f"😇 奇跡が起き、**{player.name}** の火種が戻りました！")
            await room.grave_ch.send(f"😇 **{player.name}** が蘇生され、戦場へ戻りました。")

    async def start_night_logic(self, room):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        await target_ch.send("🌙 **夜のアクション** を開始します。")
        async def cb(itx, player, act, tid):
            target = room.players[tid] if tid else None
            t_name = target.name if target else "なし"
            if act == "divine":
                res = "ライコス" if target.is_wolf_side else "人間"
                await itx.response.edit_message(content=f"🔮 判定: {t_name}は**{res}**", view=None)
                if room.gm_user: await room.gm_user.send(f"🔮 {player.name} -> {t_name} : {res}")
            else:
                await itx.response.edit_message(content=f"✅ {t_name}を選択", view=None)
                if room.gm_user: await room.gm_user.send(f"🌙 {player.name} -> {t_name}")
        tasks = []
        for p in room.get_alive():
            view = None
            msg = ""
            if p.role == ROLE_LYKOS: view=NightActionView(room,p,"steal",cb); msg="【強奪】 誰を狙いますか？"
            elif p.role == ROLE_TRIBBIE: view=NightActionView(room,p,"divine",cb); msg="【占い】 誰を占いますか？"
            elif p.role == ROLE_SIRENS: view=NightActionView(room,p,"guard",cb); msg="【護衛】 誰を守りますか？"
            elif p.role == ROLE_SWORDMASTER: view=NightActionView(room,p,"slash",cb); msg="【辻斬り】 誰を狙いますか？"
            if view: tasks.append(self.bot.get_user(p.id).send(msg, view=view))
        if tasks: await asyncio.gather(*tasks)
        else: await target_ch.send("（能力を使用できる生存者がいません）")

    async def start_vote_logic(self, room):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        await target_ch.send("🗳️ **投票フェーズ** を開始します。(全員投票で即時開票)")
        room.votes = {}
        room.vote_finished = False
        tasks = []
        for p in room.get_alive():
            view = VoteView(room, p, self)
            tasks.append(self.bot.get_user(p.id).send("【投票】 追放する者を選んでください（1回のみ）", view=view))
        if tasks: await asyncio.gather(*tasks)
        else: await target_ch.send("（投票できる生存者がいません）")

    @commands.command()
    async def wroles(self, ctx):
        embed = discord.Embed(title="📜 オンパロス戦線 役職一覧", color=0x3498db)
        for role, data in ROLE_DATA.items():
            embed.add_field(name=role, value=data["desc"], inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def walive(self, ctx):
        found_room = None
        for room in self.rooms.values():
            if ctx.author.id in room.players:
                found_room = room
                break
        if not found_room:
            await ctx.send("現在進行中のゲームに参加していません。")
            return
        alive_list = [p.name for p in found_room.players.values() if p.is_alive]
        dead_list = [p.name for p in found_room.players.values() if not p.is_alive]
        embed = discord.Embed(title="📊 現在の状況", color=0x2ecc71)
        embed.add_field(name=f"🟢 生存 ({len(alive_list)})", value="\n".join(alive_list) or "なし", inline=True)
        embed.add_field(name=f"💀 脱落 ({len(dead_list)})", value="\n".join(dead_list) or "なし", inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    async def panel(self, ctx):
        room_list = ""
        if self.rooms:
            for ch_id, room in self.rooms.items():
                ch = self.bot.get_channel(ch_id)
                ch_name = ch.name if ch else "不明"
                mode = "手動" if room.settings["mode"] == "MANUAL" else "自動"
                room_list += f"• **{ch_name}**: {len(room.players)}人 ({mode})\n"
        else: room_list = "なし"
        embed = discord.Embed(title="⚔️ オンパロス戦線 ロビー", description=f"現在のルーム:\n{room_list}", color=0x8e44ad)
        await ctx.send(embed=embed, view=Launcher(self))
        try: await ctx.message.delete()
        except: pass

    @commands.command()
    async def wclose(self, ctx):
        if ctx.channel.id in self.rooms:
            room = self.rooms[ctx.channel.id]
            room.phase = "CANCELLED"
            await ctx.send("💥 ルームを解散します...")
            await self.cleanup_venue(room)
            if ctx.channel.id in self.rooms: del self.rooms[ctx.channel.id]
        else: await ctx.send("ここにはルームがありません。")

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
        alive_txt = "\n".join([f"🟢 {p.name} ({p.role})" for p in room.players.values() if p.is_alive])
        dead_txt = "\n".join([f"💀 {p.name} ({p.role})" for p in room.players.values() if not p.is_alive])
        embed.add_field(name="生存", value=alive_txt or "なし")
        if dead_txt: embed.add_field(name="死亡", value=dead_txt)
        await ctx.author.send(embed=embed)

    @commands.command()
    async def wvote(self, ctx):
        room = await self.check_gm(ctx)
        if not room: return
        await ctx.message.delete()
        await self.start_vote_logic(room)

    @commands.command()
    async def wnight(self, ctx):
        room = await self.check_gm(ctx)
        if not room: return
        await ctx.message.delete()
        await self.start_night_logic(room)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        if self.bot.user in message.mentions:
            if message.channel.id in self.rooms:
                room = self.rooms[message.channel.id]
                alive_list = [p.name for p in room.players.values() if p.is_alive]
                dead_list = [p.name for p in room.players.values() if not p.is_alive]
                embed = discord.Embed(title="📊 現在の戦況", color=0x2ecc71)
                embed.add_field(name=f"🟢 生存 ({len(alive_list)})", value="\n".join(alive_list) or "なし", inline=True)
                embed.add_field(name=f"💀 脱落 ({len(dead_list)})", value="\n".join(dead_list) or "なし", inline=True)
                await message.channel.send(embed=embed)
            else:
                embed = discord.Embed(title="⚔️ オンパロス戦線 Bot", description="Bot Version 0.3 (Beta)", color=0x9b59b6)
                embed.add_field(name="✨ v0.3 更新内容", value="• 📩 DMコマンド `!wroles`, `!walive` 追加\n• ⚖️ 配役自動バランス調整\n• 😇 GM蘇生機能・進行ボタン追加", inline=False)
                await message.channel.send(embed=embed)

    async def create_room_logic(self, itx_or_ctx):
        channel = None
        user = None
        if isinstance(itx_or_ctx, discord.Interaction):
            channel = itx_or_ctx.channel
            user = itx_or_ctx.user
            if not itx_or_ctx.response.is_done(): await itx_or_ctx.response.send_message("ロビー作成", ephemeral=True)
        else:
            channel = itx_or_ctx.channel
            user = itx_or_ctx.author
        if channel is None: return

        if channel.id in self.rooms:
            if not isinstance(itx_or_ctx, discord.Interaction): await channel.send("既に部屋があります。")
            return

        room = GameRoom(channel)
        room.gm_user = user
        self.rooms[channel.id] = room

        async def update_panel():
            s = room.settings
            if not room.custom_settings:
                rec = room.get_recommended_settings(len(room.players))
                s_display = rec
                note = "(人数に合わせて自動調整)"
            else:
                s_display = s
                note = "(カスタム設定)"

            m_txt = "🤖全自動" if s["mode"]=="AUTO" else f"👤手動GM"
            
            # 全役職を表示
            role_summary = (
                f"🐺:{s_display['lykos']} 狂:{s_display['caeneus']} 🔮:{s_display['tribbie']} 👻:{s_display['castorice']}\n"
                f"🛡️:{s_display['sirens']} ⚔️:{s_display['swordmaster']} 💀:{s_display['mordis']}\n"
                f"💣:{s_display['cyrene']} 👮:{s_display['phainon']}"
            )
            desc = f"モード: **{m_txt}** {note}\n{role_summary}"
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
                    await itx.response.send_message("作成者のみ解散可", ephemeral=True)
                    return
                room.phase = "CANCELLED"
                await msg.edit(content="💥 解散。", embed=None, view=None)
                self.stop()
            @ui.button(label="開戦", style=discord.ButtonStyle.danger)
            async def start(self, itx, btn):
                if room.settings["mode"]=="MANUAL": room.gm_user = itx.user
                if len(room.players)<2:
                    await itx.response.send_message("人数不足", ephemeral=True)
                    return
                await itx.response.send_message("会場設営中...")
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
        
        await self.setup_venue(room)
        if room.phase == "CANCELLED":
             await self.cleanup_venue(room)
             if channel.id in self.rooms: del self.rooms[channel.id]
             return

        try:
            await self.run_game(channel.id)
        except Exception as e:
            await channel.send(f"⚠️ ゲーム実行エラー: {e}")
        finally:
            if channel.id in self.rooms:
                r = self.rooms[channel.id]
                await self.cleanup_venue(r)
                del self.rooms[channel.id]

    async def run_game(self, channel_id):
        room = self.rooms[channel_id]
        room.assign_roles()
        target_ch = room.main_ch if room.main_ch else room.lobby_channel

        spoiler_txt = "【役職一覧】\n"
        for p in room.players.values():
            spoiler_txt += f"{p.name}: {p.role}\n"
            u = self.bot.get_user(p.id)
            if u:
                data = ROLE_DATA.get(p.role, {"desc": "詳細不明", "has_ability": False})
                embed = discord.Embed(title=f"あなたの役職: {p.role}", color=0x2ecc71)
                embed.description = data["desc"]
                if data["has_ability"]:
                    embed.add_field(name="能力", value="✅ **使用可能** (GMの合図で使用)", inline=False)
                else:
                    embed.add_field(name="能力", value="❌ **能動的な能力なし**", inline=False)
                if p.role == ROLE_LYKOS:
                    mates = [x.name for x in room.players.values() if x.role == ROLE_LYKOS and x.id != p.id]
                    embed.add_field(name="仲間のライコス", value=", ".join(mates) if mates else "なし", inline=False)
                try: await u.send(embed=embed)
                except: pass

        if room.settings["mode"] == "MANUAL":
            await target_ch.send(
                f"👤 **手動GMモード**\nGM: {room.gm_user.mention}\n下のパネルで操作してください。",
                view=GMControlView(room, self)
            )
            try: await room.gm_user.send(spoiler_txt)
            except: pass
            
            while True:
                await asyncio.sleep(2)
                if room.phase == "CANCELLED": return
            return

        # === Auto Mode ===
        await target_ch.send("全自動モード開始。")
        day = 1
        while True:
            if room.phase == "CANCELLED": break
            await self.start_night_logic(room)
            await asyncio.sleep(20)

            room.phase="DAY"
            st,gt,sl = room.night_actions.get("steal"), room.night_actions.get("guard"), room.night_actions.get("slash")
            dead = []
            for t in set([x for x in [st,sl] if x]):
                if t!=gt: dead.append(room.players[t])
            
            for d in dead: await self.kill_player_logic(room, d)
            
            msg = f"🌞 {day}日目の朝\n" + (f"{', '.join([d.name for d in dead])} 脱落" if dead else "犠牲者なし")
            await target_ch.send(msg)

            if room.check_winner(): await self.end_game(room, room.check_winner()); break
            
            await target_ch.send(f"議論 {room.settings['discussion_time']}秒")
            await asyncio.sleep(room.settings['discussion_time'])

            await self.start_vote_logic(room)
            
            elapsed=0
            while elapsed < 180:
                await asyncio.sleep(1)
                elapsed+=1
                if hasattr(room, "last_executed") and room.last_executed: break
                if hasattr(room, "vote_finished") and room.vote_finished: break
            
            if hasattr(room, "last_executed"): del room.last_executed
            if hasattr(room, "vote_finished"): room.vote_finished = False

            if room.check_winner(): await self.end_game(room, room.check_winner()); break
            day+=1

    async def end_game(self, room, winner):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        embed = discord.Embed(title="決着", description=f"勝者: **{winner}**", color=0xf1c40f)
        det = ""
        for p in room.players.values(): det += f"{p.name}: {p.role} ({'生' if p.is_alive else '死'})\n"
        embed.add_field(name="内訳", value=det)
        await target_ch.send(embed=embed)
        await target_ch.send("会場は60秒後に閉鎖されます...")
        await asyncio.sleep(60)

async def setup(bot):
    await bot.add_cog(WerewolfSystem(bot))