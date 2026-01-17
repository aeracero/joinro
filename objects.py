# objects.py
import discord
import random

# --- 役職定数 ---
ROLE_VILLAGER = "村人"
ROLE_WEREWOLF = "人狼"
ROLE_SEER = "占い師"
ROLE_MEDIUM = "霊媒師"
ROLE_BODYGUARD = "狩人"
ROLE_MADMAN = "狂人"
ROLE_FOX = "妖狐"     # ★追加: 占われると死ぬ。最後まで生き残れば単独勝利
ROLE_MASON = "共有者" # ★追加: 相方が誰かわかる

# --- 陣営定数 ---
TEAM_VILLAGER = "村人陣営"
TEAM_WEREWOLF = "人狼陣営"
TEAM_FOX = "妖狐陣営" # ★追加

class Player:
    def __init__(self, member: discord.Member):
        self.member = member
        self.id = member.id
        self.name = member.display_name
        self.role = ROLE_VILLAGER
        self.is_alive = True
        self.cursed_death = False # 占いによる呪殺フラグ

    @property
    def is_wolf_side(self):
        """占い・霊媒結果での判定（黒か白か）"""
        # 妖狐は「白（人間）」判定が出るが、占われると死ぬ
        return self.role == ROLE_WEREWOLF

class GameRoom:
    def __init__(self, channel: discord.TextChannel):
        self.channel = channel
        self.players = {} 
        self.phase = "WAITING"
        
        # 設定（デフォルト値）
        self.settings = {
            "werewolf": 1,
            "seer": 1,
            "medium": 1,
            "bodyguard": 1,
            "madman": 0,
            "fox": 0,   # ★追加
            "mason": 0, # ★追加
            "discussion_time": 60
        }
        
        self.night_actions = {}
        self.votes = {}
        self.last_executed = None

    def join(self, member: discord.Member):
        if member.id not in self.players:
            self.players[member.id] = Player(member)
            return True
        return False

    def leave(self, member: discord.Member):
        if member.id in self.players:
            del self.players[member.id]
            return True
        return False

    def get_alive(self):
        return [p for p in self.players.values() if p.is_alive]

    def assign_roles(self):
        all_players = list(self.players.values())
        random.shuffle(all_players)
        
        roles = []
        roles.extend([ROLE_WEREWOLF] * self.settings["werewolf"])
        roles.extend([ROLE_SEER] * self.settings["seer"])
        roles.extend([ROLE_MEDIUM] * self.settings["medium"])
        roles.extend([ROLE_BODYGUARD] * self.settings["bodyguard"])
        roles.extend([ROLE_MADMAN] * self.settings["madman"])
        roles.extend([ROLE_FOX] * self.settings["fox"])
        
        # 共有者は必ず2人ペア（または0人）にするのが一般的だが、設定数分入れる
        roles.extend([ROLE_MASON] * self.settings["mason"])

        # 人数調整
        if len(roles) > len(all_players):
            roles = roles[:len(all_players)]
        else:
            roles.extend([ROLE_VILLAGER] * (len(all_players) - len(roles)))
        
        random.shuffle(roles)
        for p, r in zip(all_players, roles):
            p.role = r

    def check_winner(self):
        """勝利判定ロジック（妖狐優先）"""
        alive = self.get_alive()
        wolves = len([p for p in alive if p.role == ROLE_WEREWOLF])
        foxes = len([p for p in alive if p.role == ROLE_FOX])
        humans = len(alive) - wolves - foxes # 妖狐はカウントから除外

        # 1. 村人 vs 人狼 の決着がついたか？
        game_over = False
        winner_team = None

        if wolves == 0:
            game_over = True
            winner_team = TEAM_VILLAGER
        elif wolves >= (humans + foxes): # 妖狐も頭数には入る
            game_over = True
            winner_team = TEAM_WEREWOLF

        # 2. 決着がついた時、妖狐が生きていれば妖狐の勝ち
        if game_over:
            if foxes > 0:
                return TEAM_FOX
            return winner_team
        
        return None