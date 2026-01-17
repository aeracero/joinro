import discord
from discord.ext import commands
from discord import ui
import asyncio
from objects import *

# --- Launcher (常設ボタン) ---
class Launcher(ui.View):
    def __init__(self, bot_system):
        super().__init__(timeout=None)
        self.bot_system = bot_system
    
    @ui.button(label="⚔️ オンパロス戦線を作成", style=discord.ButtonStyle.primary, custom_id="ww_create_room")
    async def create_room(self, interaction: discord.Interaction, button: ui.Button):
        await self.bot_system.create_room_logic(interaction)

# --- GM用コントロールパネル (★新規追加) ---
class GMControlView(ui.View):
    def __init__(self, room):
        super().__init__(timeout=None)
        self.room = room

    @ui.button(label="📋 役職・生存状況を確認 (GMのみ)", style=discord.ButtonStyle.secondary, emoji="🕵️")
    async def check_status(self, interaction: discord.Interaction, button: ui.Button):
        # GM本人かチェック
        if not self.room.gm_user or interaction.user.id != self.room.gm_user.id:
            await interaction.response.send_message("あなたはGMではありません。", ephemeral=True)
            return

        # 状況一覧を作成
        embed = discord.Embed(title="🕵️ GM用ダッシュボード", description="現在の全プレイヤー状況です。\nこの画面はあなたにしか見えていません。", color=0x2b2d31)
        
        alive_text = ""
        dead_text = ""
        
        # プレイヤーリスト生成
        for p in self.room.players.values():
            # 役職・生存アイコン
            icon = "🟢" if p.is_alive else "💀"
            status = "生存" if p.is_alive else "死亡"
            
            # 特殊状態の表示 (モーディスの復活権など)
            extras = []
            if p.role == ROLE_MORDIS and p.mordis_revive_available: extras.append("復活可")
            if p.role == ROLE_PHAINON: extras.append("x2票")
            extra_str = f" ({', '.join(extras)})" if extras else ""

            line = f"{icon} **{p.name}** : `{p.role}` {extra_str}\n"
            
            if p.is_alive:
                alive_text += line
            else:
                dead_text += line
        
        embed.add_field(name="生存者", value=alive_text or "なし", inline=False)
        if dead_text:
            embed.add_field(name="死亡・脱落者", value=dead_text, inline=False)
        
        # 自分(GM)だけにしか見えないメッセージとして送信
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- 設定モーダル ---
class SettingsModal(ui.Modal, title="配役・モード設定"):
    def __init__(self, room, callback):
        super().__init__()
        self.room = room
        self.callback = callback
        
        curr = "1" if room.settings["mode"] == "MANUAL" else "0"
        self.mode_input = ui.TextInput(label="モード (0:自動 / 1:手動GM)", default=curr, max_length=1)
        self.lykos = ui.TextInput(label="ライコス", default=str(room.settings["lykos"]))
        self.tribbie = ui.TextInput(label="トリビー", default=str(room.settings["tribbie"]))
        self.sirens = ui.TextInput(label="セイレンス", default=str(room.settings["sirens"]))
        self.specials = ui.TextInput(label="剣士,モ,キ,フ (例:1,0,0,0)", default=f"{room.settings['swordmaster']},{room.settings['mordis']},{room.settings['cyrene']},{room.settings['phainon']}")

        self.add_item(self.mode_input)
        self.add_item(self.lykos)
        self.add_item(self.tribbie)
        self.add_item(self.sirens)
        self.add_item(self.specials)

    async def on_submit(self, itx):
        try:
            self.room.settings["mode"] = "MANUAL" if self.mode_input.value == "1" else "AUTO"
            self.room.settings["lykos"] = int(self.lykos.value)
            self.room.settings["tribbie"] = int(self.tribbie.value)
            self.room.settings["sirens"] = int(self.sirens.value)
            
            sp = self.specials.value.split(',')
            if len(sp) >= 1: self.room.settings["swordmaster"] = int(sp[0])
            if len(sp) >= 2: self.room.settings["mordis"] = int(sp[1])
            if len(sp) >= 3: self.room.settings["cyrene"] = int(sp[2])
            if len(sp) >= 4: self.room.settings["phainon"] = int(sp[3])
            
            m_str = "手動GM" if self.room.settings["mode"] == "MANUAL" else "全自動"
            await itx.response.send_message(f"設定更新: {m_str}", ephemeral=True)
            await self.callback()
        except: await itx.response.send_message("入力エラー", ephemeral=True)

# --- Action Views ---
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
        super().__init__(timeout=120)
        self.callback = callback
        options = [discord.SelectOption(label=p.name, value=str(p.id)) for p in room.get_alive() if p.id != player.id]
        if not options: options.append(discord.SelectOption(label="投票先なし", value="none"))
        select = ui.Select(placeholder="投票先", options=options)
        select.callback = self.on_vote
        self.add_item(select)
    async def on_vote(self, itx):
        val = itx.data['values'][0]
        tid = int(val) if val != "none" else None
        await self.callback(itx, tid)

# --- Bot System ---
class WerewolfSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rooms = {}

    @commands.command()
    async def panel(self, ctx):
        room_list_text = ""
        if self.rooms:
            for ch_id, room in self.rooms.items():
                ch = self.bot.get_channel(ch_id)
                ch_name = ch.name if ch else "不明"
                cnt = len(room.players)
                mode = "手動" if room.settings["mode"] == "MANUAL" else "自動"
                status = "募集中" if room.phase == "WAITING" else "進行中"
                room_list_text += f"• **{ch_name}**: {cnt}人 ({mode}/{status})\n"
        else:
            room_list_text = "現在進行中のルームはありません。"

        embed = discord.Embed(title="⚔️ オンパロス戦線 ロビー", color=0x8e44ad)
        embed.add_field(name="現在のルーム状況", value=room_list_text, inline=False)
        embed.add_field(name="新規作成", value="下のボタンから新しい部屋を作成できます。", inline=False)
        await ctx.send(embed=embed, view=Launcher(self))
        try: await ctx.message.delete()
        except: pass

    # --- GM Commands ---
    async def check_gm(self, ctx):
        if ctx.channel.id not in self.rooms: return None
        room = self.rooms[ctx.channel.id]
        if room.settings["mode"] != "MANUAL": return None
        if room.gm_user and ctx.author.id != room.gm_user.id: return None
        return room

    # ★新規: GMがいつでも状況を確認できるコマンド
    @commands.command()
    async def wstatus(self, ctx):
        """[GM] 現在の役職・生存状況をDMで受け取る"""
        room = await self.check_gm(ctx)
        if not room: return
        
        await ctx.message.delete() # コマンドは即消し
        
        embed = discord.Embed(title="🕵️ GM用ステータス", color=0x2b2d31)
        alive_txt, dead_txt = "", ""
        for p in room.players.values():
            icon = "🟢" if p.is_alive else "💀"
            line = f"{icon} **{p.name}** : `{p.role}`\n"
            if p.is_alive: alive_txt += line
            else: dead_txt += line
        
        embed.add_field(name="生存", value=alive_txt, inline=False)
        if dead_txt: embed.add_field(name="死亡", value=dead_txt, inline=False)
        
        try: await ctx.author.send(embed=embed)
        except: await ctx.send("DMを送れませんでした。設定を確認してください。")

    @commands.command()
    async def wvote(self, ctx):
        room = await self.check_gm(ctx)
        if not room: return
        await ctx.message.delete()
        await ctx.send("🗳️ **投票フェーズ** を開始しました。")
        
        room.votes = {}
        async def manual_vote_cb(itx, tid):
            voter = room.players[itx.user.id]
            target = room.players[tid] if tid else None
            t_name = target.name if target else "放棄"
            if room.gm_user:
                try: await room.gm_user.send(f"🗳️ **{voter.name}** -> **{t_name}**")
                except: pass
            await itx.response.send_message(f"{t_name} に投票しました。", ephemeral=True)

        tasks = []
        for p in room.get_alive():
            u = self.bot.get_user(p.id)
            tasks.append(u.send("【投票】 追放する人を選んでください", view=VoteView(room, p, manual_vote_cb)))
        await asyncio.gather(*tasks)

    @commands.command()
    async def wnight(self, ctx):
        room = await self.check_gm(ctx)
        if not room: return
        await ctx.message.delete()
        await ctx.send("🌙 **夜のアクション** を要請しました。")

        async def manual_night_cb(itx, player, act, tid):
            target = room.players[tid] if tid else None
            t_name = target.name if target else "なし"
            if act == "divine":
                res = "ライコス" if target.is_wolf_side else "人間"
                await itx.response.send_message(f"判定: {t_name} は **{res}** です。", ephemeral=True)
                if room.gm_user: await room.gm_user.send(f"🔮 {player.name} が {t_name} を占い、**{res}** でした。")
            else:
                act_name = {"steal":"強奪", "guard":"護衛", "slash":"辻斬り"}.get(act, act)
                await itx.response.send_message(f"{t_name} を選択しました。", ephemeral=True)
                if room.gm_user: await room.gm_user.send(f"🌙 **{player.name}** ({player.role}) -> **{t_name}** ({act_name})")

        tasks = []
        for p in room.get_alive():
            u = self.bot.get_user(p.id)
            view = None
            msg = ""
            if p.role == ROLE_LYKOS:
                view = NightActionView(room, p, "steal", manual_night_cb)
                msg = "【強奪】 誰を狙いますか？"
            elif p.role == ROLE_TRIBBIE:
                view = NightActionView(room, p, "divine", manual_night_cb)
                msg = "【占い】 誰を占いますか？"
            elif p.role == ROLE_SIRENS:
                view = NightActionView(room, p, "guard", manual_night_cb)
                msg = "【護衛】 誰を守りますか？"
            elif p.role == ROLE_SWORDMASTER:
                view = NightActionView(room, p, "slash", manual_night_cb)
                msg = "【辻斬り】 誰を狙いますか？"
            
            if view: tasks.append(u.send(msg, view=view))
        await asyncio.gather(*tasks)

    @commands.command()
    async def wdm(self, ctx, target: discord.Member, *, message: str):
        if not await self.check_gm(ctx): return
        try:
            await target.send(embed=discord.Embed(title="📩 GMメッセージ", description=message, color=0xff00ff))
            await ctx.message.add_reaction("✅")
        except: await ctx.send("送信失敗")

    @commands.command()
    async def wsay(self, ctx, *, message: str):
        if not await self.check_gm(ctx): return
        room = self.rooms[ctx.channel.id]
        await room.channel.send(message)
        await ctx.message.delete()

    @commands.command()
    async def wkill(self, ctx, target: discord.Member):
        if not await self.check_gm(ctx): return
        room = self.rooms[ctx.channel.id]
        if target.id in room.players:
            room.players[target.id].is_alive = False
            await ctx.send(f"💀 **{target.display_name}** を死亡にしました。")

    @commands.command()
    async def wend(self, ctx):
        if ctx.channel.id in self.rooms:
            del self.rooms[ctx.channel.id]
            await ctx.send("ゲーム終了。")

    # --- Run Logic ---
    async def create_room_logic(self, itx_or_ctx):
        if isinstance(itx_or_ctx, discord.Interaction):
            channel = itx_or_ctx.channel
            user = itx_or_ctx.user
            if not itx_or_ctx.response.is_done(): await itx_or_ctx.response.send_message("作成", ephemeral=True)
        else:
            channel = itx_or_ctx.channel
            user = itx_or_ctx.author

        if channel.id in self.rooms: return
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
            if room.phase == "STARTING": break
        
        await self.run_game(channel.id)

    async def run_game(self, channel_id):
        room = self.rooms[channel_id]
        room.assign_roles()

        if room.settings["mode"] == "MANUAL":
            # ★ここが変更点: GM専用の管理ボタンを設置する
            await room.channel.send(
                f"👤 **手動GMモード** で開始します。\n"
                f"GM: {room.gm_user.mention}\n"
                "下のボタンから **GM専用ダッシュボード** を開けます。",
                view=GMControlView(room)
            )
            
            spoiler = "【役職表】\n"
            for p in room.players.values(): spoiler += f"{p.name}: {p.role}\n"
            try: await room.gm_user.send(spoiler)
            except: pass

            for p in room.players.values():
                u = self.bot.get_user(p.id)
                if u: 
                    try: await u.send(f"役職: **{p.role}**\nGMの指示をお待ちください。")
                    except: pass
            return 

        # === 以下、全自動モード (前回と同じ内容) ===
        # キュレネ用：市民リスト
        citizen_list = [p.name for p in room.players.values() if p.role == ROLE_CITIZEN]
        cit_str = ", ".join(citizen_list) if citizen_list else "なし"

        for p in room.players.values():
            user = self.bot.get_user(p.id)
            if not user: continue
            embed = discord.Embed(title=f"あなたの役割: {p.role}", color=0x2ecc71)
            if p.role == ROLE_LYKOS:
                mates = [x.name for x in room.players.values() if x.role == ROLE_LYKOS and x.id != p.id]
                embed.description = f"仲間: {', '.join(mates) if mates else 'なし'}"
            elif p.role == ROLE_CYRENE:
                embed.description = f"処刑されると敗北します。\n市民: {cit_str}"
            elif p.role == ROLE_SWORDMASTER:
                embed.description = "全員を倒し勝利を目指してください。"
            else:
                embed.description = "ライコスを見つけ出し追放してください。"
            try: await user.send(embed=embed)
            except: pass
        
        await room.channel.send("🌙 夜が訪れました。")
        day = 1
        while True:
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

            tasks = []
            for p in room.get_alive():
                u = self.bot.get_user(p.id)
                view = None
                if p.role == ROLE_LYKOS: view = NightActionView(room, p, "steal", night_cb)
                elif p.role == ROLE_TRIBBIE: view = NightActionView(room, p, "divine", night_cb)
                elif p.role == ROLE_SIRENS: view = NightActionView(room, p, "guard", night_cb)
                elif p.role == ROLE_SWORDMASTER: view = NightActionView(room, p, "slash", night_cb)
                if view: tasks.append(u.send("行動を選択してください", view=view))
            await asyncio.gather(*tasks)
            await asyncio.sleep(20)

            room.phase = "DAY"
            dead = []
            st, gt, sl = room.night_actions.get("steal"), room.night_actions.get("guard"), room.night_actions.get("slash")
            atts = set([t for t in [st, sl] if t])
            for tid in atts:
                if tid == gt: continue
                v = room.players[tid]
                if v.role == ROLE_MORDIS and v.mordis_revive_available: v.mordis_revive_available = False
                else: dead.append(v)

            msg = f"🌞 **{day}日目の朝**\n"
            dead = list(set(dead))
            if dead:
                for d in dead: d.is_alive = False
                msg += f"**{', '.join([d.name for d in dead])}** が死亡しました。"
            else: msg += "犠牲者はなし。"
            await room.channel.send(msg)

            if room.check_winner():
                await self.end_game(room, room.check_winner())
                break

            await room.channel.send(f"議論開始 ({room.settings['discussion_time']}秒)")
            await asyncio.sleep(room.settings['discussion_time'])
            
            room.votes = {}
            async def vote_cb(itx, tid):
                w = room.players[itx.user.id].vote_weight
                room.votes[tid] = room.votes.get(tid, 0) + w
                await itx.response.send_message("投票済", ephemeral=True)
            
            ts = []
            for p in room.get_alive():
                ts.append(self.bot.get_user(p.id).send("投票してください", view=VoteView(room, p, vote_cb)))
            await asyncio.gather(*ts)
            await asyncio.sleep(15)

            if room.votes:
                mv = max(room.votes.values())
                cs = [k for k,v in room.votes.items() if v == mv]
                ep = room.players[random.choice(cs)]
                ep.is_alive = False
                room.last_executed = ep
                if ep.role == ROLE_CYRENE:
                    room.cyrene_executed = True
                    await room.channel.send(f"**{ep.name}** は {ROLE_CYRENE} でした！敗北！")
                else: await room.channel.send(f"**{ep.name}** が追放されました。")
            else: await room.channel.send("投票なし。")

            if room.check_winner():
                await self.end_game(room, room.check_winner())
                break
            day += 1
        del self.rooms[channel_id]

    async def end_game(self, room, winner):
        embed = discord.Embed(title="決着", description=f"勝者: **{winner}**", color=0xf1c40f)
        det = ""
        for p in room.players.values():
            st = "生存" if p.is_alive else "死亡"
            det += f"**{p.name}**: {p.role} ({st})\n"
        embed.add_field(name="内訳", value=det)
        await room.channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(WerewolfSystem(bot))