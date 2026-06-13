"""
Système Welcome / Goodbye :
  - Message de bienvenue avec embed riche
  - Message d'au revoir
  - DM de bienvenue optionnel
  - Auto-rôle à l'arrivée
"""

import discord
from discord.ext import commands
from discord import app_commands
import json, os
from datetime import timezone

WCF_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'welcome.json')


def _load():
    os.makedirs(os.path.dirname(WCF_PATH), exist_ok=True)
    if os.path.exists(WCF_PATH):
        with open(WCF_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save(d):
    with open(WCF_PATH, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

def _cfg(data, gid):
    gid = str(gid)
    data.setdefault(gid, {
        'welcome_channel': None,
        'goodbye_channel': None,
        'welcome_message': 'Bienvenue sur **{server}**, {user} ! Tu es le membre **#{count}** 🎉',
        'goodbye_message': '**{username}** a quitté le serveur. On était {count} membres.',
        'dm_welcome': False,
        'dm_message': 'Bienvenue sur **{server}** ! Bonne découverte !',
        'auto_roles': [],
        'welcome_color': 5793266,
        'embed_image': None,
    })
    return data[gid]

def _format(text: str, member: discord.Member) -> str:
    return (text
        .replace('{user}', member.mention)
        .replace('{username}', str(member))
        .replace('{name}', member.display_name)
        .replace('{server}', member.guild.name)
        .replace('{count}', str(member.guild.member_count))
        .replace('{id}', str(member.id))
    )


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        data = _load()
        cfg = _cfg(data, member.guild.id)

        # Auto-rôles
        for role_id in cfg.get('auto_roles', []):
            role = member.guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role, reason='Auto-rôle à l\'arrivée')
                except discord.Forbidden:
                    pass

        # Welcome embed
        ch_id = cfg.get('welcome_channel')
        if ch_id:
            channel = member.guild.get_channel(int(ch_id))
            if channel:
                embed = self._make_embed(member, cfg, 'welcome')
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

        # DM welcome
        if cfg.get('dm_welcome') and cfg.get('dm_message'):
            try:
                dm_embed = discord.Embed(
                    description=_format(cfg['dm_message'], member),
                    color=discord.Color.blurple(),
                )
                dm_embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        data = _load()
        cfg = _cfg(data, member.guild.id)
        ch_id = cfg.get('goodbye_channel')
        if not ch_id:
            return
        channel = member.guild.get_channel(int(ch_id))
        if not channel:
            return

        embed = discord.Embed(
            description=_format(cfg.get('goodbye_message', '**{username}** a quitté le serveur.'), member),
            color=discord.Color.red(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f'ID : {member.id}')
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    def _make_embed(self, member: discord.Member, cfg: dict, mode: str) -> discord.Embed:
        msg = _format(cfg.get('welcome_message', 'Bienvenue {user} !'), member)
        color = discord.Color(cfg.get('welcome_color', 5793266))
        embed = discord.Embed(description=msg, color=color)
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        if member.guild.icon:
            embed.set_footer(text=member.guild.name, icon_url=member.guild.icon.url)
        if cfg.get('embed_image'):
            embed.set_image(url=cfg['embed_image'])
        embed.timestamp = member.joined_at
        return embed

    # ─── group ────────────────────────────────────────
    wlc = app_commands.Group(name='welcome', description='Configuration du système de bienvenue')

    @wlc.command(name='setchannel', description='Canal pour les messages de bienvenue')
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(canal='Canal ou aucun pour désactiver')
    async def set_welcome_ch(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        cfg['welcome_channel'] = canal.id if canal else None
        _save(data)
        await interaction.response.send_message(
            f'✅ Bienvenue dans {canal.mention}.' if canal else '✅ Bienvenue désactivée.', ephemeral=True
        )

    @wlc.command(name='setgoodbye', description='Canal pour les messages d\'au revoir')
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(canal='Canal ou aucun pour désactiver')
    async def set_goodbye_ch(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        cfg['goodbye_channel'] = canal.id if canal else None
        _save(data)
        await interaction.response.send_message(
            f'✅ Au revoir dans {canal.mention}.' if canal else '✅ Au revoir désactivé.', ephemeral=True
        )

    @wlc.command(name='setmessage', description='Personnalise le message de bienvenue')
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        message='Variables : {user} {username} {name} {server} {count} {id}'
    )
    async def set_message(self, interaction: discord.Interaction, message: str):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        cfg['welcome_message'] = message
        _save(data)
        preview = _format(message, interaction.user)
        embed = discord.Embed(
            title='✅ Message mis à jour',
            description=f'**Aperçu :**\n{preview}',
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @wlc.command(name='autorole', description='Ajoute/retire un auto-rôle')
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(role='Le rôle à auto-assigner', action='add ou remove')
    async def autorole(self, interaction: discord.Interaction, role: discord.Role, action: str = 'add'):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        rid = str(role.id)

        if action == 'add':
            if rid not in cfg['auto_roles']:
                cfg['auto_roles'].append(rid)
            msg = f'✅ {role.mention} sera attribué aux nouveaux membres.'
        else:
            cfg['auto_roles'] = [r for r in cfg['auto_roles'] if r != rid]
            msg = f'✅ {role.mention} retiré des auto-rôles.'

        _save(data)
        await interaction.response.send_message(msg, ephemeral=True)

    @wlc.command(name='dm', description='Active/désactive le DM de bienvenue')
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(activer='Activer ou désactiver', message='Message DM personnalisé')
    async def dm_toggle(self, interaction: discord.Interaction, activer: bool, message: str = None):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        cfg['dm_welcome'] = activer
        if message:
            cfg['dm_message'] = message
        _save(data)
        await interaction.response.send_message(
            f'✅ DM de bienvenue **{"activé" if activer else "désactivé"}**.', ephemeral=True
        )

    @wlc.command(name='test', description='Teste les messages de bienvenue/au revoir')
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(mode='welcome ou goodbye')
    async def test_welcome(self, interaction: discord.Interaction, mode: str = 'welcome'):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        embed = self._make_embed(interaction.user, cfg, mode)
        embed.set_footer(text='🧪 Ceci est un test')
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @wlc.command(name='status', description='Affiche la configuration de bienvenue')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)

        def fmt(val):
            return f'<#{val}>' if val else '`Non configuré`'

        embed = discord.Embed(title='⚙️ Config Welcome', color=discord.Color.blurple())
        embed.add_field(name='Canal Bienvenue', value=fmt(cfg.get('welcome_channel')), inline=True)
        embed.add_field(name='Canal Au revoir', value=fmt(cfg.get('goodbye_channel')), inline=True)
        embed.add_field(name='DM', value='Oui' if cfg.get('dm_welcome') else 'Non', inline=True)
        auto = cfg.get('auto_roles', [])
        embed.add_field(name='Auto-rôles', value=', '.join(f'<@&{r}>' for r in auto) or 'Aucun', inline=False)
        embed.add_field(name='Message', value=f'```{cfg.get("welcome_message", "—")}```', inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Welcome(bot))
