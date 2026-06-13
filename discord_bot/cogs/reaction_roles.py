"""
Reaction Roles :
  - Ajouter un rôle lié à une réaction sur n'importe quel message
  - Plusieurs rôles par message
  - Mode exclusif (1 seul rôle à la fois sur un message)
  - Persistant entre les redémarrages
"""

import discord
from discord.ext import commands
from discord import app_commands
import json, os

RR_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'reaction_roles.json')


def _load():
    os.makedirs(os.path.dirname(RR_PATH), exist_ok=True)
    if os.path.exists(RR_PATH):
        with open(RR_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save(d):
    with open(RR_PATH, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        data = _load()
        msg_id = str(payload.message_id)
        if msg_id not in data:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        emoji_str = str(payload.emoji)
        entry = data[msg_id]

        if emoji_str not in entry.get('roles', {}):
            return

        role_id = int(entry['roles'][emoji_str])
        role = guild.get_role(role_id)
        if not role:
            return

        # Exclusive mode: remove other roles from this message
        if entry.get('exclusive', False):
            for other_emoji, other_rid in entry['roles'].items():
                if other_emoji != emoji_str:
                    other_role = guild.get_role(int(other_rid))
                    if other_role and other_role in member.roles:
                        try:
                            await member.remove_roles(other_role, reason='Reaction role (exclusif)')
                            # Also remove reaction
                            channel = guild.get_channel(payload.channel_id)
                            if channel:
                                msg = await channel.fetch_message(payload.message_id)
                                await msg.remove_reaction(discord.PartialEmoji(name=other_emoji), member)
                        except (discord.Forbidden, discord.NotFound):
                            pass

        try:
            await member.add_roles(role, reason='Reaction role')
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        data = _load()
        msg_id = str(payload.message_id)
        if msg_id not in data:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        emoji_str = str(payload.emoji)
        entry = data[msg_id]
        if emoji_str not in entry.get('roles', {}):
            return

        role_id = int(entry['roles'][emoji_str])
        role = guild.get_role(role_id)
        if not role:
            return

        try:
            await member.remove_roles(role, reason='Reaction role (retiré)')
        except discord.Forbidden:
            pass

    # ─── /rr commands ──────────────────────────────────
    rr = app_commands.Group(name='rr', description='Reaction Roles')

    @rr.command(name='add', description='Lie une réaction à un rôle sur un message')
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.describe(
        message_id='ID du message cible',
        emoji='L\'emoji à utiliser',
        role='Le rôle à attribuer',
        exclusif='Un seul rôle à la fois sur ce message ?',
    )
    async def rr_add(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role,
        exclusif: bool = False,
    ):
        # Try to fetch the message
        msg = None
        for channel in interaction.guild.text_channels:
            try:
                msg = await channel.fetch_message(int(message_id))
                break
            except (discord.NotFound, discord.Forbidden, ValueError):
                continue

        if not msg:
            await interaction.response.send_message('❌ Message introuvable.', ephemeral=True)
            return

        # Check role hierarchy
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                '❌ Ce rôle est au-dessus du rôle du bot.', ephemeral=True
            )
            return

        data = _load()
        mid = str(msg.id)
        if mid not in data:
            data[mid] = {
                'channel_id': msg.channel.id,
                'guild_id': interaction.guild.id,
                'roles': {},
                'exclusive': exclusif,
            }

        data[mid]['roles'][emoji] = role.id
        if exclusif:
            data[mid]['exclusive'] = True
        _save(data)

        # Add reaction to message
        try:
            await msg.add_reaction(emoji)
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.response.send_message(
                f'⚠️ Rôle configuré mais impossible d\'ajouter la réaction : `{e}`', ephemeral=True
            )
            return

        embed = discord.Embed(
            title='✅ Reaction Role ajouté',
            color=discord.Color.green(),
        )
        embed.add_field(name='Message', value=f'[Aller au message]({msg.jump_url})', inline=True)
        embed.add_field(name='Emoji', value=emoji, inline=True)
        embed.add_field(name='Rôle', value=role.mention, inline=True)
        embed.add_field(name='Exclusif', value='Oui' if exclusif else 'Non', inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rr.command(name='remove', description='Retire un reaction role d\'un message')
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.describe(message_id='ID du message', emoji='L\'emoji à retirer')
    async def rr_remove(self, interaction: discord.Interaction, message_id: str, emoji: str):
        data = _load()
        mid = str(message_id)
        if mid not in data or emoji not in data[mid].get('roles', {}):
            await interaction.response.send_message('❌ Reaction role introuvable.', ephemeral=True)
            return

        del data[mid]['roles'][emoji]
        if not data[mid]['roles']:
            del data[mid]
        _save(data)

        await interaction.response.send_message(
            f'✅ Reaction role `{emoji}` retiré du message `{message_id}`.', ephemeral=True
        )

    @rr.command(name='list', description='Liste tous les reaction roles du serveur')
    @app_commands.checks.has_permissions(manage_roles=True)
    async def rr_list(self, interaction: discord.Interaction):
        data = _load()
        gid = interaction.guild.id
        entries = {
            mid: d for mid, d in data.items()
            if d.get('guild_id') == gid
        }

        if not entries:
            await interaction.response.send_message('📭 Aucun reaction role configuré.', ephemeral=True)
            return

        embed = discord.Embed(title='🎭 Reaction Roles', color=discord.Color.blurple())
        for mid, d in list(entries.items())[:10]:
            ch = interaction.guild.get_channel(d.get('channel_id', 0))
            ch_name = ch.mention if ch else '`canal supprimé`'
            roles_txt = '\n'.join(
                f'{emo} → <@&{rid}>' for emo, rid in d['roles'].items()
            )
            embed.add_field(
                name=f'Message `{mid}` dans {ch_name}',
                value=roles_txt or 'Aucun',
                inline=False,
            )
        if len(entries) > 10:
            embed.set_footer(text=f'… et {len(entries) - 10} autres')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @rr.command(name='panel', description='Crée un message panel avec les rôles déjà configurés')
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.describe(
        titre='Titre du panel',
        description='Description du panel',
        canal='Canal où envoyer (actuel par défaut)',
    )
    async def rr_panel(
        self,
        interaction: discord.Interaction,
        titre: str = '🎭 Choisis tes rôles',
        description: str = 'Clique sur une réaction pour obtenir le rôle correspondant.',
        canal: discord.TextChannel = None,
    ):
        target = canal or interaction.channel
        embed = discord.Embed(
            title=titre,
            description=description,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text='Clique pour obtenir/retirer un rôle')
        await interaction.response.send_message('✅ Panel créé !', ephemeral=True)
        await target.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
