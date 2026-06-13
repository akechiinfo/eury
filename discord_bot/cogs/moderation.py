"""
Commandes de modération : kick, ban, unban, mute, unmute, clear, warn, warnings, slowmode
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone, timedelta
import json
import os


WARNS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'warns.json')
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_warns():
    os.makedirs(os.path.dirname(WARNS_PATH), exist_ok=True)
    if os.path.exists(WARNS_PATH):
        with open(WARNS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_warns(data):
    os.makedirs(os.path.dirname(WARNS_PATH), exist_ok=True)
    with open(WARNS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


async def send_mod_log(bot, guild, action, moderator, target, reason, extra=None):
    cfg = load_config()
    log_ch_id = cfg.get('mod_log_channel_id')
    if not log_ch_id:
        return
    channel = guild.get_channel(int(log_ch_id))
    if not channel:
        return

    colors = {
        'kick': discord.Color.orange(),
        'ban': discord.Color.red(),
        'unban': discord.Color.green(),
        'mute': discord.Color.yellow(),
        'unmute': discord.Color.green(),
        'warn': discord.Color.gold(),
        'clear': discord.Color.blurple(),
        'slowmode': discord.Color.blurple(),
    }
    icons = {
        'kick': '👢', 'ban': '🔨', 'unban': '✅',
        'mute': '🔇', 'unmute': '🔊', 'warn': '⚠️',
        'clear': '🗑️', 'slowmode': '🐢',
    }

    embed = discord.Embed(
        title=f'{icons.get(action, "🔧")} {action.capitalize()}',
        color=colors.get(action, discord.Color.blurple()),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name='Modérateur', value=moderator.mention, inline=True)
    if target:
        embed.add_field(name='Cible', value=f'{target} (`{target.id}`)', inline=True)
    embed.add_field(name='Raison', value=reason, inline=False)
    if extra:
        embed.add_field(name='Détails', value=extra, inline=False)

    await channel.send(embed=embed)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def has_mod_perms(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.kick_members

    # ── /kick ──────────────────────────────────────────
    @app_commands.command(name='kick', description='Expulse un membre du serveur')
    @app_commands.describe(membre='Le membre à expulser', raison='Raison')
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, membre: discord.Member, raison: str = 'Aucune raison'):
        if membre.top_role >= interaction.user.top_role:
            await interaction.response.send_message('❌ Tu ne peux pas expulser ce membre (hiérarchie).', ephemeral=True)
            return
        try:
            await membre.send(
                embed=discord.Embed(
                    description=f'Tu as été **expulsé** de **{interaction.guild.name}**.\n**Raison :** {raison}',
                    color=discord.Color.orange(),
                )
            )
        except discord.Forbidden:
            pass
        await membre.kick(reason=f'{interaction.user} : {raison}')
        embed = discord.Embed(
            description=f'✅ {membre.mention} a été expulsé.\n**Raison :** {raison}',
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)
        await send_mod_log(self.bot, interaction.guild, 'kick', interaction.user, membre, raison)

    # ── /ban ───────────────────────────────────────────
    @app_commands.command(name='ban', description='Bannit un membre du serveur')
    @app_commands.describe(membre='Le membre à bannir', raison='Raison', delete_days='Jours de messages à supprimer (0-7)')
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        raison: str = 'Aucune raison',
        delete_days: app_commands.Range[int, 0, 7] = 0,
    ):
        if membre.top_role >= interaction.user.top_role:
            await interaction.response.send_message('❌ Tu ne peux pas bannir ce membre (hiérarchie).', ephemeral=True)
            return
        try:
            await membre.send(
                embed=discord.Embed(
                    description=f'Tu as été **banni** de **{interaction.guild.name}**.\n**Raison :** {raison}',
                    color=discord.Color.red(),
                )
            )
        except discord.Forbidden:
            pass
        await membre.ban(reason=f'{interaction.user} : {raison}', delete_message_days=delete_days)
        embed = discord.Embed(
            description=f'✅ {membre.mention} a été banni.\n**Raison :** {raison}',
            color=discord.Color.red(),
        )
        await interaction.response.send_message(embed=embed)
        await send_mod_log(self.bot, interaction.guild, 'ban', interaction.user, membre, raison)

    # ── /unban ─────────────────────────────────────────
    @app_commands.command(name='unban', description='Débannit un utilisateur')
    @app_commands.describe(user_id='L\'ID Discord de l\'utilisateur', raison='Raison')
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, raison: str = 'Aucune raison'):
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message('❌ ID invalide.', ephemeral=True)
            return

        try:
            ban_entry = await interaction.guild.fetch_ban(discord.Object(id=uid))
            await interaction.guild.unban(ban_entry.user, reason=f'{interaction.user} : {raison}')
            embed = discord.Embed(
                description=f'✅ `{ban_entry.user}` a été débanni.\n**Raison :** {raison}',
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed)
            await send_mod_log(self.bot, interaction.guild, 'unban', interaction.user, ban_entry.user, raison)
        except discord.NotFound:
            await interaction.response.send_message('❌ Cet utilisateur n\'est pas banni.', ephemeral=True)

    # ── /mute ──────────────────────────────────────────
    @app_commands.command(name='mute', description='Mute (timeout) un membre')
    @app_commands.describe(
        membre='Le membre à muter',
        duree='Durée en minutes (max 40 320 = 28 jours)',
        raison='Raison',
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        membre: discord.Member,
        duree: app_commands.Range[int, 1, 40320] = 10,
        raison: str = 'Aucune raison',
    ):
        if membre.top_role >= interaction.user.top_role:
            await interaction.response.send_message('❌ Tu ne peux pas muter ce membre (hiérarchie).', ephemeral=True)
            return

        until = datetime.now(timezone.utc) + timedelta(minutes=duree)
        await membre.timeout(until, reason=f'{interaction.user} : {raison}')

        h, m = divmod(duree, 60)
        duration_str = f'{h}h {m}m' if h else f'{m}m'

        embed = discord.Embed(
            description=(
                f'🔇 {membre.mention} a été mute pour **{duration_str}**.\n'
                f'**Raison :** {raison}\n'
                f'**Fin :** {discord.utils.format_dt(until, style="R")}'
            ),
            color=discord.Color.yellow(),
        )
        await interaction.response.send_message(embed=embed)
        await send_mod_log(self.bot, interaction.guild, 'mute', interaction.user, membre, raison, f'Durée : {duration_str}')

    # ── /unmute ────────────────────────────────────────
    @app_commands.command(name='unmute', description='Retire le timeout d\'un membre')
    @app_commands.describe(membre='Le membre à unmute', raison='Raison')
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, membre: discord.Member, raison: str = 'Aucune raison'):
        if not membre.is_timed_out():
            await interaction.response.send_message('❌ Ce membre n\'est pas mute.', ephemeral=True)
            return
        await membre.timeout(None, reason=f'{interaction.user} : {raison}')
        embed = discord.Embed(
            description=f'🔊 {membre.mention} a été unmute.\n**Raison :** {raison}',
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)
        await send_mod_log(self.bot, interaction.guild, 'unmute', interaction.user, membre, raison)

    # ── /clear ─────────────────────────────────────────
    @app_commands.command(name='clear', description='Supprime des messages dans ce canal')
    @app_commands.describe(
        nombre='Nombre de messages à supprimer (1-100)',
        membre='Supprimer uniquement les messages de ce membre',
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(
        self,
        interaction: discord.Interaction,
        nombre: app_commands.Range[int, 1, 100] = 10,
        membre: discord.Member = None,
    ):
        await interaction.response.defer(ephemeral=True)

        def check(msg):
            return membre is None or msg.author == membre

        deleted = await interaction.channel.purge(limit=nombre, check=check, bulk=True)
        embed = discord.Embed(
            description=f'🗑️ **{len(deleted)}** message(s) supprimé(s)' +
                        (f' de {membre.mention}' if membre else '') + '.',
            color=discord.Color.blurple(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        await send_mod_log(
            self.bot, interaction.guild, 'clear', interaction.user, membre or interaction.user,
            f'{len(deleted)} messages supprimés dans {interaction.channel.mention}',
        )

    # ── /warn ──────────────────────────────────────────
    @app_commands.command(name='warn', description='Avertit un membre')
    @app_commands.describe(membre='Le membre à avertir', raison='Raison')
    @app_commands.checks.has_permissions(kick_members=True)
    async def warn(self, interaction: discord.Interaction, membre: discord.Member, raison: str):
        warns = load_warns()
        guild_id = str(interaction.guild.id)
        user_id = str(membre.id)

        if guild_id not in warns:
            warns[guild_id] = {}
        if user_id not in warns[guild_id]:
            warns[guild_id][user_id] = []

        warn_entry = {
            'reason': raison,
            'moderator_id': interaction.user.id,
            'moderator': str(interaction.user),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        warns[guild_id][user_id].append(warn_entry)
        save_warns(warns)

        count = len(warns[guild_id][user_id])

        try:
            await membre.send(
                embed=discord.Embed(
                    description=(
                        f'⚠️ Tu as reçu un avertissement sur **{interaction.guild.name}**.\n'
                        f'**Raison :** {raison}\n'
                        f'**Total warns :** {count}'
                    ),
                    color=discord.Color.gold(),
                )
            )
        except discord.Forbidden:
            pass

        embed = discord.Embed(
            description=(
                f'⚠️ {membre.mention} a été averti.\n'
                f'**Raison :** {raison}\n'
                f'**Warns total :** {count}'
            ),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)
        await send_mod_log(self.bot, interaction.guild, 'warn', interaction.user, membre, raison, f'Total warns : {count}')

    # ── /warnings ──────────────────────────────────────
    @app_commands.command(name='warnings', description='Affiche les avertissements d\'un membre')
    @app_commands.describe(membre='Le membre (toi par défaut)', clear_all='Supprimer tous les warns')
    @app_commands.checks.has_permissions(kick_members=True)
    async def warnings(
        self,
        interaction: discord.Interaction,
        membre: discord.Member = None,
        clear_all: bool = False,
    ):
        target = membre or interaction.user
        warns = load_warns()
        guild_id = str(interaction.guild.id)
        user_id = str(target.id)
        user_warns = warns.get(guild_id, {}).get(user_id, [])

        if clear_all:
            if guild_id in warns and user_id in warns[guild_id]:
                warns[guild_id][user_id] = []
                save_warns(warns)
            await interaction.response.send_message(
                f'✅ Tous les warns de {target.mention} ont été supprimés.', ephemeral=True
            )
            return

        if not user_warns:
            await interaction.response.send_message(
                f'✅ {target.mention} n\'a aucun avertissement.', ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f'⚠️ Avertissements — {target.display_name} ({len(user_warns)})',
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        for i, w in enumerate(user_warns[-10:], 1):
            ts = datetime.fromisoformat(w['timestamp'])
            embed.add_field(
                name=f'#{i} — {discord.utils.format_dt(ts, style="R")}',
                value=f'**Raison :** {w["reason"]}\n**Modérateur :** {w["moderator"]}',
                inline=False,
            )

        if len(user_warns) > 10:
            embed.set_footer(text=f'Affichage des 10 derniers sur {len(user_warns)} au total')

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /slowmode ──────────────────────────────────────
    @app_commands.command(name='slowmode', description='Définit le slowmode d\'un canal')
    @app_commands.describe(secondes='Délai en secondes (0 pour désactiver, max 21600)', canal='Canal cible')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        secondes: app_commands.Range[int, 0, 21600] = 0,
        canal: discord.TextChannel = None,
    ):
        target = canal or interaction.channel
        await target.edit(slowmode_delay=secondes)

        if secondes == 0:
            msg = f'✅ Slowmode désactivé dans {target.mention}.'
        else:
            msg = f'🐢 Slowmode défini à **{secondes}s** dans {target.mention}.'

        embed = discord.Embed(description=msg, color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed)
        await send_mod_log(self.bot, interaction.guild, 'slowmode', interaction.user, None, f'{secondes}s dans {target.mention}')

    # ── error handler ──────────────────────────────────
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message('❌ Tu n\'as pas la permission.', ephemeral=True)
        else:
            await interaction.response.send_message(f'❌ Erreur : {error}', ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
