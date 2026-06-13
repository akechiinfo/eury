"""
Système de Giveaway :
  - Durée flexible (1m, 2h, 3d…)
  - Plusieurs gagnants
  - Compte à rebours live (edit)
  - Reroll
  - Exigence de rôle
"""

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import json, os, asyncio, random
from datetime import datetime, timezone, timedelta

GW_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'giveaways.json')


def _load():
    os.makedirs(os.path.dirname(GW_PATH), exist_ok=True)
    if os.path.exists(GW_PATH):
        with open(GW_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save(data):
    with open(GW_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def parse_duration(raw: str) -> int | None:
    raw = raw.strip().lower()
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
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

def fmt_duration(secs: int) -> str:
    if secs < 60:
        return f'{secs}s'
    m, s = divmod(secs, 60)
    if m < 60:
        return f'{m}m {s}s'
    h, m = divmod(m, 60)
    if h < 24:
        return f'{h}h {m}m'
    d, h = divmod(h, 24)
    return f'{d}j {h}h'

def fmt_dt(ts: float) -> str:
    return discord.utils.format_dt(datetime.fromtimestamp(ts, tz=timezone.utc), style='R')


def make_gw_embed(gw: dict, ended=False) -> discord.Embed:
    end_ts = gw['end_time']
    entries = len(gw.get('entries', []))
    color = discord.Color.red() if ended else discord.Color.gold()
    title = '🎉 GIVEAWAY TERMINÉ' if ended else '🎉 GIVEAWAY'

    embed = discord.Embed(title=title, description=gw['prize'], color=color,
                          timestamp=datetime.fromtimestamp(end_ts, tz=timezone.utc))
    if not ended:
        embed.add_field(name='⏳ Fin', value=fmt_dt(end_ts), inline=True)
    embed.add_field(name='🏆 Gagnants', value=str(gw['winners']), inline=True)
    embed.add_field(name='👥 Participants', value=str(entries), inline=True)
    embed.add_field(name='🎫 Participer', value='Clique sur 🎉 ci-dessous !', inline=False)
    if gw.get('required_role'):
        embed.add_field(name='📋 Rôle requis', value=f'<@&{gw["required_role"]}>', inline=True)
    embed.set_footer(text=f'Organisé par {gw["host_name"]}')
    return embed


class GiveawayView(View):
    def __init__(self, gw_id: str):
        super().__init__(timeout=None)
        self.gw_id = gw_id

    @discord.ui.button(label='🎉 Participer', style=discord.ButtonStyle.green,
                       custom_id='gw:enter')
    async def enter(self, interaction: discord.Interaction, button: Button):
        data = _load()
        gw_id = None
        for mid, gw in data.items():
            if gw.get('channel_id') == interaction.channel.id:
                gw_id = mid
                break

        if not gw_id or data[gw_id].get('ended'):
            await interaction.response.send_message('❌ Ce giveaway est terminé.', ephemeral=True)
            return

        gw = data[gw_id]
        uid = str(interaction.user.id)

        # Role check
        req_role = gw.get('required_role')
        if req_role:
            if not any(r.id == int(req_role) for r in interaction.user.roles):
                await interaction.response.send_message(
                    f'❌ Tu dois avoir le rôle <@&{req_role}> pour participer.', ephemeral=True
                )
                return

        if uid in gw['entries']:
            gw['entries'].remove(uid)
            _save(data)
            await interaction.response.send_message('❌ Tu t\'es retiré du giveaway.', ephemeral=True)
        else:
            gw['entries'].append(uid)
            _save(data)
            await interaction.response.send_message('✅ Tu participes au giveaway ! Bonne chance !', ephemeral=True)


class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._tasks: dict[str, asyncio.Task] = {}

    async def cog_load(self):
        data = _load()
        now = datetime.now(timezone.utc).timestamp()
        for msg_id, gw in data.items():
            if not gw.get('ended'):
                if gw['end_time'] <= now:
                    asyncio.create_task(self._end_giveaway(msg_id))
                else:
                    task = asyncio.create_task(self._run_giveaway(msg_id))
                    self._tasks[msg_id] = task

    async def _run_giveaway(self, msg_id: str):
        data = _load()
        gw = data.get(msg_id)
        if not gw:
            return

        channel = self.bot.get_channel(gw['channel_id'])
        if not channel:
            return

        try:
            message = await channel.fetch_message(int(msg_id))
        except discord.NotFound:
            return

        # Countdown updates
        end_time = gw['end_time']
        while datetime.now(timezone.utc).timestamp() < end_time:
            remaining = end_time - datetime.now(timezone.utc).timestamp()
            if remaining > 3600:
                await asyncio.sleep(300)
            elif remaining > 600:
                await asyncio.sleep(60)
            elif remaining > 60:
                await asyncio.sleep(15)
            else:
                await asyncio.sleep(5)

            data = _load()
            gw = data.get(msg_id)
            if not gw or gw.get('ended'):
                return
            try:
                await message.edit(embed=make_gw_embed(gw))
            except (discord.NotFound, discord.Forbidden):
                return

        await self._end_giveaway(msg_id)

    async def _end_giveaway(self, msg_id: str):
        data = _load()
        gw = data.get(msg_id)
        if not gw or gw.get('ended'):
            return

        gw['ended'] = True
        _save(data)

        channel = self.bot.get_channel(gw['channel_id'])
        if not channel:
            return

        try:
            message = await channel.fetch_message(int(msg_id))
        except discord.NotFound:
            return

        entries = gw.get('entries', [])
        num_winners = min(gw['winners'], len(entries))
        winners = random.sample(entries, num_winners) if entries else []

        end_embed = make_gw_embed(gw, ended=True)
        if winners:
            end_embed.add_field(
                name='🏆 Gagnants',
                value='\n'.join(f'<@{w}>' for w in winners),
                inline=False,
            )
        else:
            end_embed.add_field(name='😢 Résultat', value='Aucun participant.', inline=False)

        await message.edit(embed=end_embed, view=None)

        if winners:
            txt = f'🎉 Félicitations {", ".join(f"<@{w}>" for w in winners)} ! Vous avez gagné **{gw["prize"]}** !'
        else:
            txt = f'😢 Personne n\'a participé au giveaway **{gw["prize"]}**.'

        await channel.send(txt, reference=message)
        gw['winner_ids'] = winners
        _save(data)

    gw_group = app_commands.Group(name='giveaway', description='Commandes de giveaway')

    @gw_group.command(name='start', description='Lance un giveaway')
    @app_commands.describe(
        duree='Durée (ex: 1h, 30m, 2d)',
        gagnants='Nombre de gagnants',
        prix='Ce que l\'on gagne',
        role_requis='Rôle requis pour participer (optionnel)',
        canal='Canal (actuel par défaut)',
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gw_start(
        self,
        interaction: discord.Interaction,
        duree: str,
        gagnants: app_commands.Range[int, 1, 20],
        prix: str,
        role_requis: discord.Role = None,
        canal: discord.TextChannel = None,
    ):
        secs = parse_duration(duree)
        if not secs:
            await interaction.response.send_message('❌ Durée invalide (ex: `1h`, `30m`, `2d`).', ephemeral=True)
            return
        if secs < 10:
            await interaction.response.send_message('❌ Durée minimale : 10 secondes.', ephemeral=True)
            return

        target_ch = canal or interaction.channel
        end_ts = datetime.now(timezone.utc).timestamp() + secs

        gw_data = {
            'prize': prix,
            'winners': gagnants,
            'end_time': end_ts,
            'host_id': interaction.user.id,
            'host_name': str(interaction.user),
            'channel_id': target_ch.id,
            'guild_id': interaction.guild.id,
            'entries': [],
            'ended': False,
            'required_role': role_requis.id if role_requis else None,
            'winner_ids': [],
        }

        placeholder_embed = make_gw_embed(gw_data)
        view = GiveawayView(gw_id='')
        await interaction.response.send_message('✅ Giveaway lancé !', ephemeral=True)
        msg = await target_ch.send(embed=placeholder_embed, view=view)

        gw_data['message_id'] = msg.id
        data = _load()
        data[str(msg.id)] = gw_data
        _save(data)

        task = asyncio.create_task(self._run_giveaway(str(msg.id)))
        self._tasks[str(msg.id)] = task

    @gw_group.command(name='end', description='Termine immédiatement un giveaway')
    @app_commands.describe(message_id='L\'ID du message du giveaway')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gw_end(self, interaction: discord.Interaction, message_id: str):
        data = _load()
        if message_id not in data:
            await interaction.response.send_message('❌ Giveaway introuvable.', ephemeral=True)
            return
        task = self._tasks.get(message_id)
        if task:
            task.cancel()
        await interaction.response.send_message('✅ Fin du giveaway en cours…', ephemeral=True)
        await self._end_giveaway(message_id)

    @gw_group.command(name='reroll', description='Tire un nouveau gagnant')
    @app_commands.describe(message_id='L\'ID du message du giveaway')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gw_reroll(self, interaction: discord.Interaction, message_id: str):
        data = _load()
        gw = data.get(message_id)
        if not gw or not gw.get('ended'):
            await interaction.response.send_message('❌ Giveaway non terminé ou introuvable.', ephemeral=True)
            return

        entries = gw.get('entries', [])
        prev_winners = gw.get('winner_ids', [])
        pool = [e for e in entries if e not in prev_winners]

        if not pool:
            pool = entries

        if not pool:
            await interaction.response.send_message('❌ Aucun participant.', ephemeral=True)
            return

        winner = random.choice(pool)
        embed = discord.Embed(
            title='🔄 Reroll Giveaway',
            description=f'🎉 Nouveau gagnant : <@{winner}> pour **{gw["prize"]}** !',
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @gw_group.command(name='list', description='Liste les giveaways actifs')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gw_list(self, interaction: discord.Interaction):
        data = _load()
        active = [
            (mid, gw) for mid, gw in data.items()
            if not gw.get('ended') and gw.get('guild_id') == interaction.guild.id
        ]
        if not active:
            await interaction.response.send_message('📭 Aucun giveaway actif.', ephemeral=True)
            return

        embed = discord.Embed(title='🎉 Giveaways actifs', color=discord.Color.gold())
        for mid, gw in active:
            remaining = gw['end_time'] - datetime.now(timezone.utc).timestamp()
            embed.add_field(
                name=gw['prize'],
                value=(
                    f'ID: `{mid}` · Fin {fmt_dt(gw["end_time"])}\n'
                    f'{len(gw["entries"])} participants · {gw["winners"]} gagnant(s)'
                ),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Giveaway(bot))
