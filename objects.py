# objects.py
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

# --- 陣営 ---
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
        self.lobby_channel = channel # 元の募集場所
        self.category = None         # ゲーム用カテゴリ
        self.main_ch = None          # 議論チャンネル
        self.grave_ch = None         # 墓場チャンネル
        
        self.players = {} 
        self.phase = "WAITING"
        self.gm_user = None
        
        self.settings = {
            "mode": "AUTO",
            "lykos": 1, "caeneus": 0,
            "tribbie": 1, "castorice": 1, "sirens": 1,
            "swordmaster": 0, "phainon": 0,
            "mordis": 0, "cyrene": 0,
            "discussion_time": 60
        }
        
        self.night_actions = {}
        self.votes = {}
        self.last_executed = None
        self.cyrene_executed = False

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

    def assign_roles(self):
        all_players = list(self.players.values())
        random.shuffle(all_players)
        
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
        
        if len(roles) > len(all_players): roles = roles[:len(all_players)]
        else: roles.extend([ROLE_CITIZEN] * (len(all_players) - len(roles)))
        
        random.shuffle(roles)
        for p, r in zip(all_players, roles):
            p.role = r
            if r == ROLE_PHAINON: p.vote_weight = 2
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