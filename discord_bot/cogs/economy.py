"""
Système d'économie complet :
  daily, work, balance, pay, rob, slots, blackjack, shop, leaderboard
"""

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import json, os, asyncio, random
from datetime import datetime, timezone, timedelta

ECO_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'economy.json')

CURRENCY = '💰'
DAILY_AMOUNT = 500
DAILY_STREAK_BONUS = 50
WORK_COOLDOWN = 3600       # 1h
DAILY_COOLDOWN = 86400     # 24h
ROB_COOLDOWN = 7200        # 2h
ROB_SUCCESS_CHANCE = 0.45

WORK_PHRASES = [
    ("Tu as réparé des PC", 120, 280),
    ("Tu as livré des pizzas", 80, 200),
    ("Tu as streamed sur Twitch", 50, 400),
    ("Tu as vendu des NFTs", 10, 600),
    ("Tu as codé toute la nuit", 200, 350),
    ("Tu as fait du trading", 0, 500),
    ("Tu as été influenceur", 100, 250),
    ("Tu as trouvé un billet dans la rue", 5, 50),
    ("Tu as fait du babysitting", 150, 220),
    ("Tu as vendu ta config gaming", 300, 800),
]

SHOP_ITEMS = {
    'shield':     {'name': '🛡️ Bouclier',     'desc': 'Immunité au vol pendant 24h', 'price': 800},
    'multiplier': {'name': '⚡ Multiplicateur', 'desc': '+50% XP pendant 1h',         'price': 1500},
    'lucky':      {'name': '🍀 Trèfle chanceux','desc': '+10% chances au casino',    'price': 1200},
    'vip':        {'name': '👑 VIP Pass',       'desc': 'Rôle VIP sur le serveur',   'price': 5000},
    'lootbox':    {'name': '📦 Lootbox',        'desc': 'Contenu aléatoire',          'price': 300},
}

SLOT_SYMBOLS = ['🍒', '🍊', '🍇', '🍓', '💎', '7️⃣', '🎰']
SLOT_WEIGHTS  = [30,   25,   20,   15,   5,    3,    2]
SLOT_PAYOUTS  = {
    '7️⃣': 50, '🎰': 30, '💎': 20,
    '🍓': 10, '🍇': 8,  '🍊': 5, '🍒': 3,
}


# ─────────────────── database helpers ───────────────────

def _load():
    os.makedirs(os.path.dirname(ECO_PATH), exist_ok=True)
    if os.path.exists(ECO_PATH):
        with open(ECO_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save(data):
    os.makedirs(os.path.dirname(ECO_PATH), exist_ok=True)
    with open(ECO_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def _user(data, gid, uid):
    gid, uid = str(gid), str(uid)
    data.setdefault(gid, {})
    data[gid].setdefault(uid, {
        'balance': 0, 'bank': 0,
        'daily_last': None, 'daily_streak': 0,
        'work_last': None, 'rob_last': None,
        'inventory': [], 'shield_until': None,
        'total_earned': 0,
    })
    return data[gid][uid]

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _parse_dt(s):
    if not s:
        return None
    return datetime.fromisoformat(s)

def _cooldown_left(last_iso, cooldown_sec):
    if not last_iso:
        return 0
    elapsed = (datetime.now(timezone.utc) - _parse_dt(last_iso)).total_seconds()
    return max(0, cooldown_sec - elapsed)

def _fmt_cd(secs):
    secs = int(secs)
    if secs < 60:
        return f'{secs}s'
    m, s = divmod(secs, 60)
    if m < 60:
        return f'{m}m {s}s'
    h, m = divmod(m, 60)
    return f'{h}h {m}m {s}s'


# ──────────────────── blackjack game ────────────────────

CARDS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
SUITS = ['♠', '♥', '♦', '♣']

def _new_deck():
    return [(c, s) for c in CARDS for s in SUITS]

def _card_value(card):
    v = card[0]
    if v in ('J', 'Q', 'K'):
        return 10
    if v == 'A':
        return 11
    return int(v)

def _hand_value(hand):
    val = sum(_card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[0] == 'A')
    while val > 21 and aces:
        val -= 10
        aces -= 1
    return val

def _fmt_hand(hand):
    return ' '.join(f'`{c[0]}{c[1]}`' for c in hand)


class BlackjackView(View):
    def __init__(self, user_id, bet, player_hand, dealer_hand, deck, eco_data, gid):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bet = bet
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.deck = deck
        self.eco_data = eco_data
        self.gid = gid
        self.finished = False

    def _make_embed(self, title='🃏 Blackjack', reveal_dealer=False):
        dealer_show = _fmt_hand(self.dealer_hand) if reveal_dealer else f'`{self.dealer_hand[0][0]}{self.dealer_hand[0][1]}` `🂠`'
        pv = _hand_value(self.player_hand)
        dv = _hand_value(self.dealer_hand) if reveal_dealer else '?'
        color = discord.Color.gold()
        if reveal_dealer:
            dv2 = _hand_value(self.dealer_hand)
            pv2 = _hand_value(self.player_hand)
            if pv2 > 21:
                color = discord.Color.red()
            elif dv2 > 21 or pv2 > dv2:
                color = discord.Color.green()
            elif pv2 == dv2:
                color = discord.Color.yellow()
            else:
                color = discord.Color.red()

        e = discord.Embed(title=title, color=color)
        e.add_field(name=f'🤖 Croupier ({dv})', value=dealer_show, inline=False)
        e.add_field(name=f'👤 Toi ({pv})', value=_fmt_hand(self.player_hand), inline=False)
        e.set_footer(text=f'Mise : {self.bet} {CURRENCY}')
        return e

    async def _end(self, interaction, result):
        self.finished = True
        for child in self.children:
            child.disabled = True

        data = _load()
        u = _user(data, self.gid, self.user_id)

        if result == 'win':
            gain = self.bet * 2
            u['balance'] += gain
            u['total_earned'] += gain
            msg = f'✅ Tu gagnes **+{gain} {CURRENCY}** !'
        elif result == 'blackjack':
            gain = int(self.bet * 2.5)
            u['balance'] += gain
            u['total_earned'] += gain
            msg = f'🃏 BLACKJACK ! Tu gagnes **+{gain} {CURRENCY}** !'
        elif result == 'push':
            u['balance'] += self.bet
            msg = f'🤝 Égalité ! Tu récupères ta mise de **{self.bet} {CURRENCY}**.'
        else:
            msg = f'❌ Tu perds **{self.bet} {CURRENCY}**...'

        _save(data)
        e = self._make_embed(reveal_dealer=True)
        e.description = msg
        await interaction.response.edit_message(embed=e, view=self)

    @discord.ui.button(label='Tirer 🃏', style=discord.ButtonStyle.green, custom_id='bj:hit')
    async def hit(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('Ce n\'est pas ton jeu !', ephemeral=True)
            return
        card = self.deck.pop()
        self.player_hand.append(card)
        pv = _hand_value(self.player_hand)
        if pv > 21:
            await self._end(interaction, 'lose')
        elif pv == 21:
            await self._stand_logic(interaction)
        else:
            await interaction.response.edit_message(embed=self._make_embed(), view=self)

    @discord.ui.button(label='Rester ✋', style=discord.ButtonStyle.red, custom_id='bj:stand')
    async def stand(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('Ce n\'est pas ton jeu !', ephemeral=True)
            return
        await self._stand_logic(interaction)

    async def _stand_logic(self, interaction):
        while _hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        pv = _hand_value(self.player_hand)
        dv = _hand_value(self.dealer_hand)
        if dv > 21 or pv > dv:
            result = 'blackjack' if pv == 21 and len(self.player_hand) == 2 else 'win'
        elif pv == dv:
            result = 'push'
        else:
            result = 'lose'
        await self._end(interaction, result)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ─────────────────────────── cog ────────────────────────

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /balance ───────────────────────────────────────
    @app_commands.command(name='balance', description='Affiche ton solde ou celui d\'un membre')
    @app_commands.describe(membre='Le membre (toi par défaut)')
    async def balance(self, interaction: discord.Interaction, membre: discord.Member = None):
        t = membre or interaction.user
        data = _load()
        u = _user(data, interaction.guild.id, t.id)
        embed = discord.Embed(
            title=f'💰 Solde de {t.display_name}',
            color=discord.Color.gold(),
        )
        embed.add_field(name='Portefeuille', value=f'`{u["balance"]:,} {CURRENCY}`', inline=True)
        embed.add_field(name='Banque', value=f'`{u["bank"]:,} {CURRENCY}`', inline=True)
        embed.add_field(name='Total', value=f'`{u["balance"] + u["bank"]:,} {CURRENCY}`', inline=True)
        embed.add_field(name='Gains totaux', value=f'`{u["total_earned"]:,} {CURRENCY}`', inline=True)
        embed.set_thumbnail(url=t.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    # ── /daily ─────────────────────────────────────────
    @app_commands.command(name='daily', description='Réclame ta récompense journalière')
    async def daily(self, interaction: discord.Interaction):
        data = _load()
        u = _user(data, interaction.guild.id, interaction.user.id)
        cd = _cooldown_left(u['daily_last'], DAILY_COOLDOWN)
        if cd > 0:
            await interaction.response.send_message(
                f'⏳ Daily dans **{_fmt_cd(cd)}**.', ephemeral=True
            )
            return

        last = _parse_dt(u['daily_last'])
        now = datetime.now(timezone.utc)
        if last and (now - last).total_seconds() < 172800:
            u['daily_streak'] = u.get('daily_streak', 0) + 1
        else:
            u['daily_streak'] = 1

        streak = u['daily_streak']
        bonus = min(streak - 1, 30) * DAILY_STREAK_BONUS
        total = DAILY_AMOUNT + bonus

        u['balance'] += total
        u['total_earned'] += total
        u['daily_last'] = _now_iso()
        _save(data)

        embed = discord.Embed(
            title='🎁 Daily réclamé !',
            color=discord.Color.green(),
        )
        embed.add_field(name='Récompense', value=f'`+{DAILY_AMOUNT} {CURRENCY}`', inline=True)
        if bonus:
            embed.add_field(name=f'Bonus streak ×{streak}', value=f'`+{bonus} {CURRENCY}`', inline=True)
        embed.add_field(name='Total', value=f'`+{total} {CURRENCY}`', inline=True)
        embed.add_field(name='🔥 Streak', value=f'`{streak} jour(s)`', inline=True)
        embed.add_field(name='Nouveau solde', value=f'`{u["balance"]:,} {CURRENCY}`', inline=True)
        embed.set_footer(text='Reviens demain pour continuer ton streak !')
        await interaction.response.send_message(embed=embed)

    # ── /work ──────────────────────────────────────────
    @app_commands.command(name='work', description='Travaille pour gagner des coins (1h cooldown)')
    async def work(self, interaction: discord.Interaction):
        data = _load()
        u = _user(data, interaction.guild.id, interaction.user.id)
        cd = _cooldown_left(u['work_last'], WORK_COOLDOWN)
        if cd > 0:
            await interaction.response.send_message(f'⏳ Tu peux retravailler dans **{_fmt_cd(cd)}**.', ephemeral=True)
            return

        phrase, min_earn, max_earn = random.choice(WORK_PHRASES)
        earned = random.randint(min_earn, max_earn)
        u['balance'] += earned
        u['total_earned'] += earned
        u['work_last'] = _now_iso()
        _save(data)

        embed = discord.Embed(
            description=f'💼 {phrase} et tu as gagné **{earned} {CURRENCY}** !',
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f'Solde : {u["balance"]:,} {CURRENCY}')
        await interaction.response.send_message(embed=embed)

    # ── /pay ───────────────────────────────────────────
    @app_commands.command(name='pay', description='Transfère des coins à un membre')
    @app_commands.describe(membre='Le destinataire', montant='Montant à transférer')
    async def pay(self, interaction: discord.Interaction, membre: discord.Member, montant: int):
        if montant <= 0:
            await interaction.response.send_message('❌ Montant invalide.', ephemeral=True)
            return
        if membre.id == interaction.user.id:
            await interaction.response.send_message('❌ Tu ne peux pas te payer toi-même.', ephemeral=True)
            return

        data = _load()
        sender = _user(data, interaction.guild.id, interaction.user.id)
        receiver = _user(data, interaction.guild.id, membre.id)

        if sender['balance'] < montant:
            await interaction.response.send_message(
                f'❌ Solde insuffisant (`{sender["balance"]:,} {CURRENCY}`).', ephemeral=True
            )
            return

        sender['balance'] -= montant
        receiver['balance'] += montant
        _save(data)

        embed = discord.Embed(
            description=f'✅ **{interaction.user.mention}** → **{membre.mention}** : `{montant:,} {CURRENCY}`',
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    # ── /rob ───────────────────────────────────────────
    @app_commands.command(name='rob', description='Tente de voler un membre (risqué !)')
    @app_commands.describe(membre='La victime')
    async def rob(self, interaction: discord.Interaction, membre: discord.Member):
        if membre.id == interaction.user.id:
            await interaction.response.send_message('❌ Tu ne peux pas te voler toi-même.', ephemeral=True)
            return

        data = _load()
        robber = _user(data, interaction.guild.id, interaction.user.id)
        victim = _user(data, interaction.guild.id, membre.id)

        cd = _cooldown_left(robber['rob_last'], ROB_COOLDOWN)
        if cd > 0:
            await interaction.response.send_message(f'⏳ Tu peux revoler dans **{_fmt_cd(cd)}**.', ephemeral=True)
            return

        if victim['balance'] < 100:
            await interaction.response.send_message('❌ Cette personne est trop pauvre à voler.', ephemeral=True)
            return

        # Check shield
        shield = victim.get('shield_until')
        if shield and datetime.fromisoformat(shield) > datetime.now(timezone.utc):
            await interaction.response.send_message(
                f'🛡️ {membre.mention} a un bouclier actif ! Tu ne peux pas le voler.', ephemeral=True
            )
            return

        robber['rob_last'] = _now_iso()

        if random.random() < ROB_SUCCESS_CHANCE:
            stolen = random.randint(
                int(victim['balance'] * 0.1),
                int(victim['balance'] * 0.4),
            )
            robber['balance'] += stolen
            robber['total_earned'] += stolen
            victim['balance'] -= stolen
            _save(data)
            embed = discord.Embed(
                title='🦹 Vol réussi !',
                description=f'Tu as volé **{stolen:,} {CURRENCY}** à {membre.mention} !',
                color=discord.Color.red(),
            )
        else:
            fine = random.randint(50, 300)
            fine = min(fine, robber['balance'])
            robber['balance'] -= fine
            _save(data)
            embed = discord.Embed(
                title='🚔 Arrêté !',
                description=f'Tu t\'es fait prendre ! Amende de **{fine:,} {CURRENCY}**.',
                color=discord.Color.orange(),
            )

        await interaction.response.send_message(embed=embed)

    # ── /slots ─────────────────────────────────────────
    @app_commands.command(name='slots', description='Lance la machine à sous')
    @app_commands.describe(mise='Montant à miser')
    async def slots(self, interaction: discord.Interaction, mise: int):
        if mise <= 0:
            await interaction.response.send_message('❌ Mise invalide.', ephemeral=True)
            return

        data = _load()
        u = _user(data, interaction.guild.id, interaction.user.id)
        if u['balance'] < mise:
            await interaction.response.send_message(
                f'❌ Solde insuffisant (`{u["balance"]:,} {CURRENCY}`).', ephemeral=True
            )
            return

        u['balance'] -= mise
        _save(data)

        # Animated spin
        await interaction.response.defer()
        frames = []
        for _ in range(3):
            row = [random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS)[0] for _ in range(3)]
            frames.append(row)

        result = frames[-1]
        spinning_embed = discord.Embed(
            title='🎰 Machine à sous — En cours...',
            description='`❓` | `❓` | `❓`',
            color=discord.Color.yellow(),
        )
        msg = await interaction.followup.send(embed=spinning_embed)

        await asyncio.sleep(0.8)
        e2 = discord.Embed(
            title='🎰 Machine à sous',
            description=f'`{result[0]}` | `❓` | `❓`',
            color=discord.Color.yellow(),
        )
        await msg.edit(embed=e2)
        await asyncio.sleep(0.6)

        e3 = discord.Embed(
            title='🎰 Machine à sous',
            description=f'`{result[0]}` | `{result[1]}` | `❓`',
            color=discord.Color.yellow(),
        )
        await msg.edit(embed=e3)
        await asyncio.sleep(0.5)

        # Calculate win
        data = _load()
        u = _user(data, interaction.guild.id, interaction.user.id)

        if result[0] == result[1] == result[2]:
            mult = SLOT_PAYOUTS.get(result[0], 3)
            gain = mise * mult
            u['balance'] += gain
            u['total_earned'] += gain
            color = discord.Color.gold()
            outcome = f'🎉 **JACKPOT ×{mult} !** Tu gagnes **+{gain:,} {CURRENCY}** !'
        elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            gain = int(mise * 1.5)
            u['balance'] += gain
            u['total_earned'] += gain
            color = discord.Color.green()
            outcome = f'✅ **Paire !** Tu gagnes **+{gain:,} {CURRENCY}** !'
        else:
            color = discord.Color.red()
            outcome = f'❌ **Perdu.** Tu perds **{mise:,} {CURRENCY}`.**'

        _save(data)
        final = discord.Embed(
            title='🎰 Machine à sous',
            description=f'`{result[0]}` | `{result[1]}` | `{result[2]}`\n\n{outcome}',
            color=color,
        )
        final.set_footer(text=f'Solde : {u["balance"]:,} {CURRENCY}')
        await msg.edit(embed=final)

    # ── /blackjack ─────────────────────────────────────
    @app_commands.command(name='blackjack', description='Joue au blackjack contre le croupier')
    @app_commands.describe(mise='Montant à miser')
    async def blackjack(self, interaction: discord.Interaction, mise: int):
        if mise <= 0:
            await interaction.response.send_message('❌ Mise invalide.', ephemeral=True)
            return

        data = _load()
        u = _user(data, interaction.guild.id, interaction.user.id)
        if u['balance'] < mise:
            await interaction.response.send_message(
                f'❌ Solde insuffisant (`{u["balance"]:,} {CURRENCY}`).', ephemeral=True
            )
            return

        u['balance'] -= mise
        _save(data)

        deck = _new_deck()
        random.shuffle(deck)
        player = [deck.pop(), deck.pop()]
        dealer = [deck.pop(), deck.pop()]

        view = BlackjackView(interaction.user.id, mise, player, dealer, deck, data, interaction.guild.id)
        pv = _hand_value(player)

        if pv == 21:
            await interaction.response.send_message('🃏 Checking...')
            await view._end(interaction, 'blackjack')
            return

        embed = view._make_embed()
        await interaction.response.send_message(embed=embed, view=view)

    # ── /shop ──────────────────────────────────────────
    @app_commands.command(name='shop', description='Affiche la boutique')
    async def shop(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title='🛒 Boutique',
            description='Utilise `/buy <item>` pour acheter.',
            color=discord.Color.blurple(),
        )
        for key, item in SHOP_ITEMS.items():
            embed.add_field(
                name=f'{item["name"]} — `{item["price"]:,} {CURRENCY}`',
                value=f'`/buy {key}` · {item["desc"]}',
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    # ── /buy ───────────────────────────────────────────
    @app_commands.command(name='buy', description='Achète un item du shop')
    @app_commands.describe(item='Nom de l\'item (shield, multiplier, lucky, vip, lootbox)')
    async def buy(self, interaction: discord.Interaction, item: str):
        item = item.lower()
        if item not in SHOP_ITEMS:
            await interaction.response.send_message(
                f'❌ Item inconnu. Items disponibles : `{"`, `".join(SHOP_ITEMS)}`', ephemeral=True
            )
            return

        shop_item = SHOP_ITEMS[item]
        data = _load()
        u = _user(data, interaction.guild.id, interaction.user.id)

        if u['balance'] < shop_item['price']:
            await interaction.response.send_message(
                f'❌ Il te manque `{shop_item["price"] - u["balance"]:,} {CURRENCY}`.', ephemeral=True
            )
            return

        u['balance'] -= shop_item['price']

        result_msg = ''
        if item == 'shield':
            u['shield_until'] = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            result_msg = '🛡️ Tu es protégé du vol pendant **24h** !'
        elif item == 'lootbox':
            prizes = [50, 100, 200, 500, 1000, 2000, 5000]
            weights = [30, 25, 20, 12, 8, 4, 1]
            prize = random.choices(prizes, weights=weights)[0]
            u['balance'] += prize
            u['total_earned'] += prize
            result_msg = f'📦 La lootbox contenait **{prize} {CURRENCY}** !'
        else:
            u['inventory'].append(item)
            result_msg = f'{shop_item["name"]} ajouté à ton inventaire !'

        _save(data)
        embed = discord.Embed(
            title=f'✅ Achat : {shop_item["name"]}',
            description=result_msg,
            color=discord.Color.green(),
        )
        embed.set_footer(text=f'Solde restant : {u["balance"]:,} {CURRENCY}')
        await interaction.response.send_message(embed=embed)

    # ── /inventory ─────────────────────────────────────
    @app_commands.command(name='inventory', description='Affiche ton inventaire')
    async def inventory(self, interaction: discord.Interaction):
        data = _load()
        u = _user(data, interaction.guild.id, interaction.user.id)
        inv = u.get('inventory', [])
        if not inv:
            await interaction.response.send_message('🎒 Ton inventaire est vide.', ephemeral=True)
            return

        counts = {}
        for it in inv:
            counts[it] = counts.get(it, 0) + 1

        embed = discord.Embed(title=f'🎒 Inventaire de {interaction.user.display_name}', color=discord.Color.blurple())
        for key, count in counts.items():
            shop_item = SHOP_ITEMS.get(key, {'name': key, 'desc': ''})
            embed.add_field(name=f'{shop_item["name"]} ×{count}', value=shop_item['desc'], inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /leaderboard ───────────────────────────────────
    @app_commands.command(name='leaderboard', description='Top 10 des plus riches du serveur')
    async def leaderboard(self, interaction: discord.Interaction):
        data = _load()
        gid = str(interaction.guild.id)
        guild_data = data.get(gid, {})

        ranking = []
        for uid, udata in guild_data.items():
            total = udata.get('balance', 0) + udata.get('bank', 0)
            ranking.append((uid, total))

        ranking.sort(key=lambda x: x[1], reverse=True)

        embed = discord.Embed(
            title='🏆 Classement Économie',
            color=discord.Color.gold(),
        )
        medals = ['🥇', '🥈', '🥉'] + ['4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']

        for i, (uid, total) in enumerate(ranking[:10]):
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f'Utilisateur ({uid})'
            embed.add_field(
                name=f'{medals[i]} {name}',
                value=f'`{total:,} {CURRENCY}`',
                inline=False,
            )

        if not ranking:
            embed.description = 'Aucune donnée.'
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Economy(bot))
