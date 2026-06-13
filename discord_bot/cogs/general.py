"""
Commandes générales : help, ping, info, avatar, serverinfo
"""

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from datetime import datetime, timezone
import time, json, os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')

def _legal_view() -> View:
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        legal = cfg.get('legal', {})
        view = View(timeout=None)
        tos = legal.get('tos_url', '')
        prv = legal.get('privacy_url', '')
        if tos and not tos.startswith('https://TON'):
            view.add_item(Button(label='📜 Conditions', url=tos, style=discord.ButtonStyle.link))
        if prv and not prv.startswith('https://TON'):
            view.add_item(Button(label='🔒 Confidentialité', url=prv, style=discord.ButtonStyle.link))
        return view
    except Exception:
        return View()


class General(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._start = time.monotonic()

    # ── /ping ──────────────────────────────────────────
    @app_commands.command(name='ping', description='Affiche la latence du bot')
    async def ping(self, interaction: discord.Interaction):
        ws_lat = round(self.bot.latency * 1000)
        t0 = time.monotonic()
        await interaction.response.defer()
        api_lat = round((time.monotonic() - t0) * 1000)

        color = discord.Color.green() if ws_lat < 100 else discord.Color.orange() if ws_lat < 200 else discord.Color.red()
        embed = discord.Embed(title='🏓 Pong !', color=color)
        embed.add_field(name='WebSocket', value=f'`{ws_lat} ms`', inline=True)
        embed.add_field(name='API', value=f'`{api_lat} ms`', inline=True)
        await interaction.followup.send(embed=embed)

    # ── /help ──────────────────────────────────────────
    @app_commands.command(name='help', description='Affiche la liste des commandes')
    async def help_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title='📖 Aide — Commandes disponibles',
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(
            name='📩 Système de Tickets',
            value=(
                '`/ticket setup` — Crée le panel de tickets\n'
                '`/ticket config` — Configure le système\n'
                '`/ticket status` — Statut de la config\n'
                '`/ticket list` — Liste les tickets ouverts\n'
                '`/ticket add` — Ajouter un membre au ticket\n'
                '`/ticket remove` — Retirer un membre du ticket\n'
                '`/ticket close` — Fermer le ticket\n'
                '`/ticket delete` — Supprimer le ticket'
            ),
            inline=False,
        )
        embed.add_field(
            name='🔨 Modération',
            value=(
                '`/kick` — Expulse un membre\n'
                '`/ban` — Bannit un membre\n'
                '`/unban` — Débannit un membre\n'
                '`/mute` — Mute (timeout) un membre\n'
                '`/unmute` — Retire le timeout\n'
                '`/clear` — Supprime des messages\n'
                '`/warn` — Avertit un membre\n'
                '`/warnings` — Voir les avertissements\n'
                '`/slowmode` — Défini le slowmode'
            ),
            inline=False,
        )
        embed.add_field(
            name='ℹ️ Général',
            value=(
                '`/ping` — Latence du bot\n'
                '`/avatar` — Avatar d\'un membre\n'
                '`/userinfo` — Infos sur un membre\n'
                '`/serverinfo` — Infos sur le serveur\n'
                '`/uptime` — Temps de fonctionnement\n'
                '`/about` — À propos du bot'
            ),
            inline=False,
        )
        embed.add_field(
            name='⚖️ Légal',
            value=(
                '`/legal` — Conditions & Confidentialité\n'
                '`/tos` — Conditions d\'utilisation\n'
                '`/privacy` — Politique de confidentialité'
            ),
            inline=False,
        )
        embed.set_footer(text=f'{interaction.guild.name}', icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
        view = _legal_view()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /avatar ────────────────────────────────────────
    @app_commands.command(name='avatar', description='Affiche l\'avatar d\'un membre')
    @app_commands.describe(membre='Le membre (toi par défaut)')
    async def avatar(self, interaction: discord.Interaction, membre: discord.Member = None):
        target = membre or interaction.user
        embed = discord.Embed(
            title=f'Avatar de {target.display_name}',
            color=discord.Color.blurple(),
        )
        embed.set_image(url=target.display_avatar.url)
        embed.add_field(name='Lien', value=f'[Ouvrir]({target.display_avatar.url})', inline=False)
        await interaction.response.send_message(embed=embed)

    # ── /userinfo ──────────────────────────────────────
    @app_commands.command(name='userinfo', description='Informations sur un membre')
    @app_commands.describe(membre='Le membre (toi par défaut)')
    async def userinfo(self, interaction: discord.Interaction, membre: discord.Member = None):
        m = membre or interaction.user
        roles = [r.mention for r in reversed(m.roles) if r != interaction.guild.default_role]

        embed = discord.Embed(
            title=f'Informations — {m}',
            color=m.color if m.color != discord.Color.default() else discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=m.display_avatar.url)
        embed.add_field(name='Nom affiché', value=m.display_name, inline=True)
        embed.add_field(name='ID', value=f'`{m.id}`', inline=True)
        embed.add_field(name='Bot', value='Oui' if m.bot else 'Non', inline=True)
        embed.add_field(
            name='Compte créé',
            value=discord.utils.format_dt(m.created_at, style='R'),
            inline=True,
        )
        embed.add_field(
            name='Rejoint le serveur',
            value=discord.utils.format_dt(m.joined_at, style='R') if m.joined_at else '—',
            inline=True,
        )
        embed.add_field(
            name=f'Rôles ({len(roles)})',
            value=' '.join(roles[:10]) + (' …' if len(roles) > 10 else '') or '—',
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    # ── /serverinfo ────────────────────────────────────
    @app_commands.command(name='serverinfo', description='Informations sur le serveur')
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        bots = sum(1 for m in g.members if m.bot)

        embed = discord.Embed(
            title=g.name,
            description=g.description or '',
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        if g.banner:
            embed.set_image(url=g.banner.url)

        embed.add_field(name='Propriétaire', value=f'<@{g.owner_id}>', inline=True)
        embed.add_field(name='ID', value=f'`{g.id}`', inline=True)
        embed.add_field(
            name='Créé le',
            value=discord.utils.format_dt(g.created_at, style='R'),
            inline=True,
        )
        embed.add_field(name='Membres', value=str(g.member_count), inline=True)
        embed.add_field(name='Bots', value=str(bots), inline=True)
        embed.add_field(name='Boosts', value=str(g.premium_subscription_count), inline=True)
        embed.add_field(name='Canaux texte', value=str(len(g.text_channels)), inline=True)
        embed.add_field(name='Canaux vocaux', value=str(len(g.voice_channels)), inline=True)
        embed.add_field(name='Rôles', value=str(len(g.roles)), inline=True)
        embed.set_footer(text=f'Niveau boost : {g.premium_tier}')
        await interaction.response.send_message(embed=embed)

    # ── /uptime ────────────────────────────────────────
    @app_commands.command(name='uptime', description='Temps de fonctionnement du bot')
    async def uptime(self, interaction: discord.Interaction):
        elapsed = time.monotonic() - self._start
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        embed = discord.Embed(
            description=f'⏱️ Uptime : `{h}h {m}m {s}s`',
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(General(bot))
