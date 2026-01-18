import discord
from discord.ext import commands
from discord import ui
import asyncio
import random
import unicodedata
import traceback
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

# --- Join Selection View ---
class JoinSelectionView(ui.View):
    def __init__(self, room, update_callback):
        super().__init__(timeout=60)
        self.room = room
        self.update_callback = update_callback

    @ui.button(label="⚔️ プレイヤー参加", style=discord.ButtonStyle.success)
    async def join_player(self, interaction: discord.Interaction, button: ui.Button):
        user = interaction.user
        if hasattr(self.room, 'spectators') and user.id in self.room.spectators:
            del self.room.spectators[user.id]
        
        if user.id not in self.room.players:
            self.room.join(user)
            code_str = getattr(self.room, 'code', '不明')
            await interaction.response.send_message(f"⚔️ **プレイヤー**として参加しました。(部屋コード: {code_str})", ephemeral=True)
            await self.update_callback()
        else:
            await interaction.response.send_message("既にプレイヤーとして参加しています。", ephemeral=True)

    @ui.button(label="👁️ 見学参加", style=discord.ButtonStyle.secondary)
    async def join_spectator(self, interaction: discord.Interaction, button: ui.Button):
        user = interaction.user
        if user.id in self.room.players:
            self.room.leave(user)
        
        if not hasattr(self.room, 'spectators'): self.room.spectators = {}
        
        if user.id not in self.room.spectators:
            self.room.spectators[user.id] = user
            code_str = getattr(self.room, 'code', '不明')
            await interaction.response.send_message(f"👁️ **見学席**に座りました。(部屋コード: {code_str})", ephemeral=True)
            await self.update_callback()
        else:
            await interaction.response.send_message("既に見学参加しています。", ephemeral=True)

    @ui.button(label="👋 離脱", style=discord.ButtonStyle.danger)
    async def leave(self, interaction: discord.Interaction, button: ui.Button):
        user = interaction.user
        removed = False
        if user.id in self.room.players:
            self.room.leave(user)
            removed = True
        if hasattr(self.room, 'spectators') and user.id in self.room.spectators:
            del self.room.spectators[user.id]
            removed = True
        
        if removed:
            await interaction.response.send_message("👋 離脱しました。", ephemeral=True)
            await self.update_callback()
        else:
            await interaction.response.send_message("参加していません。", ephemeral=True)

# --- Lobby View ---
class LobbyView(ui.View):
    def __init__(self, room, update_callback, bot_system):
        super().__init__(timeout=None)
        self.room = room
        self.update_callback = update_callback
        self.bot_system = bot_system

    @ui.button(label="参戦/離脱", style=discord.ButtonStyle.success)
    async def join(self, itx: discord.Interaction, btn: ui.Button):
        await itx.response.send_message("参加タイプを選択してください:", view=JoinSelectionView(self.room, self.update_callback), ephemeral=True)

    @ui.button(label="設定", style=discord.ButtonStyle.secondary)
    async def setting(self, itx: discord.Interaction, btn: ui.Button):
        self.room.gm_user = itx.user
        await itx.response.send_message("設定メニュー:", view=SettingsMenuView(self.room, self.update_callback), ephemeral=True)

    @ui.button(label="💥 解散", style=discord.ButtonStyle.secondary)
    async def cancel(self, itx: discord.Interaction, btn: ui.Button):
        self.room.phase = "CANCELLED"
        await itx.response.send_message("部屋を解散します...", ephemeral=True)
        self.stop()

    @ui.button(label="開戦", style=discord.ButtonStyle.danger)
    async def start(self, itx: discord.Interaction, btn: ui.Button):
        if self.room.settings["mode"] == "MANUAL":
            self.room.gm_user = itx.user
        if len(self.room.players) < 2:
            await itx.response.send_message("人数不足です（最低2名）。", ephemeral=True)
            return
        await itx.response.send_message("🚀 ゲームを開始します！")
        self.stop()
        self.room.phase = "STARTING"


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
        if self.target.mordis_revive_available: status.append("復活:有")
        if self.target.role == ROLE_CERYDRA: status.append("x2票")
        if self.target.role == ROLE_CYRENE: status.append(f"自衛:{self.target.cyrene_guard_count} バフ:{self.target.cyrene_buff_count}")
        if self.target.role == ROLE_HYANCI: status.append(f"イカルン:{self.target.hyanci_ikarun_count}")
        if self.target.role == ROLE_SAPHEL: status.append(f"バフ残:{self.target.cyrene_buff_count} 模倣呪:{getattr(self.target, 'mimicking_cyrene', False)}")
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

# --- Settings & Menus ---

class SettingsMenuView(ui.View):
    def __init__(self, room, update_callback):
        super().__init__(timeout=60)
        self.room = room
        self.update_callback = update_callback

    @ui.button(label="🐺 配役:基本(人狼/村)", style=discord.ButtonStyle.primary, row=0)
    async def role_basic(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_modal(RoleSettingsBasicModal(self.room, self.update_callback))

    @ui.button(label="⚔️ 配役:攻撃/特殊", style=discord.ButtonStyle.primary, row=0)
    async def role_advanced(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_modal(RoleSettingsAdvancedModal(self.room, self.update_callback))

    @ui.button(label="🦇 配役:その他", style=discord.ButtonStyle.primary, row=0)
    async def role_extra(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_modal(RoleSettingsExtraModal(self.room, self.update_callback))

    @ui.button(label="⚙️ ゲーム設定", style=discord.ButtonStyle.secondary, row=1)
    async def game_settings(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_modal(GameSettingsModal(self.room, self.update_callback))

    @ui.button(label="👥 メンバー編集", style=discord.ButtonStyle.danger, row=1)
    async def manage_members(self, interaction: discord.Interaction, button: ui.Button):
        if not self.check_perm(interaction): return
        await interaction.response.send_message("追放するメンバーを選択してください:", view=PlayerManagementView(self.room, self.update_callback), ephemeral=True)

    def check_perm(self, interaction):
        if interaction.user.id != self.room.gm_user.id:
            asyncio.create_task(interaction.response.send_message("権限がありません。", ephemeral=True))
            return False
        return True

class RoleSettingsBasicModal(ui.Modal, title="配役設定: 基本"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        s = room.settings if room.custom_settings else room.get_recommended_settings(len(room.players))
        
        self.add_item(ui.TextInput(label=f"🐺 {ROLE_LYKOS} (人狼)", default=str(s.get('lykos', 0))))
        self.add_item(ui.TextInput(label=f"👺 {ROLE_CAENEUS} (狂人)", default=str(s.get('caeneus', 0))))
        self.add_item(ui.TextInput(label=f"🔮 {ROLE_TRIBBIE} (占い)", default=str(s.get('tribbie', 0))))
        self.add_item(ui.TextInput(label=f"🛡️ {ROLE_SIRENS} (騎士)", default=str(s.get('sirens', 0))))
        self.add_item(ui.TextInput(label=f"👻 {ROLE_CASTORICE} (霊媒)", default=str(s.get('castorice', 0))))

    async def on_submit(self, itx):
        try:
            self.room.settings['lykos'] = int(self.children[0].value)
            self.room.settings['caeneus'] = int(self.children[1].value)
            self.room.settings['tribbie'] = int(self.children[2].value)
            self.room.settings['sirens'] = int(self.children[3].value)
            self.room.settings['castorice'] = int(self.children[4].value)
            self.room.custom_settings = True
            await itx.response.send_message("✅ 基本配役を更新しました。", ephemeral=True)
            await self.callback()
        except: await itx.response.send_message("エラー: 数字を入力してください", ephemeral=True)

class RoleSettingsAdvancedModal(ui.Modal, title="配役設定: 攻撃・特殊"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        s = room.settings if room.custom_settings else room.get_recommended_settings(len(room.players))
        
        self.add_item(ui.TextInput(label=f"⚔️ {ROLE_SWORDMASTER} (辻斬り)", default=str(s.get('swordmaster', 0))))
        self.add_item(ui.TextInput(label=f"🔪 {ROLE_PHAINON} (暗殺)", default=str(s.get('phainon', 0))))
        self.add_item(ui.TextInput(label=f"💀 {ROLE_MORDIS} (耐久)", default=str(s.get('mordis', 0))))
        self.add_item(ui.TextInput(label=f"❤️ {ROLE_CYRENE} (愛)", default=str(s.get('cyrene', 0))))
        self.add_item(ui.TextInput(label=f"🐲 {ROLE_CERYDRA} (権力)", default=str(s.get('cerydra', 0))))

    async def on_submit(self, itx):
        try:
            self.room.settings['swordmaster'] = int(self.children[0].value)
            self.room.settings['phainon'] = int(self.children[1].value)
            self.room.settings['mordis'] = int(self.children[2].value)
            self.room.settings['cyrene'] = int(self.children[3].value)
            self.room.settings['cerydra'] = int(self.children[4].value)
            self.room.custom_settings = True
            await itx.response.send_message("✅ 上級配役を更新しました。", ephemeral=True)
            await self.callback()
        except: await itx.response.send_message("エラー: 数字を入力してください", ephemeral=True)

class RoleSettingsExtraModal(ui.Modal, title="配役設定: その他"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        s = room.settings if room.custom_settings else room.get_recommended_settings(len(room.players))
        
        self.add_item(ui.TextInput(label=f"🧐 {ROLE_AGLAEA} (調査)", default=str(s.get('aglaea', 0))))
        self.add_item(ui.TextInput(label=f"🎭 {ROLE_SAPHEL} (模倣)", default=str(s.get('saphel', 0))))
        self.add_item(ui.TextInput(label=f"🦇 {ROLE_HYANCI} (蝙蝠)", default=str(s.get('hyanci', 0))))

    async def on_submit(self, itx):
        try:
            self.room.settings['aglaea'] = int(self.children[0].value)
            self.room.settings['saphel'] = int(self.children[1].value)
            self.room.settings['hyanci'] = int(self.children[2].value)
            self.room.custom_settings = True
            await itx.response.send_message("✅ その他配役を更新しました。", ephemeral=True)
            await self.callback()
        except: await itx.response.send_message("エラー: 数字を入力してください", ephemeral=True)

class GameSettingsModal(ui.Modal, title="ゲーム設定"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        s = room.settings

        mode_val = "1" if s["mode"] == "MANUAL" else "0"
        time_val = str(s.get("discussion_time", 60))
        close_val = "1" if s["auto_close"] else "0"
        rematch_val = "1" if s["rematch"] else "0"

        self.inp_mode = ui.TextInput(label="進行モード (0:自動 / 1:手動)", default=mode_val, placeholder="0 または 1", min_length=1, max_length=1)
        self.inp_time = ui.TextInput(label="議論時間 (秒) ※自動モード時", default=time_val, placeholder="60")
        self.inp_close = ui.TextInput(label="ゲーム後自動閉鎖 (0:OFF / 1:ON)", default=close_val, placeholder="0 または 1", min_length=1, max_length=1)
        self.inp_rematch = ui.TextInput(label="続戦機能 (0:OFF / 1:ON)", default=rematch_val, placeholder="0 または 1", min_length=1, max_length=1)

        self.add_item(self.inp_mode)
        self.add_item(self.inp_time)
        self.add_item(self.inp_close)
        self.add_item(self.inp_rematch)

    async def on_submit(self, itx):
        try:
            mode = "MANUAL" if self.inp_mode.value.strip() == "1" else "AUTO"
            disc_time = int(self.inp_time.value.strip())
            if disc_time < 10: disc_time = 10 
            auto_close = True if self.inp_close.value.strip() == "1" else False
            rematch = True if self.inp_rematch.value.strip() == "1" else False

            self.room.settings["mode"] = mode
            self.room.settings["discussion_time"] = disc_time
            self.room.settings["auto_close"] = auto_close
            self.room.settings["rematch"] = rematch
            
            m_str = "手動" if mode == "MANUAL" else "自動"
            c_str = "ON" if auto_close else "OFF"
            r_str = "ON" if rematch else "OFF"

            await itx.response.send_message(f"✅ ゲーム設定更新: モード={m_str}, 時間={disc_time}秒, 閉鎖={c_str}, 続戦={r_str}", ephemeral=True)
            await self.callback()
        except ValueError:
            await itx.response.send_message("エラー: 数値を入力してください。", ephemeral=True)

class PlayerManagementView(ui.View):
    def __init__(self, room, callback):
        super().__init__(timeout=60)
        self.room = room
        self.callback = callback
        
        options = []
        for p in room.players.values():
            options.append(discord.SelectOption(label=p.name, value=str(p.id), description=f"ID: {p.id}"))
        
        if not options:
            options.append(discord.SelectOption(label="参加者なし", value="none"))

        self.select = ui.Select(placeholder="追放するメンバーを選択...", options=options, max_values=1)
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def on_select(self, interaction: discord.Interaction):
        if self.select.values[0] == "none":
            return await interaction.response.send_message("対象がいません。", ephemeral=True)
        
        target_id = int(self.select.values[0])
        player = self.room.players.get(target_id)
        
        if player:
            if player.id == self.room.gm_user.id:
                 return await interaction.response.send_message("GM自身は追放できません。", ephemeral=True)
            
            self.room.leave(player.member)
            await interaction.response.send_message(f"👋 **{player.name}** を追放しました。", ephemeral=True)
            await self.callback()
        else:
            await interaction.response.send_message("プレイヤーが見つかりません。", ephemeral=True)

# --- Views (In-Game) ---
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
            elif p.id == player.id: continue 
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

        self.btn_skip = ui.Button(label="パス (何もしない)", style=discord.ButtonStyle.secondary, row=1)
        self.btn_skip.callback = self.on_skip
        self.add_item(self.btn_skip)

    async def on_submit(self, itx):
        pass 

    async def on_skip(self, itx):
        await self.callback(itx, self.player, "mimic", None)


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
    
    def generate_room_code(self):
        while True:
            code = str(random.randint(1000, 9999))
            if not any(getattr(r, 'code', '') == code for r in self.rooms.values()):
                return code

    async def setup_venue(self, room):
        # 既に作成済みならスキップ
        if room.main_ch: return

        guild = room.lobby_channel.guild
        cat_ov = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        if room.gm_user:
            cat_ov[room.gm_user] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        try:
            cat_name = f"⚔️ オンパロス戦線-{room.code}"
            room.category = await guild.create_category(cat_name, overwrites=cat_ov)
            
            main_ov = cat_ov.copy()
            grave_ov = cat_ov.copy()
            
            # 初期権限設定 (プレイヤーはメインOK、見学者はメイン閲覧のみ)
            for p in room.players.values():
                main_ov[p.member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            for s in getattr(room, 'spectators', {}).values():
                main_ov[s] = discord.PermissionOverwrite(read_messages=True, send_messages=False)
                grave_ov[s] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            room.main_ch = await room.category.create_text_channel("🌞議論-day", overwrites=main_ov)
            room.grave_ch = await room.category.create_text_channel("🪦墓場-graveyard", overwrites=grave_ov)
            
            # 部屋IDを新しいメインチャンネルIDで登録し直す
            self.rooms[room.main_ch.id] = room
            
            # ★修正: 参加者全員へのメンションを追加
            mentions = [p.member.mention for p in room.players.values()]
            mention_str = " ".join(mentions) if mentions else ""
            
            await room.main_ch.send(f"{mention_str}\n会場を作成しました。部屋コード: `{room.code}`\nこれよりゲームを開始します！")

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

        is_mimicking = getattr(player, 'mimicking_cyrene', False)
        if player.role == ROLE_CYRENE or is_mimicking:
            if room.main_ch:
                await room.main_ch.send(f"⚠️ **{player.name}** ({ROLE_CYRENE}の力) が死亡しました！\n禁忌が破られ、オンパロス陣営の火種が全て消滅します...")
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
            player.cyrene_buff_count = 2
        if player.role == ROLE_HYANCI:
            player.hyanci_ikarun_count = 2
            player.hyanci_protection_active = False
        if player.role == ROLE_SIRENS:
            player.last_guarded_id = None
        if player.role == ROLE_SAPHEL:
            player.mimicking_cyrene = False
            player.cyrene_buff_count = 1

        if room.main_ch and room.grave_ch:
            await room.main_ch.set_permissions(player.member, read_messages=True, send_messages=True)
            await room.grave_ch.set_permissions(player.member, overwrite=None)
            await room.main_ch.send(f"😇 奇跡が起き、**{player.name}** の火種が戻りました！（能力も全快）")
            await room.grave_ch.send(f"😇 **{player.name}** が蘇生され、戦場へ戻りました。")

    async def start_night_logic(self, room):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        await target_ch.send("🌙 **夜のアクション** を開始します。")
        
        for p in room.players.values():
            p.hyanci_protection_active = False
            if p.role == ROLE_SAPHEL:
                p.vote_weight = 1
                p.mimicking_cyrene = False

        active_roles = [ROLE_LYKOS, ROLE_TRIBBIE, ROLE_SIRENS, ROLE_SWORDMASTER, ROLE_PHAINON, ROLE_CYRENE, ROLE_AGLAEA, ROLE_SAPHEL, ROLE_HYANCI]
        pending_actors = set([p.id for p in room.get_alive() if p.role in active_roles])
        pending_2nd_actors = set()
        
        room.night_actions = {} 

        async def cb(itx, player, act, val):
            room.night_actions[act] = val
            target = None
            target_name = "なし"
            if val == "self_guard": target_name = "自分"
            elif val == "use": target_name = "イカルン"
            elif isinstance(val, int):
                target = room.players.get(val)
                if target: target_name = target.name
            elif isinstance(val, dict) and act == "mimic":
                src = room.players.get(val['source'])
                dst = room.players.get(val['target'])
                src_name = src.name if src else "なし"
                dst_name = dst.name if dst else "なし"
                target_name = f"{src_name} → {dst_name}"

            if act == "mimic":
                if val is None:
                    await itx.response.edit_message(content="🎭 スキップしました。", view=None)
                    pending_actors.discard(player.id)
                elif isinstance(val, int):
                    # target is already set above
                    if not target: return
                    
                    room.night_actions["mimic_src"] = val
                    action_map = {
                        ROLE_TRIBBIE: "🔮 模倣: 誰を占いますか？",
                        ROLE_SIRENS: "🛡️ 模倣: 誰を護衛しますか？",
                        ROLE_SWORDMASTER: "⚔️ 模倣: 誰を襲撃しますか？",
                        ROLE_PHAINON: "🔪 模倣: 誰を暗殺しますか？",
                        ROLE_AGLAEA: "🧐 模倣: 誰の投票先を調べますか？",
                        ROLE_CYRENE: "🐲 模倣: 誰にバフを与えますか？"
                    }
                    if target.role in action_map:
                        msg = action_map[target.role]
                        await itx.response.edit_message(content=f"🎭 {target.name} ({target.role}) を模倣します。", view=None)
                        try:
                            u = self.bot.get_user(player.id)
                            await u.send(msg, view=NightActionView(room, player, "mimic_2nd", cb))
                        except: pass
                    else:
                        await itx.response.edit_message(content=f"🎭 {target.name} ({target.role}) を模倣しました。", view=None)
                        room.night_actions["mimic"] = {'source': val, 'target': None}
                        pending_actors.discard(player.id)
            
            elif act == "mimic_2nd":
                src_id = room.night_actions.get("mimic_src")
                room.night_actions["mimic"] = {'source': src_id, 'target': val}
                await itx.response.edit_message(content=f"👉 {target_name} に能力を行使します。", view=None)
                pending_actors.discard(player.id)

            elif act == "cyrene_buff" and target:
                player.cyrene_buff_count -= 1
                await itx.response.edit_message(content=f"💪 {target_name} に力を与えました。", view=None)
                
                action_map = {
                    ROLE_LYKOS: ("steal_2nd", "【バフ効果】 2人目の強奪対象を選んでください"),
                    ROLE_TRIBBIE: ("divine_2nd", "【バフ効果】 2人目の占い対象を選んでください"),
                    ROLE_SIRENS: ("guard_2nd", "【バフ効果】 2人目の護衛対象を選んでください"),
                    ROLE_SWORDMASTER: ("slash_2nd", "【バフ効果】 2人目の辻斬り対象を選んでください"),
                    ROLE_PHAINON: ("assassinate_2nd", "【バフ効果】 2人目の暗殺対象を選んでください")
                }
                if target.role in action_map:
                    act_key, msg = action_map[target.role]
                    pending_2nd_actors.add(target.id)
                    try:
                        u = self.bot.get_user(target.id)
                        await u.send(msg, view=NightActionView(room, target, act_key, cb))
                    except: pass
                
                pending_actors.discard(player.id)

            elif act in ["steal_2nd", "divine_2nd", "guard_2nd", "slash_2nd", "assassinate_2nd"]:
                await itx.response.edit_message(content=f"✅ {target_name} (2人目) を選択。", view=None)
                pending_2nd_actors.discard(player.id)

            elif act == "hyanci_ikarun":
                if val == "use":
                    player.hyanci_ikarun_count -= 1
                    player.hyanci_protection_active = True
                    await itx.response.edit_message(content=f"🦇 イカルンを捧げました。(残{player.hyanci_ikarun_count})", view=None)
                else:
                    await itx.response.edit_message(content="🦇 何もしませんでした。", view=None)
                pending_actors.discard(player.id)

            elif act in ["divine"]:
                res = "ライコス" if target and target.is_wolf_side else "人間"
                await itx.response.edit_message(content=f"🔮 判定: {target_name}は**{res}**", view=None)
                if room.gm_user: await room.gm_user.send(f"🔮 {player.name} -> {target_name} : {res}")
                pending_actors.discard(player.id)
            
            elif act == "investigate":
                last_vote = room.prev_votes.get(target.id) if target else None
                vt_name = "なし"
                if last_vote == "skip": vt_name = "スキップ"
                elif last_vote:
                    vt = room.players.get(last_vote)
                    if vt: vt_name = vt.name
                if not room.prev_votes: vt_name = "（投票履歴なし）"
                await itx.response.edit_message(content=f"🧐 調査結果: {target_name} の投票先は **{vt_name}** です。", view=None)
                pending_actors.discard(player.id)

            elif act == "cyrene_guard":
                if val == "self_guard":
                    player.cyrene_guard_count -= 1
                    await itx.response.edit_message(content=f"🛡️ 自分を護衛しました。(残{player.cyrene_guard_count}回)", view=None)
                else:
                    await itx.response.edit_message(content="🛡️ 自衛をスキップしました。", view=None)
                pending_actors.discard(player.id)
            
            else:
                act_str = {"steal":"強奪", "guard":"護衛", "slash":"辻斬り", "assassinate":"暗殺"}.get(act, act)
                await itx.response.edit_message(content=f"✅ {target_name}を選択 ({act_str})", view=None)
                if room.gm_user: await room.gm_user.send(f"🌙 {player.name} ({player.role}) -> {target_name}")
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
            
            if p.role == ROLE_SAPHEL:
                class SaphelStartView(ui.View):
                    def __init__(self, room, player, cb):
                        super().__init__(timeout=120)
                        self.cb = cb
                        self.player = player
                        opts = []
                        for x in room.get_alive():
                            if x.id != player.id: opts.append(discord.SelectOption(label=x.name, value=str(x.id)))
                        if not opts: opts.append(discord.SelectOption(label="なし", value="none"))
                        sel = ui.Select(placeholder="🎭 誰の能力を模倣しますか？", options=opts)
                        sel.callback = self.on_sel
                        self.add_item(sel)
                        btn = ui.Button(label="パス", style=discord.ButtonStyle.secondary)
                        btn.callback = self.on_skip
                        self.add_item(btn)
                    async def on_sel(self, itx):
                        val = int(itx.data['values'][0]) if itx.data['values'][0] != "none" else None
                        await self.cb(itx, self.player, "mimic", val)
                    async def on_skip(self, itx):
                        await self.cb(itx, self.player, "mimic", None)
                
                view = SaphelStartView(room, p, cb)
                msg = "【模倣】 誰の能力を使用しますか？"
            
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
                    embed = discord.Embed(title="🌙 アクションなし", description="イカルン切れ。", color=0x2c3e50)
                    tasks.append(self.bot.get_user(p.id).send(embed=embed))
                    pending_actors.discard(p.id)

            if not view and p.role not in [ROLE_CYRENE, ROLE_HYANCI, ROLE_SAPHEL]:
                try:
                    u = self.bot.get_user(p.id)
                    embed = discord.Embed(title="🌙 静寂の夜", description="今夜、あなたが行えるアクションはありません。", color=0x2c3e50)
                    tasks.append(u.send(embed=embed))
                except: pass

        if tasks: await asyncio.gather(*tasks)
        else: await target_ch.send("（能力を使用できる生存者がいません）")

        wait_time = 0
        while len(pending_actors) > 0 or len(pending_2nd_actors) > 0:
            await asyncio.sleep(1)
            wait_time += 1
            if wait_time > 300:
                await target_ch.send("⏰ 時間切れにより夜を終了します。")
                break
            if room.phase == "CANCELLED": return

        await self.resolve_morning(room)

    async def resolve_morning(self, room):
        target_ch = room.main_ch if room.main_ch else room.lobby_channel
        
        if room.last_executed:
            mediums = [p for p in room.get_alive() if p.role == ROLE_CASTORICE]
            species = "ライコス (人狼)" if room.last_executed.is_wolf_side else "人間"
            for medium in mediums:
                try:
                    u = self.bot.get_user(medium.id)
                    if u: await u.send(f"👻 霊媒結果: 昨日処刑された **{room.last_executed.name}** は **{species}** でした。")
                except: pass
            room.last_executed = None

        saphel_id = room.night_actions.get("mimic")
        saphel_actor = next((p for p in room.get_alive() if p.role == ROLE_SAPHEL), None)
        saphel_attack = None
        saphel_guard = None
        extra_buff_target = None
        dead_candidates = []

        if saphel_actor and saphel_id and isinstance(saphel_id, dict):
            src = room.players.get(saphel_id['source'])
            dst = room.players.get(saphel_id['target'])
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
                    if saphel_actor.cyrene_buff_count > 0:
                        saphel_actor.cyrene_buff_count -= 1
                        saphel_actor.mimicking_cyrene = True
                        if dst: extra_buff_target = dst
                        if room.gm_user: await room.gm_user.send("🎭 サフェル -> キュレネ模倣 (呪い&バフ)")
                    else:
                        if room.gm_user: await room.gm_user.send("🎭 サフェル -> キュレネ模倣失敗 (回数切れ)")
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

        # サフェル(キュレネ模倣)によるバフ: ランダム追撃
        if extra_buff_target and extra_buff_target.is_alive:
            if extra_buff_target.role == ROLE_LYKOS:
                others = [p.id for p in room.get_alive() if p.role != ROLE_LYKOS and p.id != steal[0]]
                if others: steal.append(random.choice(others))
            elif extra_buff_target.role == ROLE_SWORDMASTER:
                others = [p.id for p in room.get_alive() if p.id != slash[0]]
                if others: slash.append(random.choice(others))

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
                if victim.mordis_revive_available:
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

    # --- Main Loop Logic ---
    async def create_room_logic(self, itx_or_ctx):
        channel = None
        user = None
        if isinstance(itx_or_ctx, discord.Interaction):
            channel = itx_or_ctx.channel
            user = itx_or_ctx.user
            # 応答待ち
            await itx_or_ctx.response.send_message("ロビー作成中...", ephemeral=True)
        else:
            channel = itx_or_ctx.channel
            user = itx_or_ctx.author
        
        if channel is None: return

        if channel.id in self.rooms:
            msg = "このチャンネルには既に部屋があります。"
            if isinstance(itx_or_ctx, discord.Interaction):
                await itx_or_ctx.followup.send(msg, ephemeral=True)
            else:
                await channel.send(msg)
            return

        room = GameRoom(channel)
        room.gm_user = user
        room.spectators = {}  # 見学者リスト
        room.code = self.generate_room_code() # 部屋コード発行
        self.rooms[channel.id] = room

        # ★非同期タスクとしてゲームループを開始
        asyncio.create_task(self.game_loop(channel, room))

    async def game_loop(self, channel, room):
        # メッセージ管理変数をroomに持たせる
        room.lobby_msg = None
        
        # パネル更新関数 (roomから呼び出せるようにする)
        async def update_panel():
            if not room.lobby_msg: return
            
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
                f"🛡️{s_display['sirens']} ⚔️{s_display['swordmaster']} 💀{s_display['mordis']} ❤️{s_display['cyrene']} 👮{s_display['phainon']} 🐲{s_display['cerydra']}\n"
                f"🧐{s_display['aglaea']} 🎭{s_display['saphel']} 🦇{s_display['hyanci']}"
            )
            sys_str = f"閉鎖:{'ON' if s['auto_close'] else 'OFF'}, 続戦:{'ON' if s['rematch'] else 'OFF'}"
            
            embed = discord.Embed(title="参加者募集中", description=f"{m_txt} {note}\n{sys_str}\n{role_str}", color=0x9b59b6)
            embed.add_field(name="🔑 部屋コード", value=f"`{room.code}`", inline=False)
            
            p_names = "\n".join([p.name for p in room.players.values()])
            s_names = "\n".join([u.display_name for u in room.spectators.values()])
            
            embed.add_field(name=f"参加者 {len(room.players)}名", value=p_names or "なし")
            embed.add_field(name=f"見学者 {len(room.spectators)}名", value=s_names or "なし")
            
            try:
                # Viewを再生成して渡す
                new_view = LobbyView(room, update_panel, self)
                await room.lobby_msg.edit(embed=embed, view=new_view)
            except Exception as e:
                print(f"Update panel error: {e}")

        # コールバック登録
        room.update_panel_callback = update_panel

        try:
            while True:
                # 初回メッセージ送信
                view = LobbyView(room, update_panel, self)
                room.lobby_msg = await channel.send(embed=discord.Embed(title="待機中..."), view=view)
                await update_panel()

                # 待機
                while room.phase == "WAITING":
                    await asyncio.sleep(1)
                    if room.phase == "CANCELLED":
                        await self.cleanup_venue(room)
                        if channel.id in self.rooms: del self.rooms[channel.id]
                        return
                    if room.phase == "STARTING": break
                
                await self.setup_venue(room)
                if room.phase == "CANCELLED":
                    await self.cleanup_venue(room)
                    if channel.id in self.rooms: del self.rooms[channel.id]
                    return

                # ★修正: 復活させた run_game メソッドを呼び出し
                await self.run_game(room.main_ch.id)

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
            traceback.print_exc()
        finally:
            if channel.id in self.rooms:
                r = self.rooms[channel.id]
                await self.cleanup_venue(r)
                del self.rooms[channel.id]

    # ★追加: 復活させた run_game メソッド
    async def run_game(self, channel_id):
        room = self.rooms[channel_id]
        room.assign_roles()
        target_ch = room.main_ch if room.main_ch else room.lobby_channel

        # 役職DM送信
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
                    embed.add_field(name="仲間の人狼", value=", ".join(mates) if mates else "なし", inline=False)
                try: await u.send(embed=embed)
                except: pass

        # 手動モード
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

        # 自動モードループ
        await target_ch.send("全自動モード開始。")
        while True:
            if room.phase == "CANCELLED": break
            
            # 朝（議論）
            await target_ch.send(f"議論 {room.settings['discussion_time']}秒")
            await asyncio.sleep(room.settings['discussion_time'])

            # 投票
            await self.start_vote_logic(room)
            if room.phase == "FINISHED": break
            if room.check_winner(): 
                await self.end_game(room, room.check_winner())
                break
            
            # 夜アクション
            await self.start_night_logic(room)
            if room.phase == "FINISHED": break
            if room.check_winner(): 
                await self.end_game(room, room.check_winner())
                break

    # ★修正: !create コマンドを追加
    @commands.command()
    async def create(self, ctx):
        await self.create_room_logic(ctx)

    # ★追加: !join コマンドを追加
    @commands.command()
    async def join(self, ctx, code: str = None):
        if not code:
            await ctx.send("部屋コードを指定してください。例: `!join 1234`")
            return
        
        target_room = None
        for room in self.rooms.values():
            if getattr(room, 'code', '') == code:
                target_room = room
                break
        
        if target_room:
            # 既にプレイヤーなら何もしない
            if ctx.author.id in target_room.players:
                await ctx.send("既にプレイヤーとして参加しています。")
                return

            # 見学からは外す
            if hasattr(target_room, 'spectators') and ctx.author.id in target_room.spectators:
                del target_room.spectators[ctx.author.id]

            target_room.join(ctx.author)
            await ctx.send(f"✅ 部屋 `{code}` に参加しました！")
            
            # ★修正: パネル更新を実行
            if hasattr(target_room, 'update_panel_callback'):
                await target_room.update_panel_callback()
                
        else:
            await ctx.send(f"部屋コード `{code}` が見つかりません。")

    # ★修正: パネルコマンドで参加も可能に
    @commands.command()
    async def panel(self, ctx, code: str = None):
        # もしコード指定があれば参加処理へ
        if code:
            await self.join(ctx, code)
            return

        room_list = ""
        if self.rooms:
            for ch_id, room in self.rooms.items():
                ch = self.bot.get_channel(ch_id)
                ch_name = ch.name if ch else "不明"
                mode = "手動" if room.settings["mode"] == "MANUAL" else "自動"
                code_str = getattr(room, 'code', 'なし')
                room_list += f"• **{ch_name}** (Code: {code_str}): {len(room.players)}人 ({mode})\n"
        else: room_list = "なし"
        embed = discord.Embed(title="⚔️ オンパロス戦線 ロビー", description=f"現在のルーム:\n{room_list}", color=0x8e44ad)
        await ctx.send(embed=embed, view=Launcher(self))
        try: await ctx.message.delete()
        except: pass

async def setup(bot):
    await bot.add_cog(WerewolfSystem(bot))