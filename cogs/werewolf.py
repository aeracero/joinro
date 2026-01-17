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
        if self.target.role == ROLE_MORDIS: status.append(f"復活:{'有' if self.target.mordis_revive_available else '無'}")
        if self.target.role == ROLE_CERYDRA: status.append("x2票")
        if self.target.role == ROLE_CYRENE: status.append(f"自衛:{self.target.cyrene_guard_count} バフ:{self.target.cyrene_buff_count}")
        if self.target.role == ROLE_HYANCI: status.append(f"イカルン:{self.target.hyanci_ikarun_count}")
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
        await interaction.response.send_message("🌙 夜のアクションを開始します。全員の行動完了を待機中...", ephemeral=True)
        asyncio.create_task(self.system.start_night_logic(self.room))

    @ui.button(label="🗳️ 投票フェーズ開始", style=discord.ButtonStyle.primary, row=2)
    async def start_vote(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_message("🗳️ 投票フェーズを開始します。", ephemeral=True)
        asyncio.create_task(self.system.start_vote_logic(self.room))

    @ui.button(label="💥 強制終了", style=discord.ButtonStyle.danger, row=3)
    async def close_room(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        self.room.phase = "CANCELLED"
        await interaction.response.send_message("部屋を解散しました。", ephemeral=True)

    def check_perm(self, interaction):
        if not self.room.gm_user or interaction.user.id != self.room.gm_user.id:
            return False
        return True

# --- Settings ---
class SettingsModal(ui.Modal, title="配役・システム設定"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        s = room.get_recommended_settings(len(room.players)) if not room.custom_settings else room.settings
        
        mode_v = "1" if s["mode"] == "MANUAL" else "0"
        close_v = "1" if s["auto_close"] else "0"
        rematch_v = "1" if s["rematch"] else "0"
        self.inp_sys = ui.TextInput(label="システム: モード,閉鎖,続戦(0/1)", default=f"{mode_v}, {close_v}, {rematch_v}", placeholder="例: 0, 1, 0")
        
        def_wolves = f"{s.get('lykos',0)}, {s.get('caeneus',0)}"
        self.inp_wolves = ui.TextInput(label="人狼: ライコス, カイニス", default=def_wolves, placeholder="1, 0")
        def_info = f"{s.get('tribbie',0)}, {s.get('sirens',0)}, {s.get('castorice',0)}, {s.get('aglaea',0)}"
        self.inp_info = ui.TextInput(label="村: 占, 騎, 霊, アグライア", default=def_info, placeholder="1, 1, 1, 0")
        def_atk = f"{s.get('swordmaster',0)}, {s.get('phainon',0)}, {s.get('saphel',0)}"
        self.inp_atk = ui.TextInput(label="攻撃: 剣士, 暗殺, サフェル", default=def_atk, placeholder="0, 0, 0")
        def_sp = f"{s.get('mordis',0)}, {s.get('cyrene',0)}, {s.get('cerydra',0)}, {s.get('hyanci',0)}"
        self.inp_sp = ui.TextInput(label="特殊: モーディス,キュレネ,ケリュドラ,ヒアンシー", default=def_sp, placeholder="0, 0, 0, 0")

        self.add_item(self.inp_sys)
        self.add_item(self.inp_wolves)
        self.add_item(self.inp_info)
        self.add_item(self.inp_atk)
        self.add_item(self.inp_sp)

    def normalize(self, text):
        return unicodedata.normalize('NFKC', text)

    def parse_list(self, text, count):
        text = self.normalize(text)
        for sep in ['、', ' ', '　']: text = text.replace(sep, ',')
        parts = [p.strip() for p in text.split(',') if p.strip()]
        result = []
        for i in range(count):
            try: result.append(int(parts[i]))
            except: result.append(0)
        return result

    async def on_submit(self, itx):
        try:
            sys_vals = self.parse_list(self.inp_sys.value, 3)
            self.room.settings["mode"] = "MANUAL" if sys_vals[0] == 1 else "AUTO"
            self.room.settings["auto_close"] = True if sys_vals[1] == 1 else False
            self.room.settings["rematch"] = True if sys_vals[2] == 1 else False

            wolves = self.parse_list(self.inp_wolves.value, 2)
            info = self.parse_list(self.inp_info.value, 4)
            atk = self.parse_list(self.inp_atk.value, 3)
            sp = self.parse_list(self.inp_sp.value, 4)
            
            s = self.room.settings
            s["lykos"], s["caeneus"] = wolves[0], wolves[1]
            s["tribbie"], s["sirens"], s["castorice"], s["aglaea"] = info[0], info[1], info[2], info[3]
            s["swordmaster"], s["phainon"], s["saphel"] = atk[0], atk[1], atk[2]
            s["mordis"], s["cyrene"], s["cerydra"], s["hyanci"] = sp[0], sp[1], sp[2], sp[3]
            
            self.room.custom_settings = True
            
            m_str = "手動" if s["mode"] == "MANUAL" else "自動"
            c_str = "閉鎖ON" if s["auto_close"] else "閉鎖OFF"
            r_str = "続戦ON" if s["rematch"] else "続戦OFF"
            
            await itx.response.send_message(f"✅ 設定更新: {m_str}, {c_str}, {r_str} (カスタム配役)", ephemeral=True)
            await self.callback()
        except: await itx.response.send_message("エラー: 入力形式を確認してください", ephemeral=True)

# --- Views ---
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

class NightActionView(ui.View):
    def __init__(self, room, player, action_type, callback):
        super().__init__(timeout=120)
        self.room = room
        self.player = player
        self.action_type = action_type
        self.callback = callback
        
        options = []
        for p in room.get_alive():
            if player.role == ROLE_SIRENS:
                if p.id == player.last_guarded_id: continue
            elif p.id == player.id: 
                continue 
            options.append(discord.SelectOption(label=p.name, value=str(p.id)))
        
        if not options: options.append(discord.SelectOption(label="なし", value="none"))
        select = ui.Select(placeholder="対象を選択", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, itx):
        tid = int(itx.data['values'][0]) if itx.data['values'][0] != "none" else None
        await self.callback(itx, self.player, self.action_type, tid)

class CyreneSelfGuardView(ui.View):
    def __init__(self, room, player, callback):
        super().__init__(timeout=120)
        self.room = room
        self.player = player
        self.callback = callback
    
    @ui.button(label="🛡️ 自分を守る (消費:1)", style=discord.ButtonStyle.success)
    async def guard_self(self, itx, btn):
        await self.callback(itx, self.player, "cyrene_guard", "self_guard")
    
    @ui.button(label="何もしない", style=discord.ButtonStyle.secondary)
    async def skip(self, itx, btn):
        await self.callback(itx, self.player, "cyrene_guard", None)

class HyanciActionView(ui.View):
    def __init__(self, room, player, callback):
        super().__init__(timeout=120)
        self.room = room
        self.player = player
        self.callback = callback
    
    @ui.button(label="🦇 イカルンを捧げる (消費:1)", style=discord.ButtonStyle.danger)
    async def use_ikarun(self, itx, btn):
        await self.callback(itx, self.player, "hyanci_ikarun", "use")
    
    @ui.button(label="何もしない", style=discord.ButtonStyle.secondary)
    async def skip(self, itx, btn):
        await self.callback(itx, self.player, "hyanci_ikarun", None)

class SaphelActionView(ui.View):
    def __init__(self, room, player, callback):
        super().__init__(timeout=120)
        self.room = room
        self.player = player
        self.callback = callback
        
        opts1 = []
        for p in room.get_alive():
            if p.id != player.id:
                opts1.append(discord.SelectOption(label=p.name, value=str(p.id)))
        if not opts1: opts1.append(discord.SelectOption(label="なし", value="none"))
        
        self.sel_src = ui.Select(placeholder="🎭 誰の能力を模倣しますか？", options=opts1, row=0)
        self.add_item(self.sel_src)

        opts2 = []
        for p in room.get_alive():
            if p.id != player.id:
                opts2.append(discord.SelectOption(label=p.name, value=str(p.id)))
        if not opts2: opts2.append(discord.SelectOption(label="なし", value="none"))
        
        self.sel_dst = ui.Select(placeholder="👉 誰に能力を行使しますか？", options=opts2, row=1)
        self.add_item(self.sel_dst)

        self.btn = ui.Button(label="決定", style=discord.ButtonStyle.primary, row=2)
        self.btn.callback = self.on_submit
        self.add_item(self.btn)

    async def on_submit(self, itx):
        if not self.sel_src.values or not self.sel_dst.values:
            await itx.response.send_message("⚠️ 両方の対象を選んでください。", ephemeral=True)
            return
        
        src_val = self.sel_src.values[0]
        dst_val = self.sel_dst.values[0]
        src_id = int(src_val) if src_val != "none" else None
        dst_id = int(dst_val) if dst_val != "none" else None
        
        await self.callback(itx, self.player, "mimic", {"source": src_id, "target": dst_id})


# --- Bot System ---
class WerewolfSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rooms = {}

    def get_room_from_context(self, ctx_or_channel_id):
        cid = ctx_or_channel_id.channel.id if hasattr(ctx_or_channel_id, 'channel') else ctx_or_channel_id
        if cid in self.rooms: return self.rooms[cid]
        for room in self.rooms.values():
            if room.main_ch and room.main_ch.id == cid: return room
            if room.grave_ch and room.grave_ch.id == cid: return room
        return None

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
        if not player.is_alive: return False
        
        if player.role == ROLE_HYANCI and player.hyanci_protection_active:
            if random.random() < 0.5:
                try:
                    u = self.bot.get_user(player.id)
                    await u.send("🦇 **イカルン** の加護により死を免れました！")
                except: pass
                return False 

        player.is_alive = False
        
        if room.main_ch and room.grave_ch:
            await room.main_ch.set_permissions(player.member, read_messages=True, send_messages=False)
            await room.grave_ch.set_permissions(player.member, read_messages=True, send_messages=True)
            await room.main_ch.send(f"💀 **{player.name}** が脱落しました。")
            await room.grave_ch.send(f"🪦 **{player.name}** が火種を失い、ここに辿り着きました。")

        if player.role == ROLE_CYRENE:
            if room.main_ch:
                await room.main_ch.send(f"⚠️ **{player.name}** は **{ROLE_CYRENE}** でした！\n禁忌が破られ、オンパロス陣営の火種が全て消滅します...")
            targets = [p for p in room.get_alive() if p.team == TEAM_AMPHOREUS]
            for t in targets:
                t.is_alive = False
                if room.main_ch and room.grave_ch:
                    await room.main_ch.set_permissions(t.member, read_messages=True, send_messages=False)
                    await room.grave_ch.set_permissions(t.member, read_messages=True, send_messages=True)
                    await room.grave_ch.send(f"🪦 **{t.name}** がキュレネの死に伴い消滅しました。")
        
        return True

    async def revive_player_logic(self, room, player):
        if player.is_alive: return
        player.is_alive = True
        
        if player.role == ROLE_MORDIS: player.mordis_revive_available = True
        if player.role == ROLE_CYRENE: 
            player.cyrene_guard_count = 1
            player.cyrene_buff_count = 1 # リセット値1
        if player.role == ROLE_HYANCI:
            player.hyanci_ikarun_count = 2
            player.hyanci_protection_active = False
        if player.role == ROLE_SIRENS:
            player.last_guarded_id = None

        if room.main_ch and room.grave_ch:
            await room.main_ch.set_permissions(player.member, read_messages=True, send_messages=True)
            await room.grave_ch.set_permissions(player.member, overwrite=None)
            await room.main_ch.send(f"😇 奇跡が起き、**{player.name}** の火種が戻りました！（能力も全快）")
            await room.grave_ch.send(f"😇 **{player.name}** が蘇生され、戦場へ戻りました。")

    async def start_night_logic(self, room):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        await target_ch.send("🌙 **夜のアクション** を開始します。")
        
        # リセット処理
        for p in room.players.values():
            p.hyanci_protection_active = False
            # サフェルの投票権などをリセット (もしケリュドラ模倣していた場合)
            if p.role == ROLE_SAPHEL: p.vote_weight = 1

        active_roles = [ROLE_LYKOS, ROLE_TRIBBIE, ROLE_SIRENS, ROLE_SWORDMASTER, ROLE_PHAINON, ROLE_CYRENE, ROLE_AGLAEA, ROLE_SAPHEL, ROLE_HYANCI]
        pending_actors = set([p.id for p in room.get_alive() if p.role in active_roles])
        room.night_actions = {} 

        async def cb(itx, player, act, val):
            # val: int(id), str(special), dict(mimic)
            room.night_actions[act] = val
            
            target_name = "なし"
            if val == "self_guard": target_name = "自分"
            elif val == "use": target_name = "イカルン"
            elif isinstance(val, int):
                t = room.players.get(val)
                if t: target_name = t.name
            elif isinstance(val, dict) and act == "mimic":
                src = room.players.get(val['source'])
                dst = room.players.get(val['target'])
                src_name = src.name if src else "なし"
                dst_name = dst.name if dst else "なし"
                target_name = f"{src_name} → {dst_name}"

            # Responses
            if act == "cyrene_buff":
                player.cyrene_buff_count -= 1
                await itx.response.edit_message(content=f"💪 {target_name} に力を与えました。", view=None)
                target = room.players.get(val)
                action_map = {
                    ROLE_LYKOS: ("steal_2nd", "【バフ効果】 2人目の強奪対象を選んでください"),
                    ROLE_TRIBBIE: ("divine_2nd", "【バフ効果】 2人目の占い対象を選んでください"),
                    ROLE_SIRENS: ("guard_2nd", "【バフ効果】 2人目の護衛対象を選んでください"),
                    ROLE_SWORDMASTER: ("slash_2nd", "【バフ効果】 2人目の辻斬り対象を選んでください"),
                    ROLE_PHAINON: ("assassinate_2nd", "【バフ効果】 2人目の暗殺対象を選んでください")
                }
                if target and target.role in action_map:
                    act_key, msg = action_map[target.role]
                    pending_actors.add(target.id) 
                    try:
                        u = self.bot.get_user(target.id)
                        await u.send(msg, view=NightActionView(room, target, act_key, cb))
                    except: pass

            elif act == "hyanci_ikarun":
                if val == "use":
                    player.hyanci_ikarun_count -= 1
                    player.hyanci_protection_active = True
                    await itx.response.edit_message(content=f"🦇 イカルンを捧げました。(残{player.hyanci_ikarun_count})", view=None)
                else:
                    await itx.response.edit_message(content="🦇 何もしませんでした。", view=None)

            elif act in ["divine", "divine_2nd"]:
                target = room.players.get(val)
                res = "ライコス" if target and target.is_wolf_side else "人間"
                await itx.response.edit_message(content=f"🔮 判定: {target_name}は**{res}**", view=None)
                if room.gm_user: await room.gm_user.send(f"🔮 {player.name} -> {target_name} : {res}")
            
            elif act == "investigate":
                target = room.players.get(val)
                last_vote = room.prev_votes.get(target.id) if target else None
                vt_name = "なし"
                if last_vote == "skip": vt_name = "スキップ"
                elif last_vote:
                    vt = room.players.get(last_vote)
                    if vt: vt_name = vt.name
                if not room.prev_votes: vt_name = "（投票履歴なし）"
                await itx.response.edit_message(content=f"🧐 調査結果: {target_name} の投票先は **{vt_name}** です。", view=None)

            elif act == "mimic":
                await itx.response.edit_message(content=f"🎭 {target_name} の能力を模倣します。", view=None)

            elif act == "cyrene_guard":
                if val == "self_guard":
                    player.cyrene_guard_count -= 1
                    await itx.response.edit_message(content=f"🛡️ 自分を護衛しました。(残{player.cyrene_guard_count}回)", view=None)
                else:
                    await itx.response.edit_message(content="🛡️ 自衛をスキップしました。", view=None)
            
            else:
                act_str = {"steal":"強奪", "guard":"護衛", "slash":"辻斬り", "assassinate":"暗殺"}.get(act.split('_')[0], act)
                await itx.response.edit_message(content=f"✅ {target_name}を選択 ({act_str})", view=None)
                if room.gm_user: await room.gm_user.send(f"🌙 {player.name} ({player.role}) -> {target_name}")

            if "_2nd" in act or player.role != ROLE_CYRENE:
                pending_actors.discard(player.id)
            else:
                pending_actors.discard(player.id)

        tasks = []
        for p in room.get_alive():
            view, msg = None, ""
            
            if p.role == ROLE_LYKOS: view=NightActionView(room,p,"steal",cb); msg="【強奪】 誰を狙いますか？"
            elif p.role == ROLE_TRIBBIE: view=NightActionView(room,p,"divine",cb); msg="【占い】 誰を占いますか？"
            elif p.role == ROLE_SIRENS: view=NightActionView(room,p,"guard",cb); msg="【護衛】 誰を守りますか？"
            elif p.role == ROLE_SWORDMASTER: view=NightActionView(room,p,"slash",cb); msg="【辻斬り】 誰を狙いますか？"
            elif p.role == ROLE_PHAINON: view=NightActionView(room,p,"assassinate",cb); msg="【暗殺】 誰を狙いますか？"
            elif p.role == ROLE_AGLAEA: view=NightActionView(room,p,"investigate",cb); msg="【調査】 誰の投票先を調べますか？"
            elif p.role == ROLE_SAPHEL: view=SaphelActionView(room,p,cb); msg="【模倣】 模倣先と行使先を選んでください。"
            
            if view: tasks.append(self.bot.get_user(p.id).send(msg, view=view))

            if p.role == ROLE_CYRENE:
                if p.cyrene_guard_count > 0:
                    v1 = CyreneSelfGuardView(room, p, cb)
                    tasks.append(self.bot.get_user(p.id).send("【自衛】", view=v1))
                if p.cyrene_buff_count > 0:
                    v2 = NightActionView(room, p, "cyrene_buff", cb)
                    tasks.append(self.bot.get_user(p.id).send("【強化】", view=v2))
            
            if p.role == ROLE_HYANCI:
                if p.hyanci_ikarun_count > 0:
                    v3 = HyanciActionView(room, p, cb)
                    tasks.append(self.bot.get_user(p.id).send("【生存】 イカルンを使用しますか？", view=v3))
                else:
                    embed = discord.Embed(title="🌙 アクションなし", description="イカルンが尽きているため、アクションはありません。", color=0x2c3e50)
                    tasks.append(self.bot.get_user(p.id).send(embed=embed))
                    pending_actors.discard(p.id)

            if not view and p.role not in [ROLE_CYRENE, ROLE_HYANCI]:
                try:
                    u = self.bot.get_user(p.id)
                    embed = discord.Embed(title="🌙 静寂の夜", description="今夜、あなたが行えるアクションはありません。", color=0x2c3e50)
                    tasks.append(u.send(embed=embed))
                except: pass

        if tasks: await asyncio.gather(*tasks)
        else: await target_ch.send("（能力を使用できる生存者がいません）")

        wait_time = 0
        while len(pending_actors) > 0:
            await asyncio.sleep(1)
            wait_time += 1
            if wait_time > 300:
                await target_ch.send("⏰ 時間切れにより夜を終了します。")
                break
            if room.phase == "CANCELLED": return

        await self.resolve_morning(room)

    async def resolve_morning(self, room):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        
        # 霊媒処理(Castorice)
        if room.last_executed:
            mediums = [p for p in room.get_alive() if p.role == ROLE_CASTORICE]
            species = "ライコス (人狼)" if room.last_executed.is_wolf_side else "人間"
            for medium in mediums:
                try:
                    u = self.bot.get_user(medium.id)
                    if u: await u.send(f"👻 霊媒結果: 昨日処刑された **{room.last_executed.name}** は **{species}** でした。")
                except: pass
            
            # ★追加: サフェルがキャストリスを模倣していた場合
            mimic_data = room.night_actions.get("mimic")
            saphel_actor = next((p for p in room.get_alive() if p.role == ROLE_SAPHEL), None)
            if saphel_actor and mimic_data:
                src = room.players.get(mimic_data['source'])
                if src and src.role == ROLE_CASTORICE:
                    try:
                        u = self.bot.get_user(saphel_actor.id)
                        await u.send(f"🎭 模倣霊媒結果: 昨日処刑された **{room.last_executed.name}** は **{species}** でした。")
                    except: pass

            room.last_executed = None

        # --- サフェル解決 ---
        mimic_data = room.night_actions.get("mimic")
        saphel_actor = next((p for p in room.get_alive() if p.role == ROLE_SAPHEL), None)
        saphel_attack = None
        saphel_guard = None
        dead_candidates = []

        if saphel_actor and mimic_data:
            src = room.players.get(mimic_data['source'])
            dst = room.players.get(mimic_data['target'])
            
            if src:
                if src.role == ROLE_LYKOS:
                    dead_candidates.append(saphel_actor)
                    if room.gm_user: await room.gm_user.send(f"🎭 サフェル自滅 (狼模倣)")
                elif src.role == ROLE_SIRENS: 
                    if dst: saphel_guard = dst.id
                elif src.role in [ROLE_SWORDMASTER, ROLE_PHAINON]: 
                    if dst: saphel_attack = dst.id
                elif src.role == ROLE_TRIBBIE:
                    if dst:
                        res = "ライコス" if dst.is_wolf_side else "人間"
                        try:
                            u = self.bot.get_user(saphel_actor.id)
                            await u.send(f"🎭 模倣占い結果: {dst.name} は **{res}** です。")
                        except: pass
                elif src.role == ROLE_AGLAEA:
                    if dst:
                        last_vote = room.prev_votes.get(dst.id)
                        vote_name = "なし"
                        if last_vote == "skip": vote_name = "スキップ"
                        elif last_vote:
                            v_target = room.players.get(last_vote)
                            if v_target: vote_name = v_target.name
                        try:
                            u = self.bot.get_user(saphel_actor.id)
                            await u.send(f"🎭 模倣調査結果: {dst.name} の投票先は **{vote_name}** です。")
                        except: pass
                elif src.role == ROLE_MORDIS:
                    saphel_actor.mordis_revive_available = True
                    if room.gm_user: await room.gm_user.send("🎭 サフェル -> モーディス模倣 (耐久回復)")
                elif src.role == ROLE_CERYDRA:
                    saphel_actor.vote_weight = 2
                    if room.gm_user: await room.gm_user.send("🎭 サフェル -> ケリュドラ模倣 (明日2票)")
                elif src.role == ROLE_CYRENE:
                    if room.gm_user: await room.gm_user.send("🎭 サフェル -> キュレネ模倣 (何も起きません)")
                elif src.role == ROLE_HYANCI:
                    saphel_actor.hyanci_protection_active = True
                    if room.gm_user: await room.gm_user.send("🎭 サフェル -> ヒアンシー模倣 (保護)")

        steal = [room.night_actions.get("steal"), room.night_actions.get("steal_2nd")]
        guard = [room.night_actions.get("guard"), room.night_actions.get("guard_2nd")]
        slash = [room.night_actions.get("slash"), room.night_actions.get("slash_2nd")]
        assas = [room.night_actions.get("assassinate"), room.night_actions.get("assassinate_2nd")]
        cy_g = room.night_actions.get("cyrene_guard")

        if saphel_guard: guard.append(saphel_guard)
        if saphel_attack: slash.append(saphel_attack)

        steal = [x for x in steal if x]
        guard = [x for x in guard if x]
        slash = [x for x in slash if x]
        assas = [x for x in assas if x]

        if room.night_actions.get("guard"):
            siren = next((p for p in room.get_alive() if p.role == ROLE_SIRENS), None)
            if siren: siren.last_guarded_id = room.night_actions.get("guard")

        all_attacks = set(steal + slash) 
        for tid in all_attacks:
            if tid in guard: continue 
            victim = room.players.get(tid)
            if victim:
                if victim.role == ROLE_CYRENE and cy_g == "self_guard": continue
                if victim.role == ROLE_MORDIS and victim.mordis_revive_available:
                    victim.mordis_revive_available = False
                else:
                    dead_candidates.append(victim)
        
        phainon_player = next((p for p in room.get_alive() if p.role == ROLE_PHAINON), None)
        if phainon_player:
            for ph_tid in assas:
                target_p = room.players.get(ph_tid)
                if target_p:
                    if target_p.is_wolf_side or target_p.team == TEAM_SWORDMASTER:
                        if target_p not in dead_candidates: dead_candidates.append(target_p)
                    else:
                        if target_p not in dead_candidates: dead_candidates.append(target_p)
                        if phainon_player not in dead_candidates: dead_candidates.append(phainon_player)

        actually_dead = []
        for d in list(set(dead_candidates)):
            is_dead = await self.kill_player_logic(room, d)
            if is_dead: actually_dead.append(d)
        
        msg = f"🌞 **朝が来ました**\n" + (f"{', '.join([d.name for d in actually_dead])} が無惨な姿で発見されました。" if actually_dead else "昨晩は犠牲者がいませんでした。")
        await target_ch.send(msg)

        if room.check_winner():
            await self.end_game(room, room.check_winner())
        else:
            await target_ch.send(f"議論を開始してください ({room.settings['discussion_time']}秒)")

    async def start_vote_logic(self, room):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        await target_ch.send("🗳️ **投票フェーズ** を開始します。(全員投票で即時開票)")
        room.votes = {}
        tasks = []
        for p in room.get_alive():
            view = VoteView(room, p, self)
            tasks.append(self.bot.get_user(p.id).send("【投票】 追放する者を選んでください（1回のみ）", view=view))
        if tasks: await asyncio.gather(*tasks)
        else: await target_ch.send("（投票できる生存者がいません）")

        wait_time = 0
        while True:
            await asyncio.sleep(1)
            wait_time += 1
            if wait_time > 180:
                await target_ch.send("⏰ 時間切れ。強制開票します。")
                break
            if room.phase == "CANCELLED": return
            if len(room.votes) >= len(room.get_alive()): break

        await self.tally_votes_logic(room)

    async def tally_votes_logic(self, room):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        await target_ch.send("🗳️ **投票終了**。開票を行います...")
        await asyncio.sleep(3)

        room.prev_votes = room.votes.copy()

        tally = {}
        for voter_id, target in room.votes.items():
            voter = room.players.get(voter_id)
            weight = voter.vote_weight if voter else 1
            tally[target] = tally.get(target, 0) + weight

        if not tally:
            await target_ch.send("投票がありませんでした。")
            return

        max_votes = max(tally.values())
        candidates = [t for t, count in tally.items() if count == max_votes]

        if "skip" in candidates or len(candidates) > 1:
            reason = "スキップ多数" if "skip" in candidates else "同数票"
            await target_ch.send(f"投票の結果、**{reason}** となりました。\n本日の処刑は見送られます。")
        else:
            final_target_id = candidates[0]
            executed_player = room.players.get(final_target_id)
            if executed_player:
                is_dead = await self.kill_player_logic(room, executed_player)
                if is_dead:
                    room.last_executed = executed_player
                    if executed_player.role == ROLE_CYRENE:
                        room.cyrene_executed = True
                        await target_ch.send(f"⚠️ 処刑された **{executed_player.name}** は... **{ROLE_CYRENE}** でした！！\n禁忌に触れたため、オンパロス陣営は敗北となります。")
                else:
                    await target_ch.send(f"⚠️ **{executed_player.name}** は処刑台に上がりましたが、奇跡的に生還しました！")
            else:
                await target_ch.send("エラー: 対象が見つかりません。")
        
        if room.check_winner():
            await self.end_game(room, room.check_winner())

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
        room = self.get_room_from_context(ctx)
        if room:
            room.phase = "CANCELLED"
            await ctx.send("💥 ルームを解散します...")
            await self.cleanup_venue(room)
            if room.lobby_channel.id in self.rooms: del self.rooms[room.lobby_channel.id]
        else:
            await ctx.send("ここにはルームがありません。")

    async def check_gm(self, ctx):
        room = self.get_room_from_context(ctx)
        if not room: return None
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
        asyncio.create_task(self.start_vote_logic(room))

    @commands.command()
    async def wnight(self, ctx):
        room = await self.check_gm(ctx)
        if not room: return
        await ctx.message.delete()
        asyncio.create_task(self.start_night_logic(room))

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        if self.bot.user in message.mentions:
            room = self.get_room_from_context(message)
            if room:
                alive_list = [p.name for p in room.players.values() if p.is_alive]
                dead_list = [p.name for p in room.players.values() if not p.is_alive]
                embed = discord.Embed(title="📊 現在の戦況", color=0x2ecc71)
                embed.add_field(name=f"🟢 生存 ({len(alive_list)})", value="\n".join(alive_list) or "なし", inline=True)
                embed.add_field(name=f"💀 脱落 ({len(dead_list)})", value="\n".join(dead_list) or "なし", inline=True)
                await message.channel.send(embed=embed)
            else:
                embed = discord.Embed(title="⚔️ オンパロス戦線 Bot", description="Bot Version 0.5.7 (Beta)", color=0x9b59b6)
                embed.add_field(name="✨ v0.5.7 更新内容", value="• 🎭 サフェルの模倣機能強化 (モーディス、ケリュドラ、キャストリス対応)\n• 🐉 キュレネのバフ回数調整(1回)", inline=False)
                await message.channel.send(embed=embed)

    # --- Main Loop Logic ---
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

        try:
            while True:
                async def update_panel():
                    s = room.settings
                    if not room.custom_settings:
                        rec = room.get_recommended_settings(len(room.players))
                        s_display = rec
                        note = "(自動)"
                    else:
                        s_display = s
                        note = "(カスタム)"
                    m_txt = "手動" if s["mode"]=="MANUAL" else "全自動"
                    role_str = (
                        f"🐺{s_display['lykos']} 狂{s_display['caeneus']} 🔮{s_display['tribbie']} 👻{s_display['castorice']} "
                        f"🛡️{s_display['sirens']} ⚔️{s_display['swordmaster']} 💀{s_display['mordis']} 💣{s_display['cyrene']} 👮{s_display['phainon']} 🐲{s_display['cerydra']}\n"
                        f"🧐{s_display['aglaea']} 🎭{s_display['saphel']} 🦇{s_display['hyanci']}"
                    )
                    sys_str = f"閉鎖:{'ON' if s['auto_close'] else 'OFF'}, 続戦:{'ON' if s['rematch'] else 'OFF'}"
                    embed = discord.Embed(title="参加者募集中", description=f"{m_txt} {note}\n{sys_str}\n{role_str}", color=0x9b59b6)
                    p_names = "\n".join([p.name for p in room.players.values()])
                    embed.add_field(name=f"参加者 {len(room.players)}名", value=p_names or "なし")
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

                await self.run_game(channel.id)

                if room.settings["auto_close"]:
                    await asyncio.sleep(60)
                    await self.cleanup_venue(room)
                else:
                    await room.main_ch.send("🛑 自動閉鎖OFF: 終了するには `!wclose` してください。")
                    while room.phase == "FINISHED":
                        await asyncio.sleep(2)
                        if channel.id not in self.rooms: return 

                if room.settings["rematch"] and channel.id in self.rooms:
                    await self.cleanup_venue(room) 
                    room.reset_for_rematch()
                    await channel.send("🔁 続戦します。ロビーへ戻ります。")
                else:
                    break

        except Exception as e:
            await channel.send(f"⚠️ エラー発生: {e}")
        finally:
            if channel.id in self.rooms:
                r = self.rooms[channel.id]
                await self.cleanup_venue(r)
                del self.rooms[channel.id]

    async def run_game(self, channel_id):
        room = self.rooms[channel_id]
        room.assign_roles()
        target_ch = room.main_ch if room.main_ch else room.lobby_channel

        for p in room.players.values():
            u = self.bot.get_user(p.id)
            if u:
                data = ROLE_DATA.get(p.role, {"desc": "詳細不明", "has_ability": False})
                embed = discord.Embed(title=f"あなたの役職: {p.role}", color=0x2ecc71)
                embed.description = data["desc"]
                if data["has_ability"]:
                    embed.add_field(name="能力", value="✅ **使用可能**", inline=False)
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
            spoiler = "【役職一覧】\n" + "\n".join([f"{p.name}: {p.role}" for p in room.players.values()])
            try: await room.gm_user.send(spoiler)
            except: pass
            
            while True:
                await asyncio.sleep(2)
                if room.phase == "CANCELLED": return
                if room.phase == "FINISHED": return
            return

        # === Auto Mode ===
        await target_ch.send("全自動モード開始。")
        while True:
            if room.phase == "CANCELLED": break
            
            await self.start_night_logic(room)
            if room.phase == "FINISHED": break
            if room.check_winner(): 
                await self.end_game(room, room.check_winner())
                break
            
            await target_ch.send(f"議論 {room.settings['discussion_time']}秒")
            await asyncio.sleep(room.settings['discussion_time'])

            await self.start_vote_logic(room)
            if room.phase == "FINISHED": break
            if room.check_winner(): 
                await self.end_game(room, room.check_winner())
                break

    async def end_game(self, room, winner):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        embed = discord.Embed(title="決着", description=f"勝者: **{winner}**", color=0xf1c40f)
        det = ""
        for p in room.players.values(): det += f"{p.name}: {p.role} ({'生' if p.is_alive else '死'})\n"
        embed.add_field(name="内訳", value=det)
        await target_ch.send(embed=embed)
        
        close_msg = "60秒後に閉鎖" if room.settings["auto_close"] else "自動閉鎖OFF"
        rematch_msg = "続戦あり" if room.settings["rematch"] else "完全終了"
        await target_ch.send(f"ゲーム終了。({close_msg} / {rematch_msg})")
        
        room.phase = "FINISHED"

async def setup(bot):
    await bot.add_cog(WerewolfSystem(bot))