"""
Auto-modération :
  - Anti-spam (messages trop rapides)
  - Anti-invitations Discord
  - Anti-liens externes
  - Filtre de mots
  - Limite de majuscules
  - Mention spam
  - Log automatique + mute/warn du contrevenant
"""

import discord
from discord.ext import commands
from discord import app_commands
import json, os, re, asyncio
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque

AM_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'automod.json')
WARNS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'warns.json')

INVITE_PATTERN = re.compile(
    r'(discord\.gg|discordapp\.com/invite|discord\.com/invite)/[a-zA-Z0-9\-]+'
)
URL_PATTERN = re.compile(
    r'https?://[^\s]+'
)


def _load():
    os.makedirs(os.path.dirname(AM_PATH), exist_ok=True)
    if os.path.exists(AM_PATH):
        with open(AM_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save(d):
    with open(AM_PATH, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

def _cfg(data, gid):
    gid = str(gid)
    data.setdefault(gid, {
        'enabled': False,
        'log_channel': None,
        'anti_spam': True,
        'spam_threshold': 5,         # messages par fenêtre
        'spam_window': 5,            # secondes
        'anti_invite': True,
        'anti_link': False,
        'allowed_links': [],
        'caps_limit': 70,            # % de majuscules
        'caps_min_length': 10,       # longueur min pour vérifier les caps
        'mention_limit': 5,
        'word_filter': [],
        'mute_duration': 5,          # minutes
        'warn_before_mute': True,
        'ignored_roles': [],
        'ignored_channels': [],
    })
    return data[gid]

def _load_warns():
    if os.path.exists(WARNS_PATH):
        with open(WARNS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save_warns(d):
    os.makedirs(os.path.dirname(WARNS_PATH), exist_ok=True)
    with open(WARNS_PATH, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=2, ensure_ascii=False)


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # spam tracking: guild -> user -> deque of timestamps
        self._spam: dict[str, dict[str, deque]] = defaultdict(lambda: defaultdict(deque))

    def _is_ignored(self, message: discord.Message, cfg: dict) -> bool:
        if not message.guild:
            return True
        # Check ignored roles
        for rid in cfg.get('ignored_roles', []):
            if message.author.get_role(int(rid)):
                return True
        # Check ignored channels
        if str(message.channel.id) in [str(c) for c in cfg.get('ignored_channels', [])]:
            return True
        # Staff bypass
        if message.author.guild_permissions.manage_messages:
            return True
        return False

    async def _punish(self, message: discord.Message, cfg: dict, reason: str):
        guild = message.guild
        member = message.author

        # Add warn
        warns = _load_warns()
        gid = str(guild.id)
        uid = str(member.id)
        warns.setdefault(gid, {}).setdefault(uid, [])
        warns[gid][uid].append({
            'reason': f'[AutoMod] {reason}',
            'moderator': 'AutoMod',
            'moderator_id': self.bot.user.id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
        warn_count = len(warns[gid][uid])
        _save_warns(warns)

        # Try to delete the message
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

        # Mute if too many warns or warn_before_mute is off
        should_mute = (not cfg.get('warn_before_mute', True)) or warn_count >= 3
        muted = False
        if should_mute:
            mute_mins = cfg.get('mute_duration', 5)
            try:
                until = datetime.now(timezone.utc) + timedelta(minutes=mute_mins)
                await member.timeout(until, reason=f'AutoMod : {reason}')
                muted = True
            except (discord.Forbidden, discord.HTTPException):
                pass

        # DM the user
        action_txt = f'mute de {cfg["mute_duration"]}min' if muted else 'avertissement'
        try:
            e = discord.Embed(
                title='⚠️ AutoMod — Violation',
                description=(
                    f'**Serveur :** {guild.name}\n'
                    f'**Raison :** {reason}\n'
                    f'**Action :** {action_txt}\n'
                    f'**Warns :** {warn_count}/3'
                ),
                color=discord.Color.orange(),
            )
            await member.send(embed=e)
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Log
        log_ch_id = cfg.get('log_channel')
        if log_ch_id:
            ch = guild.get_channel(int(log_ch_id))
            if ch:
                log_embed = discord.Embed(
                    title='🤖 AutoMod — Action',
                    color=discord.Color.red(),
                    timestamp=datetime.now(timezone.utc),
                )
                log_embed.add_field(name='Membre', value=f'{member.mention} (`{member.id}`)', inline=True)
                log_embed.add_field(name='Canal', value=message.channel.mention, inline=True)
                log_embed.add_field(name='Raison', value=reason, inline=False)
                log_embed.add_field(name='Action', value=action_txt, inline=True)
                log_embed.add_field(name='Warns', value=str(warn_count), inline=True)
                content_preview = message.content[:200] if message.content else '—'
                log_embed.add_field(name='Message', value=f'```{content_preview}```', inline=False)
                log_embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await ch.send(embed=log_embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        data = _load()
        cfg = _cfg(data, message.guild.id)

        if not cfg.get('enabled', False):
            return
        if self._is_ignored(message, cfg):
            return

        content = message.content or ''
        gid = str(message.guild.id)
        uid = str(message.author.id)
        now = datetime.now(timezone.utc).timestamp()

        # ── Anti-spam ──────────────────────────────────
        if cfg.get('anti_spam', True):
            window = cfg.get('spam_window', 5)
            threshold = cfg.get('spam_threshold', 5)
            dq = self._spam[gid][uid]
            dq.append(now)
            while dq and now - dq[0] > window:
                dq.popleft()
            if len(dq) >= threshold:
                dq.clear()
                await self._punish(message, cfg, f'Spam ({threshold} messages en {window}s)')
                return

        # ── Anti-invitations ───────────────────────────
        if cfg.get('anti_invite', True) and INVITE_PATTERN.search(content):
            await self._punish(message, cfg, 'Invitation Discord non autorisée')
            return

        # ── Anti-liens ─────────────────────────────────
        if cfg.get('anti_link', False) and URL_PATTERN.search(content):
            allowed = cfg.get('allowed_links', [])
            if not any(a in content for a in allowed):
                await self._punish(message, cfg, 'Lien non autorisé')
                return

        # ── Filtre de mots ─────────────────────────────
        content_lower = content.lower()
        for word in cfg.get('word_filter', []):
            if word.lower() in content_lower:
                await self._punish(message, cfg, f'Mot interdit : ||{word}||')
                return

        # ── Caps lock ──────────────────────────────────
        min_len = cfg.get('caps_min_length', 10)
        caps_limit = cfg.get('caps_limit', 70)
        if len(content) >= min_len:
            letters = [c for c in content if c.isalpha()]
            if letters:
                caps_pct = sum(1 for c in letters if c.isupper()) / len(letters) * 100
                if caps_pct >= caps_limit:
                    await self._punish(message, cfg, f'Trop de majuscules ({int(caps_pct)}%)')
                    return

        # ── Mention spam ───────────────────────────────
        mention_limit = cfg.get('mention_limit', 5)
        total_mentions = len(message.mentions) + len(message.role_mentions)
        if total_mentions >= mention_limit:
            await self._punish(message, cfg, f'Trop de mentions ({total_mentions}/{mention_limit})')
            return

    # ─── /automod commands ─────────────────────────────
    am = app_commands.Group(name='automod', description='Configuration de l\'auto-modération')

    @am.command(name='enable', description='Active ou désactive l\'AutoMod')
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(activer='True pour activer, False pour désactiver')
    async def am_enable(self, interaction: discord.Interaction, activer: bool):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        cfg['enabled'] = activer
        _save(data)
        status = 'activé ✅' if activer else 'désactivé ❌'
        await interaction.response.send_message(f'🤖 AutoMod **{status}**.', ephemeral=True)

    @am.command(name='logchannel', description='Canal de logs AutoMod')
    @app_commands.checks.has_permissions(administrator=True)
    async def am_log(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        cfg['log_channel'] = canal.id if canal else None
        _save(data)
        await interaction.response.send_message(
            f'✅ Logs AutoMod dans {canal.mention}.' if canal else '✅ Logs désactivés.', ephemeral=True
        )

    @am.command(name='antispam', description='Configure l\'anti-spam')
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(activer='Activer', messages='Seuil de messages', secondes='Fenêtre de temps (s)')
    async def am_spam(
        self,
        interaction: discord.Interaction,
        activer: bool = True,
        messages: app_commands.Range[int, 2, 20] = 5,
        secondes: app_commands.Range[int, 2, 30] = 5,
    ):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        cfg['anti_spam'] = activer
        cfg['spam_threshold'] = messages
        cfg['spam_window'] = secondes
        _save(data)
        await interaction.response.send_message(
            f'✅ Anti-spam {"activé" if activer else "désactivé"} — {messages} msg / {secondes}s.', ephemeral=True
        )

    @am.command(name='antiinvite', description='Bloque les invitations Discord')
    @app_commands.checks.has_permissions(administrator=True)
    async def am_invite(self, interaction: discord.Interaction, activer: bool):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        cfg['anti_invite'] = activer
        _save(data)
        await interaction.response.send_message(
            f'✅ Anti-invite {"activé" if activer else "désactivé"}.', ephemeral=True
        )

    @am.command(name='antilink', description='Bloque les liens externes')
    @app_commands.checks.has_permissions(administrator=True)
    async def am_link(self, interaction: discord.Interaction, activer: bool):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        cfg['anti_link'] = activer
        _save(data)
        await interaction.response.send_message(
            f'✅ Anti-lien {"activé" if activer else "désactivé"}.', ephemeral=True
        )

    @am.command(name='wordfilter', description='Ajoute/retire un mot interdit')
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(action='add ou remove', mot='Le mot à filtrer')
    async def am_word(self, interaction: discord.Interaction, action: str, mot: str):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        mot = mot.lower()
        if action == 'add':
            if mot not in cfg['word_filter']:
                cfg['word_filter'].append(mot)
            msg = f'✅ `{mot}` ajouté au filtre.'
        else:
            cfg['word_filter'] = [w for w in cfg['word_filter'] if w != mot]
            msg = f'✅ `{mot}` retiré du filtre.'
        _save(data)
        await interaction.response.send_message(msg, ephemeral=True)

    @am.command(name='ignorerole', description='Ignore un rôle dans l\'AutoMod')
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(role='Rôle à ignorer', action='add ou remove')
    async def am_ignore_role(self, interaction: discord.Interaction, role: discord.Role, action: str = 'add'):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)
        rid = str(role.id)
        if action == 'add':
            if rid not in cfg['ignored_roles']:
                cfg['ignored_roles'].append(rid)
        else:
            cfg['ignored_roles'] = [r for r in cfg['ignored_roles'] if r != rid]
        _save(data)
        await interaction.response.send_message(
            f'✅ {role.mention} {"ignoré" if action == "add" else "plus ignoré"} par l\'AutoMod.', ephemeral=True
        )

    @am.command(name='status', description='Affiche la config AutoMod')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def am_status(self, interaction: discord.Interaction):
        data = _load()
        cfg = _cfg(data, interaction.guild.id)

        def yn(v):
            return '✅' if v else '❌'

        embed = discord.Embed(
            title='🤖 AutoMod — Configuration',
            color=discord.Color.green() if cfg.get('enabled') else discord.Color.red(),
        )
        embed.add_field(name='Statut', value='**Activé** ✅' if cfg.get('enabled') else '**Désactivé** ❌', inline=False)
        embed.add_field(name='Anti-spam', value=f'{yn(cfg["anti_spam"])} — {cfg["spam_threshold"]} msg/{cfg["spam_window"]}s', inline=True)
        embed.add_field(name='Anti-invite', value=yn(cfg['anti_invite']), inline=True)
        embed.add_field(name='Anti-lien', value=yn(cfg['anti_link']), inline=True)
        embed.add_field(name='Caps limit', value=f'{cfg["caps_limit"]}% (min {cfg["caps_min_length"]} chars)', inline=True)
        embed.add_field(name='Mention limit', value=str(cfg['mention_limit']), inline=True)
        embed.add_field(name='Mute durée', value=f'{cfg["mute_duration"]}min', inline=True)
        words = cfg.get('word_filter', [])
        embed.add_field(name=f'Mots filtrés ({len(words)})',
                        value=', '.join(f'||{w}||' for w in words[:10]) or 'Aucun', inline=False)
        log = cfg.get('log_channel')
        embed.add_field(name='Canal logs', value=f'<#{log}>' if log else '`Non configuré`', inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
