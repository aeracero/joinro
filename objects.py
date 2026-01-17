import discord
import random

# --- 役職定義 ---
ROLE_CITIZEN = "タイタンの末裔"
ROLE_LYKOS = "ライコス"
ROLE_CAENEUS = "カイニス"
ROLE_TRIBBIE = "トリビー"
ROLE_CASTORICE = "キャストリス"
ROLE_SIRENS = "セイレンス"
ROLE_PHAINON = "ファイノン"
ROLE_SWORDMASTER = "黒衣の剣士"
ROLE_MORDIS = "モーディス"
ROLE_CYRENE = "キュレネ"
ROLE_CERYDRA = "ケリュドラ" # ★新規追加

ROLE_DATA = {
    ROLE_CITIZEN: {"desc": "能力なし。推理で戦う市民。", "has_ability": False},
    ROLE_LYKOS: {"desc": "人狼。夜に襲撃可能。", "has_ability": True},
    ROLE_CAENEUS: {"desc": "狂人。人狼の勝利が目的。", "has_ability": False},
    ROLE_TRIBBIE: {"desc": "占い師。正体を見抜く。", "has_ability": True},
    ROLE_CASTORICE: {"desc": "霊媒師。昨日の処刑者の正体を知る。", "has_ability": False},
    ROLE_SIRENS: {"desc": "騎士。襲撃から護衛する。", "has_ability": True},
    ROLE_PHAINON: {"desc": "暗殺者。夜に一人を襲撃可能だが、味方を襲うと自分も死ぬ。", "has_ability": True}, # ★変更
    ROLE_SWORDMASTER: {"desc": "辻斬り(第3陣営)。生存勝利。", "has_ability": True},
    ROLE_MORDIS: {"desc": "1回襲撃を耐える。", "has_ability": False},
    ROLE_CYRENE: {"desc": "処刑されると村敗北。", "has_ability": False},
    ROLE_CERYDRA: {"desc": "権力者。投票が2票分になる。", "has_ability": False} # ★変更(継承)
}

TEAM_AMPHOREUS = "オンパロス陣営"
TEAM_LYKOS = "ライコス陣営"
TEAM_SWORDMASTER = "黒衣の剣士"

class Player:
    def __init__(self, member: discord.Member):
        self.member = member
        self.id = member.id
        self.name = member.display_name
        self.role = ROLE_CITIZEN
        self.is_alive = True
        self.mordis_revive_available = True
        self.vote_weight = 1

    @property
    def team(self):
        if self.role in [ROLE_LYKOS, ROLE_CAENEUS]: return TEAM_LYKOS
        if self.role == ROLE_SWORDMASTER: return TEAM_SWORDMASTER
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
        
        self.players = {} 
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
            "mordis": 0, "cyrene": 0,
            "cerydra": 0, # ★追加
            "discussion_time": 60
        }
        
        self.night_actions = {}
        self.votes = {}
        self.last_executed = None
        self.cyrene_executed = False
        self.vote_finished = False

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
        self.last_executed = None
        self.cyrene_executed = False
        self.vote_finished = False
        self.category = None
        self.main_ch = None
        self.grave_ch = None
        for p in self.players.values():
            p.is_alive = True
            p.mordis_revive_available = True
            p.vote_weight = 1

    def get_recommended_settings(self, count):
        s = self.settings.copy()
        for k in list(s.keys()):
            if k not in ["mode", "auto_close", "rematch", "discussion_time"]:
                s[k] = 0
        
        if count <= 3:
            s["lykos"] = 1
        elif count == 4:
            s["lykos"] = 1; s["tribbie"] = 1
        elif count == 5:
            s["lykos"] = 1; s["tribbie"] = 1; s["sirens"] = 1
        elif count == 6:
            s["lykos"] = 1; s["caeneus"] = 1; s["tribbie"] = 1; s["sirens"] = 1
        elif count == 7:
            s["lykos"] = 2; s["tribbie"] = 1; s["sirens"] = 1; s["castorice"] = 1
        elif count == 8:
            s["lykos"] = 2; s["caeneus"] = 1; s["tribbie"] = 1; s["sirens"] = 1; s["castorice"] = 1
        if count >= 9:
            s["swordmaster"] = 1; s["phainon"] = 1 # 特殊職を入れる
        
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
        roles.extend([ROLE_CERYDRA]*s["cerydra"]) # ★追加
        
        if len(roles) > len(all_players): roles = roles[:len(all_players)]
        else: roles.extend([ROLE_CITIZEN] * (len(all_players) - len(roles)))
        
        random.shuffle(roles)
        for p, r in zip(all_players, roles):
            p.role = r
            if r == ROLE_CERYDRA: p.vote_weight = 2 # ★ケリュドラが2票
            if r == ROLE_MORDIS: p.mordis_revive_available = True

    def check_winner(self):
        alive = self.get_alive()
        wolves = len([p for p in alive if p.role == ROLE_LYKOS])
        sm_alive = len([p for p in alive if p.role == ROLE_SWORDMASTER]) > 0
        humans = len(alive) - wolves

        if self.cyrene_executed: return TEAM_LYKOS
        
        game_over = False
        winner = None

        if wolves == 0:
            game_over = True
            winner = TEAM_AMPHOREUS
        elif wolves >= humans:
            game_over = True
            winner = TEAM_LYKOS
        
        if game_over:
            if sm_alive: return TEAM_SWORDMASTER
            return winner
            
        return None