"""
Polls & Rappels :
  - Sondage avec jusqu'à 8 options + boutons interactifs
  - Résultats live avec barres de progression
  - Rappels personnels (/remind)
"""

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import json, os, asyncio
from datetime import datetime, timezone, timedelta

REMINDERS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'reminders.json')

NUMBER_EMOJIS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣']


def parse_time(raw: str) -> int | None:
    raw = raw.strip().lower()
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    total = 0
    buf = ''
    for ch in raw:
        if ch.isdigit():
            buf += ch
        elif ch in units and buf:
            total += int(buf) * units[ch]
            buf = ''
        else:
            return None
    if buf:
        total += int(buf)
    return total or None

def fmt_time(secs: int) -> str:
    if secs < 60:
        return f'{secs}s'
    m, s = divmod(secs, 60)
    if m < 60:
        return f'{m}m' + (f' {s}s' if s else '')
    h, m = divmod(m, 60)
    if h < 24:
        return f'{h}h' + (f' {m}m' if m else '')
    d, h = divmod(h, 24)
    return f'{d}j' + (f' {h}h' if h else '')


class PollView(View):
    def __init__(self, options: list[str], author_id: int, end_time: float | None = None):
        super().__init__(timeout=end_time)
        self.options = options
        self.author_id = author_id
        self.votes: dict[int, int] = {}     # user_id -> option_index
        self.ended = False

        for i, opt in enumerate(options):
            btn = Button(
                label=opt[:80],
                emoji=NUMBER_EMOJIS[i],
                style=discord.ButtonStyle.blurple,
                custom_id=f'poll:{i}',
            )
            btn.callback = self._make_callback(i)
            self.add_item(btn)

        end_btn = Button(
            label='🔒 Terminer',
            style=discord.ButtonStyle.red,
            custom_id='poll:end',
        )
        end_btn.callback = self._end_callback
        self.add_item(end_btn)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if self.ended:
                await interaction.response.send_message('Ce sondage est terminé.', ephemeral=True)
                return

            uid = interaction.user.id
            prev = self.votes.get(uid)

            if prev == index:
                del self.votes[uid]
                msg = f'❌ Vote retiré pour **{self.options[index]}**.'
            else:
                self.votes[uid] = index
                msg = f'✅ Vote enregistré pour **{self.options[index]}**.'

            await interaction.response.send_message(msg, ephemeral=True)
            await self._update_embed(interaction.message)
        return callback

    async def _end_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message('❌ Seul l\'auteur peut terminer le sondage.', ephemeral=True)
            return
        self.ended = True
        for child in self.children:
            child.disabled = True
        embed = self._build_embed(finished=True)
        await interaction.response.edit_message(embed=embed, view=self)

    def _build_embed(self, finished=False) -> discord.Embed:
        total = len(self.votes)
        counts = [0] * len(self.options)
        for idx in self.votes.values():
            if 0 <= idx < len(counts):
                counts[idx] += 1

        color = discord.Color.red() if finished else discord.Color.blurple()
        embed = discord.Embed(
            title='📊 Sondage' + (' — Terminé' if finished else ''),
            color=color,
        )

        lines = []
        for i, opt in enumerate(self.options):
            pct = counts[i] / total * 100 if total else 0
            bar_filled = int(pct / 5)
            bar = '█' * bar_filled + '░' * (20 - bar_filled)
            lines.append(
                f'{NUMBER_EMOJIS[i]} **{opt}**\n`{bar}` **{counts[i]}** vote(s) ({pct:.0f}%)'
            )

        embed.description = '\n\n'.join(lines)
        embed.set_footer(text=f'👥 {total} votant(s) au total' + (' · Sondage terminé' if finished else ' · Clique pour voter'))
        return embed

    async def _update_embed(self, message: discord.Message):
        try:
            await message.edit(embed=self._build_embed())
        except (discord.NotFound, discord.Forbidden):
            pass

    async def on_timeout(self):
        self.ended = True
        for child in self.children:
            child.disabled = True


class Polls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._reminder_tasks: list[asyncio.Task] = []

    async def cog_load(self):
        # Restore pending reminders
        if os.path.exists(REMINDERS_PATH):
            with open(REMINDERS_PATH, 'r') as f:
                reminders = json.load(f)
            now = datetime.now(timezone.utc).timestamp()
            for r in reminders:
                if r['end_time'] > now:
                    task = asyncio.create_task(self._reminder_task(r))
                    self._reminder_tasks.append(task)

    def _save_reminders(self, reminders):
        os.makedirs(os.path.dirname(REMINDERS_PATH), exist_ok=True)
        with open(REMINDERS_PATH, 'w') as f:
            json.dump(reminders, f, indent=2)

    async def _reminder_task(self, r: dict):
        end = r['end_time']
        now = datetime.now(timezone.utc).timestamp()
        delay = max(0, end - now)
        await asyncio.sleep(delay)

        try:
            channel = self.bot.get_channel(r['channel_id'])
            if channel:
                embed = discord.Embed(
                    title='⏰ Rappel !',
                    description=r['message'],
                    color=discord.Color.yellow(),
                    timestamp=datetime.now(timezone.utc),
                )
                embed.set_footer(text='Rappel demandé')
                await channel.send(f'<@{r["user_id"]}>', embed=embed)
        except Exception:
            pass

        # Remove from file
        if os.path.exists(REMINDERS_PATH):
            with open(REMINDERS_PATH, 'r') as f:
                data = json.load(f)
            data = [x for x in data if x.get('id') != r.get('id')]
            self._save_reminders(data)

    # ── /poll ──────────────────────────────────────────
    @app_commands.command(name='poll', description='Crée un sondage interactif (jusqu\'à 8 options)')
    @app_commands.describe(
        question='La question du sondage',
        option1='Option 1',
        option2='Option 2',
        option3='Option 3',
        option4='Option 4',
        option5='Option 5',
        option6='Option 6',
        option7='Option 7',
        option8='Option 8',
        duree='Durée avant fermeture auto (ex: 1h, 30m) — optionnel',
    )
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: str = None,
        option4: str = None,
        option5: str = None,
        option6: str = None,
        option7: str = None,
        option8: str = None,
        duree: str = None,
    ):
        opts = [o for o in [option1, option2, option3, option4, option5, option6, option7, option8] if o]

        timeout = None
        end_time = None
        footer_extra = ''
        if duree:
            secs = parse_time(duree)
            if secs and 10 <= secs <= 604800:
                timeout = secs
                end_time = datetime.now(timezone.utc).timestamp() + secs
                footer_extra = f' · Ferme dans {fmt_time(secs)}'
            else:
                await interaction.response.send_message('❌ Durée invalide (10s min, 7j max).', ephemeral=True)
                return

        embed = discord.Embed(
            title=f'📊 {question}',
            color=discord.Color.blurple(),
        )
        options_text = '\n'.join(f'{NUMBER_EMOJIS[i]} {opt}' for i, opt in enumerate(opts))
        embed.description = options_text
        embed.set_footer(text=f'0 votant(s){footer_extra} · Clique pour voter')
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        view = PollView(opts, interaction.user.id, end_time=timeout)
        await interaction.response.send_message(embed=embed, view=view)

        if timeout:
            await asyncio.sleep(timeout)
            if not view.ended:
                view.ended = True
                for child in view.children:
                    child.disabled = True
                final = view._build_embed(finished=True)
                try:
                    msg = await interaction.original_response()
                    await msg.edit(embed=final, view=view)
                except Exception:
                    pass

    # ── /remind ────────────────────────────────────────
    @app_commands.command(name='remind', description='Configure un rappel personnel')
    @app_commands.describe(
        duree='Dans combien de temps (ex: 30m, 2h, 1d)',
        message='Ce dont tu veux te souvenir',
    )
    async def remind(self, interaction: discord.Interaction, duree: str, message: str):
        secs = parse_time(duree)
        if not secs or secs < 10:
            await interaction.response.send_message('❌ Durée invalide (min 10s).', ephemeral=True)
            return
        if secs > 2592000:  # 30 days
            await interaction.response.send_message('❌ Maximum 30 jours.', ephemeral=True)
            return

        end = datetime.now(timezone.utc).timestamp() + secs
        r = {
            'id': f'{interaction.user.id}_{end}',
            'user_id': interaction.user.id,
            'channel_id': interaction.channel.id,
            'message': message,
            'end_time': end,
        }

        # Persist
        existing = []
        if os.path.exists(REMINDERS_PATH):
            with open(REMINDERS_PATH, 'r') as f:
                existing = json.load(f)
        existing.append(r)
        self._save_reminders(existing)

        task = asyncio.create_task(self._reminder_task(r))
        self._reminder_tasks.append(task)

        embed = discord.Embed(
            title='⏰ Rappel enregistré !',
            description=f'**Dans :** {fmt_time(secs)}\n**Message :** {message}',
            color=discord.Color.green(),
        )
        embed.set_footer(text=f'Tu seras rappelé dans {fmt_time(secs)}')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /quickpoll ─────────────────────────────────────
    @app_commands.command(name='quickpoll', description='Sondage rapide Oui/Non')
    @app_commands.describe(question='Ta question')
    async def quickpoll(self, interaction: discord.Interaction, question: str):
        embed = discord.Embed(
            title=f'📊 {question}',
            description='✅ Oui · ❌ Non',
            color=discord.Color.blurple(),
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        msg = await interaction.channel.send(embed=embed)
        await msg.add_reaction('✅')
        await msg.add_reaction('❌')
        await interaction.response.send_message('✅ Sondage créé !', ephemeral=True)


async def setup(bot):
    await bot.add_cog(Polls(bot))
