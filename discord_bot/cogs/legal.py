"""
Commandes légales :
  /legal       — Embed avec boutons ToS + Politique de confidentialité
  /tos         — Conditions d'utilisation directement
  /privacy     — Politique de confidentialité directement
  /about       — Informations sur le bot + liens légaux
"""

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import json, os
from datetime import datetime, timezone

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_legal(cfg: dict) -> dict:
    return cfg.get('legal', {})


def legal_view(cfg: dict) -> View:
    """Crée la View avec les boutons ToS + Confidentialité."""
    legal = get_legal(cfg)
    view = View(timeout=None)

    tos_url = legal.get('tos_url', '')
    privacy_url = legal.get('privacy_url', '')
    support = legal.get('support_server')

    if tos_url and not tos_url.startswith('https://TON'):
        view.add_item(Button(
            label='📜 Conditions d\'utilisation',
            url=tos_url,
            style=discord.ButtonStyle.link,
        ))

    if privacy_url and not privacy_url.startswith('https://TON'):
        view.add_item(Button(
            label='🔒 Politique de confidentialité',
            url=privacy_url,
            style=discord.ButtonStyle.link,
        ))

    if support and not support.startswith('https://TON'):
        view.add_item(Button(
            label='💬 Serveur de support',
            url=support,
            style=discord.ButtonStyle.link,
        ))

    return view


def legal_embed(cfg: dict, title: str = '⚖️ Informations légales') -> discord.Embed:
    legal = get_legal(cfg)
    tos_url = legal.get('tos_url', '')
    privacy_url = legal.get('privacy_url', '')
    bot_name = legal.get('bot_name', 'Ce bot')

    not_configured = lambda url: not url or url.startswith('https://TON')

    tos_text = (
        f'[Lire les conditions d\'utilisation]({tos_url})'
        if not not_configured(tos_url)
        else '`Non configuré — remplis config.json`'
    )
    privacy_text = (
        f'[Lire la politique de confidentialité]({privacy_url})'
        if not not_configured(privacy_url)
        else '`Non configuré — remplis config.json`'
    )

    embed = discord.Embed(
        title=title,
        description=(
            f'En utilisant **{bot_name}**, tu acceptes nos documents légaux ci-dessous.\n'
            f'Ces documents régissent l\'utilisation du bot et la gestion de tes données.'
        ),
        color=discord.Color.dark_grey(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name='📜 Conditions d\'utilisation',
        value=tos_text,
        inline=False,
    )
    embed.add_field(
        name='🔒 Politique de confidentialité',
        value=privacy_text,
        inline=False,
    )
    embed.set_footer(text=f'{bot_name} · Documents légaux')
    return embed


class Legal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── /legal ─────────────────────────────────────────
    @app_commands.command(name='legal', description='Affiche les liens légaux du bot (ToS + Confidentialité)')
    async def legal_cmd(self, interaction: discord.Interaction):
        cfg = load_config()
        embed = legal_embed(cfg)
        view = legal_view(cfg)
        await interaction.response.send_message(embed=embed, view=view)

    # ── /tos ───────────────────────────────────────────
    @app_commands.command(name='tos', description='Conditions d\'utilisation du bot')
    async def tos(self, interaction: discord.Interaction):
        cfg = load_config()
        legal = get_legal(cfg)
        tos_url = legal.get('tos_url', '')
        bot_name = legal.get('bot_name', 'Ce bot')

        embed = discord.Embed(
            title='📜 Conditions d\'utilisation',
            color=discord.Color.blurple(),
        )

        if tos_url and not tos_url.startswith('https://TON'):
            embed.description = (
                f'En utilisant **{bot_name}**, tu acceptes les [conditions d\'utilisation]({tos_url}).\n\n'
                f'Clique sur le bouton ci-dessous pour les lire en détail.'
            )
            view = View(timeout=None)
            view.add_item(Button(label='📜 Lire les conditions', url=tos_url, style=discord.ButtonStyle.link))
        else:
            embed.description = (
                '⚠️ Les conditions d\'utilisation ne sont pas encore configurées.\n'
                'L\'administrateur doit remplir `config.json` → `legal.tos_url`.'
            )
            embed.color = discord.Color.orange()
            view = View()

        embed.set_footer(text=f'{bot_name} · Conditions d\'utilisation')
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    # ── /privacy ───────────────────────────────────────
    @app_commands.command(name='privacy', description='Politique de confidentialité du bot')
    async def privacy(self, interaction: discord.Interaction):
        cfg = load_config()
        legal = get_legal(cfg)
        privacy_url = legal.get('privacy_url', '')
        bot_name = legal.get('bot_name', 'Ce bot')

        embed = discord.Embed(
            title='🔒 Politique de confidentialité',
            color=discord.Color.dark_blue(),
        )

        if privacy_url and not privacy_url.startswith('https://TON'):
            embed.description = (
                f'**{bot_name}** collecte et traite certaines données pour fonctionner '
                f'(identifiants Discord, messages dans les tickets, etc.).\n\n'
                f'Consulte notre [politique de confidentialité]({privacy_url}) pour savoir '
                f'quelles données sont collectées, comment elles sont utilisées et comment les supprimer.'
            )
            view = View(timeout=None)
            view.add_item(Button(label='🔒 Lire la politique', url=privacy_url, style=discord.ButtonStyle.link))
        else:
            embed.description = (
                '⚠️ La politique de confidentialité n\'est pas encore configurée.\n'
                'L\'administrateur doit remplir `config.json` → `legal.privacy_url`.'
            )
            embed.color = discord.Color.orange()
            view = View()

        embed.add_field(
            name='📋 Données collectées',
            value=(
                '• Identifiant Discord (ID utilisateur)\n'
                '• Messages envoyés dans les tickets\n'
                '• XP et progression de niveau\n'
                '• Solde et transactions économie\n'
                '• Avertissements de modération'
            ),
            inline=False,
        )
        embed.add_field(
            name='🗑️ Suppression de données',
            value='Contacte un administrateur du serveur pour demander la suppression de tes données.',
            inline=False,
        )
        embed.set_footer(text=f'{bot_name} · Politique de confidentialité')
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    # ── /about ─────────────────────────────────────────
    @app_commands.command(name='about', description='Informations sur le bot')
    async def about(self, interaction: discord.Interaction):
        cfg = load_config()
        legal = get_legal(cfg)
        bot_name = legal.get('bot_name', self.bot.user.name)

        embed = discord.Embed(
            title=f'ℹ️ À propos de {bot_name}',
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name='Serveurs', value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name='Latence', value=f'{round(self.bot.latency * 1000)} ms', inline=True)
        embed.add_field(name='Version discord.py', value=discord.__version__, inline=True)
        embed.add_field(
            name='📋 Fonctionnalités',
            value=(
                '📩 Tickets · 💰 Économie · ⭐ Niveaux\n'
                '🎉 Giveaways · 🎵 Musique · 🤖 AutoMod\n'
                '🎭 Reaction Roles · 📊 Sondages · 😂 Fun'
            ),
            inline=False,
        )

        tos_url = legal.get('tos_url', '')
        privacy_url = legal.get('privacy_url', '')
        links = []
        if tos_url and not tos_url.startswith('https://TON'):
            links.append(f'[📜 Conditions d\'utilisation]({tos_url})')
        if privacy_url and not privacy_url.startswith('https://TON'):
            links.append(f'[🔒 Confidentialité]({privacy_url})')

        if links:
            embed.add_field(name='⚖️ Légal', value=' · '.join(links), inline=False)

        embed.set_footer(text=f'{bot_name} · Développé avec discord.py')

        view = legal_view(cfg)
        await interaction.response.send_message(embed=embed, view=view)

    # ── /legal setup ───────────────────────────────────
    legal_admin = app_commands.Group(name='legalconfig', description='Configure les liens légaux')

    @legal_admin.command(name='set', description='Définit les URLs légaux du bot')
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        tos_url='URL des conditions d\'utilisation',
        privacy_url='URL de la politique de confidentialité',
        bot_name='Nom du bot affiché dans les embeds',
        support_server='URL du serveur de support (optionnel)',
    )
    async def legal_set(
        self,
        interaction: discord.Interaction,
        tos_url: str = None,
        privacy_url: str = None,
        bot_name: str = None,
        support_server: str = None,
    ):
        cfg = load_config()
        legal = cfg.setdefault('legal', {})
        changed = []

        def validate_url(url: str) -> bool:
            return url.startswith('http://') or url.startswith('https://')

        if tos_url is not None:
            if not validate_url(tos_url):
                await interaction.response.send_message('❌ URL ToS invalide (doit commencer par http:// ou https://).', ephemeral=True)
                return
            legal['tos_url'] = tos_url
            changed.append(f'📜 ToS → `{tos_url}`')

        if privacy_url is not None:
            if not validate_url(privacy_url):
                await interaction.response.send_message('❌ URL Confidentialité invalide.', ephemeral=True)
                return
            legal['privacy_url'] = privacy_url
            changed.append(f'🔒 Confidentialité → `{privacy_url}`')

        if bot_name is not None:
            legal['bot_name'] = bot_name
            changed.append(f'🤖 Nom → `{bot_name}`')

        if support_server is not None:
            if support_server.lower() == 'none':
                legal['support_server'] = None
                changed.append('💬 Serveur support → retiré')
            elif validate_url(support_server):
                legal['support_server'] = support_server
                changed.append(f'💬 Serveur support → `{support_server}`')
            else:
                await interaction.response.send_message('❌ URL serveur de support invalide.', ephemeral=True)
                return

        if not changed:
            await interaction.response.send_message('❌ Aucun paramètre fourni.', ephemeral=True)
            return

        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)

        embed = discord.Embed(
            title='✅ Configuration légale mise à jour',
            description='\n'.join(changed),
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @legal_admin.command(name='status', description='Affiche la configuration légale actuelle')
    @app_commands.checks.has_permissions(administrator=True)
    async def legal_status(self, interaction: discord.Interaction):
        cfg = load_config()
        legal = get_legal(cfg)

        def fmt(url):
            if not url or url.startswith('https://TON'):
                return '`❌ Non configuré`'
            return f'[✅ Configuré]({url})'

        embed = discord.Embed(title='⚙️ Config légale', color=discord.Color.blurple())
        embed.add_field(name='Nom du bot', value=f'`{legal.get("bot_name", "Non défini")}`', inline=False)
        embed.add_field(name='📜 ToS', value=fmt(legal.get('tos_url')), inline=True)
        embed.add_field(name='🔒 Confidentialité', value=fmt(legal.get('privacy_url')), inline=True)
        embed.add_field(name='💬 Serveur support', value=fmt(legal.get('support_server')), inline=True)

        preview_view = legal_view(cfg)
        embed.add_field(
            name='Aperçu boutons',
            value=f'`{len(preview_view.children)}` bouton(s) actif(s) dans `/legal`',
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message('❌ Permission refusée.', ephemeral=True)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Legal(bot))
