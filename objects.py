import discord
import random

# --- 役職定義 (一般的な人狼用語へ変更) ---
ROLE_CITIZEN = "市民"
ROLE_LYKOS = "人狼"
ROLE_CAENEUS = "狂人"
ROLE_TRIBBIE = "占い師"
ROLE_CASTORICE = "霊媒師"
ROLE_SIRENS = "騎士"
ROLE_PHAINON = "暗殺者"
ROLE_SWORDMASTER = "辻斬り"
ROLE_MORDIS = "長老"
ROLE_CYRENE = "聖女"
ROLE_CERYDRA = "富豪"
ROLE_AGLAEA = "探偵"
ROLE_SAPHEL = "模倣者"
ROLE_HYANCI = "蝙蝠"

ROLE_DATA = {
    ROLE_CITIZEN: {"desc": "能力なし。推理で戦う市民。", "has_ability": False},
    ROLE_LYKOS: {"desc": "夜に襲撃可能。", "has_ability": True},
    ROLE_CAENEUS: {"desc": "人狼の勝利が目的。", "has_ability": False},
    ROLE_TRIBBIE: {"desc": "夜に一人を占い、人狼か否かを知る。", "has_ability": True},
    ROLE_CASTORICE: {"desc": "昨日の処刑者の正体(人狼か否か)を知る。", "has_ability": False},
    ROLE_SIRENS: {"desc": "夜に一人を護衛可能(自分OK、連続NG)。", "has_ability": True},
    ROLE_PHAINON: {"desc": "夜に一人を暗殺可能。ただし相手が人狼以外だと自爆する。", "has_ability": True},
    ROLE_SWORDMASTER: {"desc": "第3陣営。毎晩一人を襲撃可能。最後まで生存すれば勝利。", "has_ability": True},
    ROLE_MORDIS: {"desc": "人狼の襲撃を1回耐える。", "has_ability": False},
    ROLE_CYRENE: {"desc": "死亡すると村人陣営が敗北する(全滅)。自衛1回/バフ2回。", "has_ability": True},
    ROLE_CERYDRA: {"desc": "投票時の票数が2票分になる。", "has_ability": False},
    ROLE_AGLAEA: {"desc": "昨日の投票先を一人調査できる。", "has_ability": True},
    ROLE_SAPHEL: {"desc": "他者の能力を模倣して使用する(人狼を模倣すると死亡)。", "has_ability": True},
    ROLE_HYANCI: {"desc": "第3陣営。生存すれば勝利。供物を捧げて50%で死を回避。", "has_ability": True}
}

TEAM_AMPHOREUS = "村人陣営"
TEAM_LYKOS = "人狼陣営"
TEAM_SWORDMASTER = "辻斬り"
TEAM_HYANCI = "蝙蝠"

class Player:
    def __init__(self, member: discord.Member):
        self.member = member
        self.id = member.id
        self.name = member.display_name
        self.role = ROLE_CITIZEN
        self.is_alive = True
        self.mordis_revive_available = False
        
        # 聖女(キュレネ)用
        self.cyrene_guard_count = 1
        self.cyrene_buff_count = 2
        
        # 蝙蝠(ヒアンシー)用
        self.hyanci_ikarun_count = 2
        self.hyanci_protection_active = False
        
        # 模倣者(サフェル)用
        self.mimicking_cyrene = False 
        
        self.last_guarded_id = None
        self.vote_weight = 1

    @property
    def team(self):
        if self.role in [ROLE_LYKOS, ROLE_CAENEUS]: return TEAM_LYKOS
        if self.role == ROLE_SWORDMASTER: return TEAM_SWORDMASTER
        if self.role == ROLE_HYANCI: return TEAM_HYANCI
        return TEAM_AMPHOREUS

    @property
    def is_wolf_side(self):
        return self.role == ROLE_LYKOS

class GameRoom:
    def __init__(self, channel: discord.TextChannel):
        self.lobby_channel = channel
        self.category = None
        self.main_ch = None
        self.grave_ch = None
        self.code = "0000" # 初期値
        
        self.players = {} 
        self.spectators = {}
        self.phase = "WAITING"
        self.gm_user = None
        self.custom_settings = False

        self.settings = {
            "mode": "AUTO",
            "auto_close": True,
            "rematch": False,
            
            "lykos": 1, "caeneus": 0,
            "tribbie": 1, "castorice": 1, "sirens": 1,
            "swordmaster": 0, "phainon": 0,
            "mordis": 0, "cyrene": 0, "cerydra": 0,
            "aglaea": 0, "saphel": 0, "hyanci": 0,
            
            "discussion_time": 60
        }
        
        self.night_actions = {}
        self.votes = {}
        self.prev_votes = {}
        self.last_executed = None
        self.cyrene_executed = False
        self.vote_finished = False
        self.lobby_msg = None
        self.update_panel_callback = None

    def join(self, member):
        if member.id not in self.players:
            self.players[member.id] = Player(member)
            return True

    def leave(self, member):
        if member.id in self.players:
            del self.players[member.id]
            return True

    def get_alive(self):
        return [p for p in self.players.values() if p.is_alive]

    def reset_for_rematch(self):
        self.phase = "WAITING"
        self.night_actions = {}
        self.votes = {}
        self.prev_votes = {}
        self.last_executed = None
        self.cyrene_executed = False
        self.vote_finished = False
        # カテゴリ・チャンネルは維持
        for p in self.players.values():
            p.is_alive = True
            p.mordis_revive_available = False
            p.cyrene_guard_count = 1
            p.cyrene_buff_count = 2
            p.hyanci_ikarun_count = 2
            p.hyanci_protection_active = False
            p.mimicking_cyrene = False
            p.last_guarded_id = None
            p.vote_weight = 1
            
            # 役職ごとの再設定
            if p.role == ROLE_CERYDRA: p.vote_weight = 2
            if p.role == ROLE_MORDIS: p.mordis_revive_available = True
            if p.role == ROLE_SAPHEL: p.cyrene_buff_count = 1

    def get_recommended_settings(self, count):
        s = self.settings.copy()
        for k in list(s.keys()):
            if k not in ["mode", "auto_close", "rematch", "discussion_time"]:
                s[k] = 0
        if count <= 3: s["lykos"] = 1
        elif count == 4: s["lykos"] = 1; s["tribbie"] = 1
        elif count == 5: s["lykos"] = 1; s["tribbie"] = 1; s["sirens"] = 1
        elif count == 6: s["lykos"] = 1; s["caeneus"] = 1; s["tribbie"] = 1; s["sirens"] = 1
        elif count == 7: s["lykos"] = 2; s["tribbie"] = 1; s["sirens"] = 1; s["castorice"] = 1
        elif count == 8: s["lykos"] = 2; s["caeneus"] = 1; s["tribbie"] = 1; s["sirens"] = 1; s["castorice"] = 1
        if count >= 9: s["swordmaster"] = 1; s["phainon"] = 1; s["aglaea"] = 1
        return s

    def assign_roles(self):
        all_players = list(self.players.values())
        random.shuffle(all_players)
        
        if not self.custom_settings:
            rec = self.get_recommended_settings(len(all_players))
            for k in rec.keys():
                if k not in ["mode", "auto_close", "rematch", "discussion_time"]:
                    self.settings[k] = rec[k]

        roles = []
        s = self.settings
        roles.extend([ROLE_LYKOS]*s["lykos"])
        roles.extend([ROLE_CAENEUS]*s["caeneus"])
        roles.extend([ROLE_TRIBBIE]*s["tribbie"])
        roles.extend([ROLE_CASTORICE]*s["castorice"])
        roles.extend([ROLE_SIRENS]*s["sirens"])
        roles.extend([ROLE_SWORDMASTER]*s["swordmaster"])
        roles.extend([ROLE_PHAINON]*s["phainon"])
        roles.extend([ROLE_MORDIS]*s["mordis"])
        roles.extend([ROLE_CYRENE]*s["cyrene"])
        roles.extend([ROLE_CERYDRA]*s["cerydra"])
        roles.extend([ROLE_AGLAEA]*s["aglaea"])
        roles.extend([ROLE_SAPHEL]*s["saphel"])
        roles.extend([ROLE_HYANCI]*s["hyanci"])
        
        if len(roles) > len(all_players): roles = roles[:len(all_players)]
        else: roles.extend([ROLE_CITIZEN] * (len(all_players) - len(roles)))
        
        random.shuffle(roles)
        for p, r in zip(all_players, roles):
            p.role = r
            # 初期化
            p.mordis_revive_available = False
            p.cyrene_guard_count = 1
            p.cyrene_buff_count = 0
            p.hyanci_ikarun_count = 2
            p.hyanci_protection_active = False
            p.mimicking_cyrene = False
            p.vote_weight = 1

            # 役職別設定
            if r == ROLE_CERYDRA: p.vote_weight = 2
            if r == ROLE_MORDIS: p.mordis_revive_available = True
            
            if r == ROLE_CYRENE:
                p.cyrene_buff_count = 2
            elif r == ROLE_SAPHEL:
                p.cyrene_buff_count = 1

    def check_winner(self):
        alive = self.get_alive()
        wolves = len([p for p in alive if p.role == ROLE_LYKOS])
        sm_alive = len([p for p in alive if p.role == ROLE_SWORDMASTER]) > 0
        hy_alive = len([p for p in alive if p.role == ROLE_HYANCI]) > 0
        humans = len(alive) - wolves

        game_over = False
        winner = None

        if self.cyrene_executed:
            game_over = True
            winner = TEAM_LYKOS
        elif wolves == 0:
            game_over = True
            winner = TEAM_AMPHOREUS
        elif wolves >= humans:
            game_over = True
            winner = TEAM_LYKOS
        
        if game_over:
            final_winner = TEAM_SWORDMASTER if sm_alive else winner
            if hy_alive:
                return f"{final_winner} & {TEAM_HYANCI}"
            return final_winner
            
        return None