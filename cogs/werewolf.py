# cogs/werewolf.py
import discord
from discord.ext import commands
from discord import ui
import asyncio
from objects import *

# --- Launcher / SettingsModal (前回と同様なので省略形) ---
# ※コピペ時は前回のSettingsModalクラスなどをそのまま使ってください
class Launcher(ui.View):
    def __init__(self, bot_system):
        super().__init__(timeout=None)
        self.bot_system = bot_system
    @ui.button(label="⚔️ オンパロス戦線を開始", style=discord.ButtonStyle.primary, custom_id="ww_create_room")
    async def create_room(self, interaction: discord.Interaction, button: ui.Button):
        await self.bot_system.create_room_logic(interaction)

class SettingsModal(ui.Modal, title="配役設定"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        self.lykos = ui.TextInput(label="ライコス", default=str(room.settings["lykos"]))
        self.tribbie = ui.TextInput(label="トリビー", default=str(room.settings["tribbie"]))
        self.sirens = ui.TextInput(label="セイレンス", default=str(room.settings["sirens"]))
        self.sm = ui.TextInput(label="黒衣の剣士", default=str(room.settings["swordmaster"]))
        self.specials = ui.TextInput(label="特殊(モ/キ/フ)", default="0,0,0", required=False)
        self.add_item(self.lykos)
        self.add_item(self.tribbie)
        self.add_item(self.sirens)
        self.add_item(self.sm)
        self.add_item(self.specials)
    async def on_submit(self, itx):
        try:
            self.room.settings["lykos"] = int(self.lykos.value)
            self.room.settings["tribbie"] = int(self.tribbie.value)
            self.room.settings["sirens"] = int(self.sirens.value)
            self.room.settings["swordmaster"] = int(self.sm.value)
            sp = self.specials.value.split(',')
            if len(sp) >= 3:
                self.room.settings["mordis"] = int(sp[0])
                self.room.settings["cyrene"] = int(sp[1])
                self.room.settings["phainon"] = int(sp[2])
            await itx.response.send_message("設定更新", ephemeral=True)
            await self.callback()
        except: await itx.response.send_message("入力エラー", ephemeral=True)

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
        tid = itx.data['values'][0]
        tid = int(tid) if tid != "none" else None
        await self.callback(itx, self.player, self.action_type, tid)

class VoteView(ui.View):
    def __init__(self, room, player, callback):
        super().__init__(timeout=60)
        self.callback = callback
        options = [discord.SelectOption(label=p.name, value=str(p.id)) for p in room.get_alive() if p.id != player.id]
        select = ui.Select(placeholder="追放する者を選択", options=options)
        select.callback = self.on_vote
        self.add_item(select)
    async def on_vote(self, itx):
        await self.callback(itx, int(itx.data['values'][0]))

# --- Bot System ---
class WerewolfSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rooms = {}

    @commands.command()
    async def panel(self, ctx):
        embed = discord.Embed(title="⚔️ オンパロス戦線", description="火種を巡る争いが始まります。", color=0x8e44ad)
        await ctx.send(embed=embed, view=Launcher(self))
        try: await ctx.message.delete()
        except: pass

    async def create_room_logic(self, itx_or_ctx):
        if isinstance(itx_or_ctx, discord.Interaction):
            channel = itx_or_ctx.channel
            if not itx_or_ctx.response.is_done(): await itx_or_ctx.response.send_message("ロビー作成", ephemeral=True)
        else: channel = itx_or_ctx.channel

        if channel.id in self.rooms: return
        room = GameRoom(channel)
        self.rooms[channel.id] = room

        async def update_panel():
            s = room.settings
            desc = f"🐺ライコス:{s['lykos']} 🔮トリビー:{s['tribbie']} 🛡️セイレンス:{s['sirens']} ⚔️剣士:{s['swordmaster']}\n特殊:{s['mordis']}/{s['cyrene']}/{s['phainon']}"
            embed = discord.Embed(title="参戦者募集中", description=desc, color=0x9b59b6)
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
            @ui.button(label="配役設定", style=discord.ButtonStyle.secondary)
            async def setting(self, itx, btn):
                await itx.response.send_modal(SettingsModal(room, update_panel))
            @ui.button(label="開戦", style=discord.ButtonStyle.danger)
            async def start(self, itx, btn):
                if len(room.players) < 2:
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
            if room.phase == "STARTING": break
        
        await self.run_game(channel.id)

    async def run_game(self, channel_id):
        room = self.rooms[channel_id]
        room.assign_roles()
        
        # --- 役職通知 ---
        # キュレネ用：市民リスト
        citizen_list = [p.name for p in room.players.values() if p.role == ROLE_CITIZEN]
        cit_str = ", ".join(citizen_list) if citizen_list else "なし"

        for p in room.players.values():
            user = self.bot.get_user(p.id)
            if not user: continue
            
            embed = discord.Embed(title=f"あなたの役割: {p.role}", color=0x2ecc71)
            
            if p.role == ROLE_LYKOS:
                mates = [x.name for x in room.players.values() if x.role == ROLE_LYKOS and x.id != p.id]
                embed.description = f"夜に火種を奪い、排除してください。\n仲間: {', '.join(mates) if mates else 'なし'}"
            elif p.role == ROLE_SWORDMASTER:
                embed.description = "あなたは第3陣営です。すべてを斬り伏せ、最後に立っていた者が勝者です。"
            elif p.role == ROLE_CYRENE:
                embed.description = f"あなたが処刑されると敗北します。\n【タイタンの末裔(市民)】: {cit_str}"
            elif p.role == ROLE_MORDIS:
                embed.description = "一度だけ襲撃(火種強奪)を耐えることができます。"
            elif p.role == ROLE_SIRENS:
                embed.description = "夜に一人を選び、火種を守ってください。"
            else:
                embed.description = "ライコスを見つけ出し、追放してください。"

            try: await user.send(embed=embed)
            except: pass
        
        await room.channel.send("🌙 夜が訪れました。")

        day = 1
        while True:
            # === 夜 ===
            room.phase = "NIGHT"
            room.night_actions = {}
            
            async def night_cb(itx, player, act, tid):
                target = room.players[tid] if tid else None
                t_name = target.name if target else "なし"
                
                if act == "divine":
                    res = "ライコス" if target.is_wolf_side else "人間"
                    await itx.response.send_message(f"判定: {t_name} は **{res}** です。", ephemeral=True)
                else:
                    room.night_actions[act] = tid
                    await itx.response.send_message(f"{t_name} を選択。", ephemeral=True)

            tasks_list = []
            for p in room.get_alive():
                user = self.bot.get_user(p.id)
                view = None
                
                if p.role == ROLE_LYKOS:
                    # テキストだけ「強奪」にする
                    view = NightActionView(room, p, "steal", night_cb)
                    msg = "【強奪】 誰の火種を奪い、葬りますか？"
                elif p.role == ROLE_TRIBBIE:
                    view = NightActionView(room, p, "divine", night_cb)
                    msg = "【占い】 誰を調べますか？"
                elif p.role == ROLE_SIRENS:
                    view = NightActionView(room, p, "guard", night_cb)
                    msg = "【護衛】 誰を守りますか？"
                elif p.role == ROLE_SWORDMASTER:
                    view = NightActionView(room, p, "slash", night_cb)
                    msg = "【辻斬り】 誰を始末しますか？"
                
                if view: tasks_list.append(user.send(msg, view=view))
            
            if tasks_list: await asyncio.gather(*tasks_list)
            await asyncio.sleep(20)

            # === 朝 ===
            room.phase = "DAY"
            dead = []
            
            guard_target = room.night_actions.get("guard")
            steal_target = room.night_actions.get("steal") # ライコスの襲撃
            slash_target = room.night_actions.get("slash") # 剣士の襲撃
            
            # ターゲット集計 (強奪も斬撃も、処理は「死」)
            attacks = []
            if steal_target: attacks.append(steal_target)
            if slash_target: attacks.append(slash_target)
            
            attacks = set(attacks)
            
            for tid in attacks:
                # 護衛成功判定 (ライコスの攻撃も剣士の攻撃も守れる設定)
                if tid == guard_target:
                    continue
                
                victim = room.players[tid]
                
                # モーディス判定 (復活権があれば耐える)
                if victim.role == ROLE_MORDIS and victim.mordis_revive_available:
                    victim.mordis_revive_available = False
                    # 死なない
                else:
                    dead.append(victim)

            # --- 結果発表 ---
            msg = f"🌞 **{day}日目の朝**\n"
            dead = list(set(dead))
            if dead:
                for d in dead: d.is_alive = False
                msg += f"昨晩、**{', '.join([d.name for d in dead])}** の火種が消え、帰らぬ人となりました。"
            else:
                msg += "昨晩は犠牲者がいませんでした。"
            
            # 霊媒結果
            if room.last_executed and any(p.role == ROLE_CASTORICE and p.is_alive for p in room.players.values()):
                med_res = "ライコス" if room.last_executed.is_wolf_side else "人間"
                for p in room.get_alive():
                    if p.role == ROLE_CASTORICE:
                        u = self.bot.get_user(p.id)
                        await u.send(f"【霊媒】 昨日処刑された {room.last_executed.name} は **{med_res}** でした。")

            await room.channel.send(msg)

            if room.check_winner():
                await self.end_game(room, room.check_winner())
                break

            # 議論 & 投票
            await room.channel.send(f"議論開始 ({room.settings['discussion_time']}秒)")
            await asyncio.sleep(room.settings['discussion_time'])
            
            room.votes = {}
            async def vote_cb(itx, tid):
                weight = room.players[itx.user.id].vote_weight
                current = room.votes.get(tid, 0)
                room.votes[tid] = current + weight
                await itx.response.send_message("投票済", ephemeral=True)

            vt = []
            for p in room.get_alive():
                u = self.bot.get_user(p.id)
                vt.append(u.send("【投票】 追放する人を選んでください", view=VoteView(room, p, vote_cb)))
            await asyncio.gather(*vt)
            await asyncio.sleep(15)

            if room.votes:
                max_v = max(room.votes.values())
                cands = [k for k,v in room.votes.items() if v == max_v]
                exec_id = random.choice(cands)
                exec_p = room.players[exec_id]
                exec_p.is_alive = False
                room.last_executed = exec_p
                
                if exec_p.role == ROLE_CYRENE:
                    room.cyrene_executed = True
                    await room.channel.send(f"処刑された **{exec_p.name}** は {ROLE_CYRENE} でした...！！\n禁忌に触れたため、オンパロス陣営は敗北しました。")
                else:
                    await room.channel.send(f"投票の結果、**{exec_p.name}** が追放されました。")
            else:
                await room.channel.send("投票なし。")

            if room.check_winner():
                await self.end_game(room, room.check_winner())
                break
            
            day += 1
        
        del self.rooms[channel_id]

    async def end_game(self, room, winner):
        embed = discord.Embed(title="決着", description=f"勝者: **{winner}**", color=0xf1c40f)
        det = ""
        for p in room.players.values():
            status = "生存" if p.is_alive else "死亡"
            det += f"**{p.name}**: {p.role} ({status})\n"
        embed.add_field(name="内訳", value=det)
        await room.channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(WerewolfSystem(bot))