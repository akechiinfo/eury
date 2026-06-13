"""
Commandes fun : 8ball, rps, meme Reddit, trivia, blague, vrai ou faux, dé, pile/face
"""

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import random, asyncio, json, html
import aiohttp

EIGHT_BALL = [
    ('✅', 'C\'est certain.', discord.Color.green()),
    ('✅', 'Décidément oui.', discord.Color.green()),
    ('✅', 'Sans aucun doute.', discord.Color.green()),
    ('✅', 'Oui, absolument.', discord.Color.green()),
    ('✅', 'Tu peux compter dessus.', discord.Color.green()),
    ('✅', 'Comme je le vois, oui.', discord.Color.green()),
    ('✅', 'Fort probablement.', discord.Color.green()),
    ('🤔', 'Réessaie plus tard.', discord.Color.yellow()),
    ('🤔', 'Difficile à prédire maintenant.', discord.Color.yellow()),
    ('🤔', 'Concentre-toi et redemande.', discord.Color.yellow()),
    ('🤔', 'Ne compte pas dessus.', discord.Color.yellow()),
    ('❌', 'Ma réponse est non.', discord.Color.red()),
    ('❌', 'Mes sources disent non.', discord.Color.red()),
    ('❌', 'Les perspectives ne sont pas bonnes.', discord.Color.red()),
    ('❌', 'Très peu probable.', discord.Color.red()),
]

RPS_CHOICES = {'🪨': 'pierre', '📄': 'feuille', '✂️': 'ciseaux'}
RPS_WIN = {'🪨': '✂️', '📄': '🪨', '✂️': '📄'}

JOKES = [
    "Pourquoi les plongeurs plongent-ils toujours en arrière et jamais en avant ? Parce que sinon ils tomberaient dans le bateau.",
    "C'est l'histoire d'un mec qui se noie dans du lait en criant : Au lait ! Au lait !",
    "Comment appelle-t-on un chat tombé dans un pot de peinture ? Un chat-peint.",
    "Qu'est-ce qu'un canif ? Un petit fien.",
    "Pourquoi l'épouvantail a-t-il reçu un prix ? Parce qu'il était exceptionnel dans son domaine.",
    "Qu'est-ce qu'un crocodile qui surveille des valises ? Un bag-arre.",
    "Comment s'appelle un chat qui mange des citrons ? Un chat-grin.",
    "Que dit un électricien quand il réussit son travail ? Cou-rant !",
    "Pourquoi les ours polaires ne mangent-ils pas de pingouins ? Parce qu'ils n'arrivent pas à enlever l'emballage.",
    "Pourquoi les mathématiciens ont-ils peur des négatifs ? Parce qu'ils ne les voient pas venir.",
]

SUBREDDITS = ['dankmemes', 'memes', 'me_irl', 'AdviceAnimals', 'ProgrammerHumor']

FACTS = [
    "Les pieuvres ont trois cœurs.",
    "Une journée sur Vénus est plus longue qu'une année sur Vénus.",
    "Les fourmis peuvent soulever 50 fois leur propre poids.",
    "Le miel ne se périme jamais. On en a trouvé dans les pyramides qui était encore bon.",
    "Il y a plus d'étoiles dans l'univers que de grains de sable sur Terre.",
    "Les dauphins ont des noms pour s'appeler entre eux.",
    "Les chats ont plus de 100 sons vocaux, les chiens en ont seulement 10.",
    "La Tour Eiffel grandit de 15 cm en été à cause de la dilatation thermique.",
    "Les flamants roses sont blancs à la naissance.",
    "Un escargot peut dormir 3 ans d'affilée.",
]

WOULD_YOU = [
    ("Devenir invisible", "Pouvoir voler"),
    ("Manger de la pizza toute ta vie", "Ne jamais manger de pizza"),
    ("Parler à tous les animaux", "Parler toutes les langues"),
    ("Voyager dans le passé", "Voyager dans le futur"),
    ("Avoir 10M€ maintenant", "Avoir 1000€/mois à vie"),
    ("Ne jamais dormir", "Ne jamais manger"),
    ("Avoir une mémoire parfaite", "Pouvoir tout oublier sur commande"),
    ("Jouer dans un film", "Écrire un livre bestseller"),
    ("Rencontrer ton idole", "Devenir célèbre toi-même"),
    ("Vivre 150 ans en bonne santé", "Vivre 80 ans avec tout ce que tu veux"),
]


class RPSView(View):
    def __init__(self, challenger_id: int):
        super().__init__(timeout=30)
        self.challenger_id = challenger_id
        self.result = None

    async def _play(self, interaction: discord.Interaction, user_choice: str):
        bot_choice = random.choice(list(RPS_CHOICES.keys()))
        for child in self.children:
            child.disabled = True

        if user_choice == bot_choice:
            result = '🤝 Égalité !'
            color = discord.Color.yellow()
        elif RPS_WIN[user_choice] == bot_choice:
            result = '✅ Tu gagnes !'
            color = discord.Color.green()
        else:
            result = '❌ Tu perds !'
            color = discord.Color.red()

        embed = discord.Embed(title='🪨📄✂️ Pierre-Feuille-Ciseaux', color=color)
        embed.add_field(name='Ton choix', value=f'{user_choice} {RPS_CHOICES[user_choice]}', inline=True)
        embed.add_field(name='Bot', value=f'{bot_choice} {RPS_CHOICES[bot_choice]}', inline=True)
        embed.add_field(name='Résultat', value=result, inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji='🪨', style=discord.ButtonStyle.grey, custom_id='rps:rock')
    async def rock(self, i, b):
        if i.user.id != self.challenger_id:
            return await i.response.send_message('Pas ton jeu !', ephemeral=True)
        await self._play(i, '🪨')

    @discord.ui.button(emoji='📄', style=discord.ButtonStyle.grey, custom_id='rps:paper')
    async def paper(self, i, b):
        if i.user.id != self.challenger_id:
            return await i.response.send_message('Pas ton jeu !', ephemeral=True)
        await self._play(i, '📄')

    @discord.ui.button(emoji='✂️', style=discord.ButtonStyle.grey, custom_id='rps:scissors')
    async def scissors(self, i, b):
        if i.user.id != self.challenger_id:
            return await i.response.send_message('Pas ton jeu !', ephemeral=True)
        await self._play(i, '✂️')


class TriviaView(View):
    def __init__(self, correct: str, all_answers: list, user_id: int):
        super().__init__(timeout=20)
        self.correct = correct
        self.user_id = user_id
        self.answered = set()

        for ans in all_answers:
            btn = Button(
                label=ans[:80],
                style=discord.ButtonStyle.blurple,
                custom_id=f'trivia:{ans[:80]}',
            )
            btn.callback = self._make_callback(ans)
            self.add_item(btn)

    def _make_callback(self, answer: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id in self.answered:
                await interaction.response.send_message('Tu as déjà répondu !', ephemeral=True)
                return
            self.answered.add(interaction.user.id)

            if answer == self.correct:
                msg = f'✅ {interaction.user.mention} — Bonne réponse !'
                color = discord.Color.green()
            else:
                msg = f'❌ {interaction.user.mention} — Faux ! La réponse était **{self.correct}**.'
                color = discord.Color.red()

            for child in self.children:
                child.disabled = True
                if child.label == self.correct[:80]:
                    child.style = discord.ButtonStyle.green

            embed = discord.Embed(description=msg, color=color)
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=embed)
        return callback


class WouldYouView(View):
    def __init__(self, opt_a: str, opt_b: str):
        super().__init__(timeout=60)
        self.opt_a = opt_a
        self.opt_b = opt_b
        self.votes = {'A': 0, 'B': 0}
        self.voters: set = set()

    def _bar(self, count_a, count_b):
        total = count_a + count_b or 1
        pct_a = count_a / total
        filled = int(pct_a * 10)
        return '█' * filled + '░' * (10 - filled)

    @discord.ui.button(label='Option A', style=discord.ButtonStyle.blurple, custom_id='wyr:a')
    async def vote_a(self, i: discord.Interaction, b: Button):
        if i.user.id in self.voters:
            return await i.response.send_message('Déjà voté !', ephemeral=True)
        self.voters.add(i.user.id)
        self.votes['A'] += 1
        await self._update(i)

    @discord.ui.button(label='Option B', style=discord.ButtonStyle.green, custom_id='wyr:b')
    async def vote_b(self, i: discord.Interaction, b: Button):
        if i.user.id in self.voters:
            return await i.response.send_message('Déjà voté !', ephemeral=True)
        self.voters.add(i.user.id)
        self.votes['B'] += 1
        await self._update(i)

    async def _update(self, i: discord.Interaction):
        a, b_ = self.votes['A'], self.votes['B']
        total = a + b_ or 1
        bar = self._bar(a, b_)
        embed = discord.Embed(
            title='🤔 Tu préfères…',
            color=discord.Color.blurple(),
        )
        embed.add_field(name=f'🅰️ {self.opt_a}', value=f'`{bar}` **{a}** ({a*100//total}%)', inline=False)
        embed.add_field(name=f'🅱️ {self.opt_b}', value=f'`{"░"*10}` **{b_}** ({b_*100//total}%)', inline=False)
        embed.set_footer(text=f'{total} vote(s) au total')
        await i.response.edit_message(embed=embed, view=self)


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /8ball ─────────────────────────────────────────
    @app_commands.command(name='8ball', description='La boule magique répond à tes questions')
    @app_commands.describe(question='Ta question')
    async def eight_ball(self, interaction: discord.Interaction, question: str):
        emoji, answer, color = random.choice(EIGHT_BALL)
        embed = discord.Embed(color=color)
        embed.add_field(name='❓ Question', value=question, inline=False)
        embed.add_field(name=f'{emoji} Réponse', value=answer, inline=False)
        embed.set_thumbnail(url='https://upload.wikimedia.org/wikipedia/commons/thumb/f/fd/8ball.svg/240px-8ball.svg.png')
        await interaction.response.send_message(embed=embed)

    # ── /rps ───────────────────────────────────────────
    @app_commands.command(name='rps', description='Pierre-Feuille-Ciseaux contre le bot')
    async def rps(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title='🪨📄✂️ Pierre-Feuille-Ciseaux',
            description='Choisis ton arme !',
            color=discord.Color.blurple(),
        )
        view = RPSView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    # ── /coinflip ──────────────────────────────────────
    @app_commands.command(name='coinflip', description='Lance une pièce')
    async def coinflip(self, interaction: discord.Interaction):
        await interaction.response.defer()
        result = random.choice(['Pile 🌕', 'Face 🦅'])
        for frame in ['🔄 Lancer…', '🪙 En l\'air…', result]:
            embed = discord.Embed(
                title='🪙 Pile ou Face',
                description=frame,
                color=discord.Color.gold(),
            )
            if frame == '🔄 Lancer…':
                msg = await interaction.followup.send(embed=embed)
            else:
                await msg.edit(embed=embed)
            if frame != result:
                await asyncio.sleep(0.7)

    # ── /dice ──────────────────────────────────────────
    @app_commands.command(name='dice', description='Lance un dé')
    @app_commands.describe(faces='Nombre de faces (défaut 6)', quantite='Nombre de dés (défaut 1)')
    async def dice(
        self,
        interaction: discord.Interaction,
        faces: app_commands.Range[int, 2, 1000] = 6,
        quantite: app_commands.Range[int, 1, 10] = 1,
    ):
        rolls = [random.randint(1, faces) for _ in range(quantite)]
        total = sum(rolls)
        rolls_str = ' + '.join(f'`{r}`' for r in rolls)
        embed = discord.Embed(
            title=f'🎲 {quantite}d{faces}',
            description=f'{rolls_str} = **{total}**',
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    # ── /joke ──────────────────────────────────────────
    @app_commands.command(name='joke', description='Une blague aléatoire')
    async def joke(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title='😂 Blague du jour',
            description=random.choice(JOKES),
            color=discord.Color.yellow(),
        )
        await interaction.response.send_message(embed=embed)

    # ── /fact ──────────────────────────────────────────
    @app_commands.command(name='fact', description='Un fait random insolite')
    async def fact(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title='🧠 Le saviez-vous ?',
            description=random.choice(FACTS),
            color=discord.Color.teal(),
        )
        await interaction.response.send_message(embed=embed)

    # ── /meme ──────────────────────────────────────────
    @app_commands.command(name='meme', description='Un meme aléatoire depuis Reddit')
    async def meme(self, interaction: discord.Interaction):
        await interaction.response.defer()
        sub = random.choice(SUBREDDITS)
        url = f'https://www.reddit.com/r/{sub}/random/.json'
        headers = {'User-Agent': 'DiscordBot/1.0'}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        raise ValueError('bad status')
                    data = await resp.json()
                    post = data[0]['data']['children'][0]['data']
                    title = post.get('title', 'Meme')
                    img_url = post.get('url', '')
                    ups = post.get('ups', 0)
                    nsfw = post.get('over_18', False)
                    if nsfw or not img_url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                        raise ValueError('NSFW or no image')

            embed = discord.Embed(title=title, color=discord.Color.orange())
            embed.set_image(url=img_url)
            embed.set_footer(text=f'👍 {ups:,} | r/{sub}')
            await interaction.followup.send(embed=embed)
        except Exception:
            await interaction.followup.send('❌ Impossible de charger un meme. Réessaie !', ephemeral=True)

    # ── /trivia ────────────────────────────────────────
    @app_commands.command(name='trivia', description='Question de culture générale')
    async def trivia(self, interaction: discord.Interaction):
        await interaction.response.defer()
        url = 'https://opentdb.com/api.php?amount=1&type=multiple&lang=fr'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    data = await resp.json()

            q = data['results'][0]
            question = html.unescape(q['question'])
            correct = html.unescape(q['correct_answer'])
            incorrect = [html.unescape(a) for a in q['incorrect_answers']]
            all_ans = incorrect + [correct]
            random.shuffle(all_ans)

            difficulty_colors = {'easy': discord.Color.green(), 'medium': discord.Color.yellow(), 'hard': discord.Color.red()}
            embed = discord.Embed(
                title='🧠 Trivia',
                description=question,
                color=difficulty_colors.get(q['difficulty'], discord.Color.blurple()),
            )
            embed.add_field(name='Catégorie', value=html.unescape(q['category']), inline=True)
            embed.add_field(name='Difficulté', value=q['difficulty'].capitalize(), inline=True)
            embed.set_footer(text='Tu as 20 secondes pour répondre !')

            view = TriviaView(correct, all_ans, interaction.user.id)
            await interaction.followup.send(embed=embed, view=view)
        except Exception:
            await interaction.followup.send('❌ Impossible de charger une question. Réessaie !', ephemeral=True)

    # ── /wouldyourather ────────────────────────────────
    @app_commands.command(name='wouldyourather', description='Tu préfères… (vote interactif)')
    async def wyr(self, interaction: discord.Interaction):
        opt_a, opt_b = random.choice(WOULD_YOU)
        embed = discord.Embed(
            title='🤔 Tu préfères…',
            color=discord.Color.blurple(),
        )
        embed.add_field(name='🅰️', value=opt_a, inline=True)
        embed.add_field(name='🅱️', value=opt_b, inline=True)
        embed.set_footer(text='Tout le monde peut voter !')
        view = WouldYouView(opt_a, opt_b)
        await interaction.response.send_message(embed=embed, view=view)

    # ── /choose ────────────────────────────────────────
    @app_commands.command(name='choose', description='Choisis entre plusieurs options')
    @app_commands.describe(options='Sépare tes options avec | ex: pizza|sushi|burger')
    async def choose(self, interaction: discord.Interaction, options: str):
        choices = [o.strip() for o in options.split('|') if o.strip()]
        if len(choices) < 2:
            await interaction.response.send_message('❌ Donne au moins 2 options séparées par `|`.', ephemeral=True)
            return
        chosen = random.choice(choices)
        embed = discord.Embed(
            description=f'🎯 Je choisis : **{chosen}**',
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)

    # ── /ship ──────────────────────────────────────────
    @app_commands.command(name='ship', description='Calcule la compatibilité amoureuse entre deux membres')
    @app_commands.describe(membre1='Premier membre', membre2='Deuxième membre (toi par défaut)')
    async def ship(self, interaction: discord.Interaction, membre1: discord.Member, membre2: discord.Member = None):
        b = membre2 or interaction.user
        seed = (min(membre1.id, b.id) * max(membre1.id, b.id)) % 101
        pct = seed
        bar = '💗' * (pct // 10) + '🖤' * (10 - pct // 10)
        if pct >= 80:
            msg = '💞 Vous êtes faits l\'un pour l\'autre !'
        elif pct >= 60:
            msg = '💕 C\'est une belle complicité !'
        elif pct >= 40:
            msg = '💛 Il y a quelque chose… peut-être.'
        elif pct >= 20:
            msg = '🤷 Compliqué…'
        else:
            msg = '❄️ Zéro chimie !'

        embed = discord.Embed(
            title=f'💘 {membre1.display_name} & {b.display_name}',
            color=discord.Color.pink() if hasattr(discord.Color, 'pink') else discord.Color.magenta(),
        )
        embed.add_field(name=f'{pct}%', value=f'`{bar}`', inline=False)
        embed.add_field(name='Verdict', value=msg, inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /pp ────────────────────────────────────────────
    @app_commands.command(name='pp', description='Mesure la taille du PP de quelqu\'un 😳')
    @app_commands.describe(membre='La cible (toi par défaut)')
    async def pp(self, interaction: discord.Interaction, membre: discord.Member = None):
        t = membre or interaction.user
        seed = t.id % 21
        bar = '8' + '=' * seed + 'D'
        embed = discord.Embed(
            title=f'📏 PP de {t.display_name}',
            description=f'`{bar}`  ({seed} cm)',
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Fun(bot))
