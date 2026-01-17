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

# --- 役職データ (説明文と能力の有無) ---
ROLE_DATA = {
    ROLE_CITIZEN: {
        "desc": "特別な能力を持たない一般の英雄です。\n議論と推理でライコスを追い詰めましょう。",
        "has_ability": False
    },
    ROLE_LYKOS: {
        "desc": "人狼陣営です。夜に他のプレイヤーの火種を奪い（襲撃）、排除することができます。\n正体がバレないように振る舞いましょう。",
        "has_ability": True
    },
    ROLE_CAENEUS: {
        "desc": "ライコスに加担する狂人です。特別な能力はありませんが、ライコス陣営が勝利すればあなたも勝利となります。",
        "has_ability": False
    },
    ROLE_TRIBBIE: {
        "desc": "占い師です。夜に一人を選び、その人物が「人間」か「ライコス」かを見抜くことができます。",
        "has_ability": True
    },
    ROLE_CASTORICE: {
        "desc": "霊媒師です。朝、前日に処刑された人物が「人間」だったか「ライコス」だったかを知ることができます。",
        "has_ability": False
    },
    ROLE_SIRENS: {
        "desc": "騎士です。夜に一人を選び、ライコスの襲撃から護衛することができます。\n自分自身は守れません。",
        "has_ability": True
    },
    ROLE_PHAINON: {
        "desc": "あなたの投票は「2票分」としてカウントされます。\nこの能力は自動的に適用されます。",
        "has_ability": False
    },
    ROLE_SWORDMASTER: {
        "desc": "第3陣営の殺人鬼です。夜に辻斬りを行い、プレイヤーを減らします。\n最後まで生き残れば単独勝利となります。",
        "has_ability": True
    },
    ROLE_MORDIS: {
        "desc": "一度だけ襲撃されても耐えることができます（自動発動）。\n復活能力を持っていることは誰にもバレません。",
        "has_ability": False
    },
    ROLE_CYRENE: {
        "desc": "あなたが処刑されると、禁忌により村人側（オンパロス陣営）が即敗北します。\n疑われないように立ち回りましょう。",
        "has_ability": False
    }
}

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
        self.lobby_channel = channel
        self.category = None
        self.main_ch = None
        self.grave_ch = None
        
        self.players = {} 
        self.phase = "WAITING"
        self.gm_user = None
        
        # ★追加: カスタム設定フラグ
        self.custom_settings = False

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

    # ★人数に応じた推奨配役を返す
    def get_recommended_settings(self, count):
        s = self.settings.copy()
        # リセット
        for k in ["lykos", "caeneus", "tribbie", "castorice", "sirens", "swordmaster", "phainon", "mordis", "cyrene"]:
            s[k] = 0
        
        # 配役ロジック (一般例)
        if count <= 3:
            s["lykos"] = 1 # 3人以下: 狼1 (テスト用)
        elif count == 4:
            s["lykos"] = 1; s["tribbie"] = 1 # 狼1, 占1
        elif count == 5:
            s["lykos"] = 1; s["tribbie"] = 1; s["sirens"] = 1 # 狼1, 占1, 騎1
        elif count == 6:
            s["lykos"] = 1; s["caeneus"] = 1; s["tribbie"] = 1; s["sirens"] = 1 # 狼1, 狂1, 占1, 騎1
        elif count == 7:
            s["lykos"] = 2; s["tribbie"] = 1; s["sirens"] = 1; s["castorice"] = 1 # 狼2, 占1, 霊1, 騎1
        elif count == 8:
            s["lykos"] = 2; s["caeneus"] = 1; s["tribbie"] = 1; s["sirens"] = 1; s["castorice"] = 1
        elif count >= 9:
            # 9人以上: 狼2, 狂1, 占1, 霊1, 騎1, 剣士1 (特殊役職投入)
            s["lykos"] = 2; s["caeneus"] = 1; s["tribbie"] = 1; s["sirens"] = 1; s["castorice"] = 1; s["swordmaster"] = 1
        
        return s

    def assign_roles(self):
        all_players = list(self.players.values())
        random.shuffle(all_players)
        
        # ★設定をいじってない場合、人数に合わせて自動調整
        if not self.custom_settings:
            rec = self.get_recommended_settings(len(all_players))
            # modeとtimeは維持して役職数だけ上書き
            for k, v in rec.items():
                self.settings[k] = v

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