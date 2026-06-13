"""
Système XP / Niveaux :
  - XP par message (cooldown 60s)
  - Carte de rang générée avec Pillow
  - Notifications de level-up
  - Classement
  - Rôles de niveau (configurable)
"""

import discord
from discord.ext import commands
from discord import app_commands
import json, os, asyncio, math, io
from datetime import datetime, timezone

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

import aiohttp

LEVELS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'levels.json')
LVLCFG_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'levels_config.json')
XP_PER_MSG_MIN = 10
XP_PER_MSG_MAX = 25
XP_COOLDOWN = 60


def _load():
    os.makedirs(os.path.dirname(LEVELS_PATH), exist_ok=True)
    if os.path.exists(LEVELS_PATH):
        with open(LEVELS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save(data):
    with open(LEVELS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def _load_cfg():
    if os.path.exists(LVLCFG_PATH):
        with open(LVLCFG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def _save_cfg(data):
    os.makedirs(os.path.dirname(LVLCFG_PATH), exist_ok=True)
    with open(LVLCFG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def _user(data, gid, uid):
    gid, uid = str(gid), str(uid)
    data.setdefault(gid, {})
    data[gid].setdefault(uid, {'xp': 0, 'level': 0, 'messages': 0, 'last_xp': None})
    return data[gid][uid]

def xp_for_level(level):
    return int(100 * (level ** 1.5))

def total_xp_for_level(level):
    return sum(xp_for_level(i) for i in range(1, level + 1))

def level_from_xp(xp):
    level = 0
    while xp >= xp_for_level(level + 1):
        xp -= xp_for_level(level + 1)
        level += 1
    return level

def xp_progress(total_xp):
    level = 0
    xp = total_xp
    while xp >= xp_for_level(level + 1):
        xp -= xp_for_level(level + 1)
        level += 1
    needed = xp_for_level(level + 1)
    return level, xp, needed


async def fetch_avatar_bytes(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.read()


def build_rank_card(username: str, discriminator: str, avatar_bytes: bytes,
                    level: int, rank: int, current_xp: int, needed_xp: int,
                    total_xp: int) -> io.BytesIO:
    W, H = 900, 250
    BAR_COLOR = (88, 101, 242)
    BG1 = (32, 34, 37)
    BG2 = (47, 49, 54)

    img = Image.new('RGBA', (W, H), BG1)
    draw = ImageDraw.Draw(img)

    # Background gradient panels
    for x in range(W):
        r = int(BG1[0] + (BG2[0] - BG1[0]) * x / W)
        g = int(BG1[1] + (BG2[1] - BG1[1]) * x / W)
        b = int(BG1[2] + (BG2[2] - BG1[2]) * x / W)
        draw.line([(x, 0), (x, H)], fill=(r, g, b))

    # Avatar circle
    try:
        av_img = Image.open(io.BytesIO(avatar_bytes)).convert('RGBA').resize((160, 160))
        mask = Image.new('L', (160, 160), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, 160, 160), fill=255)
        av_circle = Image.new('RGBA', (160, 160), (0, 0, 0, 0))
        av_circle.paste(av_img, (0, 0), mask)
        # Border ring
        ring = Image.new('RGBA', (172, 172), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(ring)
        ring_draw.ellipse((0, 0, 172, 172), fill=(*BAR_COLOR, 255))
        img.paste(ring, (39, 39), ring)
        img.paste(av_circle, (45, 45), av_circle)
    except Exception:
        draw.ellipse((45, 45, 205, 205), fill=(100, 100, 100))

    # XP bar background
    bar_x, bar_y, bar_w, bar_h = 240, 170, 620, 30
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=15, fill=(60, 62, 68))

    # XP bar fill
    if needed_xp > 0:
        fill_w = int(bar_w * min(current_xp / needed_xp, 1.0))
    else:
        fill_w = bar_w
    if fill_w > 0:
        draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=15, fill=(*BAR_COLOR, 255))

    # Fonts (fallback to default if no font available)
    try:
        fn_big   = ImageFont.truetype('arial.ttf', 36)
        fn_med   = ImageFont.truetype('arial.ttf', 26)
        fn_small = ImageFont.truetype('arial.ttf', 20)
    except Exception:
        fn_big = fn_med = fn_small = ImageFont.load_default()

    # Username
    draw.text((240, 80), username, font=fn_big, fill=(255, 255, 255))
    draw.text((240, 122), f'#{discriminator}' if discriminator else '', font=fn_small, fill=(148, 155, 164))

    # Level + Rank
    draw.text((240, 30), f'NIVEAU {level}', font=fn_med, fill=(*BAR_COLOR,))
    rank_text = f'RANG #{rank}'
    bbox = draw.textbbox((0, 0), rank_text, font=fn_med)
    draw.text((W - 30 - (bbox[2] - bbox[0]), 30), rank_text, font=fn_med, fill=(255, 215, 0))

    # XP text
    xp_text = f'{current_xp:,} / {needed_xp:,} XP'
    bbox2 = draw.textbbox((0, 0), xp_text, font=fn_small)
    draw.text((bar_x + bar_w - (bbox2[2] - bbox2[0]), bar_y - 28), xp_text, font=fn_small, fill=(148, 155, 164))

    # Total XP
    draw.text((bar_x, bar_y + bar_h + 8), f'XP total : {total_xp:,}', font=fn_small, fill=(100, 110, 120))

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._xp_cooldowns: dict[str, float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        key = f'{message.guild.id}:{message.author.id}'
        now = datetime.now(timezone.utc).timestamp()
        if now - self._xp_cooldowns.get(key, 0) < XP_COOLDOWN:
            return
        self._xp_cooldowns[key] = now

        import random
        xp_gain = random.randint(XP_PER_MSG_MIN, XP_PER_MSG_MAX)

        data = _load()
        u = _user(data, message.guild.id, message.author.id)
        old_level = level_from_xp(u['xp'])
        u['xp'] += xp_gain
        u['messages'] = u.get('messages', 0) + 1
        new_level = level_from_xp(u['xp'])
        _save(data)

        if new_level > old_level:
            await self._on_level_up(message, new_level)

    async def _on_level_up(self, message: discord.Message, new_level: int):
        cfg = _load_cfg()
        gid = str(message.guild.id)
        channel_id = cfg.get(gid, {}).get('levelup_channel')
        channel = (
            message.guild.get_channel(int(channel_id))
            if channel_id else message.channel
        )

        rewards = {5: '🌟', 10: '🔥', 20: '💎', 50: '👑'}
        bonus = rewards.get(new_level, '')

        embed = discord.Embed(
            title=f'🎉 Level Up ! {bonus}',
            description=f'{message.author.mention} est maintenant **niveau {new_level}** !',
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=message.author.display_avatar.url)

        # Level roles
        role_rewards = cfg.get(gid, {}).get('level_roles', {})
        role_id = role_rewards.get(str(new_level))
        if role_id:
            role = message.guild.get_role(int(role_id))
            if role:
                try:
                    await message.author.add_roles(role)
                    embed.add_field(name='🎁 Rôle débloqué', value=role.mention, inline=False)
                except discord.Forbidden:
                    pass

        if channel:
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

    # ── /rank ──────────────────────────────────────────
    @app_commands.command(name='rank', description='Affiche ta carte de rang')
    @app_commands.describe(membre='Le membre (toi par défaut)')
    async def rank(self, interaction: discord.Interaction, membre: discord.Member = None):
        await interaction.response.defer()
        target = membre or interaction.user
        data = _load()
        u = _user(data, interaction.guild.id, target.id)

        lv, cur_xp, needed = xp_progress(u['xp'])

        # Calculate rank
        gid = str(interaction.guild.id)
        guild_data = data.get(gid, {})
        ranking = sorted(guild_data.items(), key=lambda x: x[1].get('xp', 0), reverse=True)
        rank = next((i + 1 for i, (uid, _) in enumerate(ranking) if uid == str(target.id)), '?')

        if PILLOW_OK:
            try:
                av_bytes = await fetch_avatar_bytes(str(target.display_avatar.url))
                disc = target.discriminator if target.discriminator != '0' else ''
                buf = build_rank_card(
                    target.display_name, disc,
                    av_bytes, lv, rank, cur_xp, needed, u['xp']
                )
                file = discord.File(fp=buf, filename='rank.png')
                embed = discord.Embed(color=discord.Color.blurple())
                embed.set_image(url='attachment://rank.png')
                await interaction.followup.send(embed=embed, file=file)
                return
            except Exception:
                pass

        # Fallback embed si Pillow échoue
        bar_fill = int((cur_xp / needed * 20)) if needed else 20
        bar = '█' * bar_fill + '░' * (20 - bar_fill)
        embed = discord.Embed(title=f'🏅 Rang de {target.display_name}', color=discord.Color.blurple())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name='Niveau', value=f'`{lv}`', inline=True)
        embed.add_field(name='Rang', value=f'`#{rank}`', inline=True)
        embed.add_field(name='Messages', value=f'`{u.get("messages", 0):,}`', inline=True)
        embed.add_field(name=f'XP ({cur_xp:,}/{needed:,})', value=f'`{bar}`', inline=False)
        embed.add_field(name='XP Total', value=f'`{u["xp"]:,}`', inline=True)
        await interaction.followup.send(embed=embed)

    # ── /top ───────────────────────────────────────────
    @app_commands.command(name='top', description='Classement XP du serveur')
    async def top(self, interaction: discord.Interaction):
        data = _load()
        gid = str(interaction.guild.id)
        guild_data = data.get(gid, {})
        ranking = sorted(guild_data.items(), key=lambda x: x[1].get('xp', 0), reverse=True)

        medals = ['🥇', '🥈', '🥉'] + ['4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
        embed = discord.Embed(title='⭐ Classement XP', color=discord.Color.gold())

        for i, (uid, udata) in enumerate(ranking[:10]):
            m = interaction.guild.get_member(int(uid))
            name = m.display_name if m else f'User ({uid})'
            lv = level_from_xp(udata.get('xp', 0))
            embed.add_field(
                name=f'{medals[i]} {name}',
                value=f'Niveau **{lv}** · `{udata.get("xp", 0):,} XP`',
                inline=False,
            )

        if not ranking:
            embed.description = 'Aucune donnée.'
        await interaction.response.send_message(embed=embed)

    # ── /levels config ─────────────────────────────────
    levels_group = app_commands.Group(name='levels', description='Configuration du système de niveaux')

    @levels_group.command(name='setchannel', description='Canal pour les annonces de level-up')
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(canal='Canal ou "none" pour désactiver')
    async def setchannel(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        cfg = _load_cfg()
        gid = str(interaction.guild.id)
        cfg.setdefault(gid, {})
        cfg[gid]['levelup_channel'] = canal.id if canal else None
        _save_cfg(cfg)
        msg = f'✅ Annonces de level-up dans {canal.mention}.' if canal else '✅ Annonces de level-up désactivées.'
        await interaction.response.send_message(msg, ephemeral=True)

    @levels_group.command(name='setrole', description='Attribue un rôle à un niveau donné')
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(niveau='Le niveau requis', role='Rôle à donner')
    async def setrole(self, interaction: discord.Interaction,
                      niveau: app_commands.Range[int, 1, 200], role: discord.Role):
        cfg = _load_cfg()
        gid = str(interaction.guild.id)
        cfg.setdefault(gid, {}).setdefault('level_roles', {})
        cfg[gid]['level_roles'][str(niveau)] = role.id
        _save_cfg(cfg)
        await interaction.response.send_message(
            f'✅ {role.mention} sera attribué au niveau **{niveau}**.', ephemeral=True
        )

    @levels_group.command(name='reset', description='Remet à zéro l\'XP d\'un membre')
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(membre='Le membre à reset')
    async def reset(self, interaction: discord.Interaction, membre: discord.Member):
        data = _load()
        gid = str(interaction.guild.id)
        uid = str(membre.id)
        if gid in data and uid in data[gid]:
            data[gid][uid] = {'xp': 0, 'level': 0, 'messages': 0, 'last_xp': None}
            _save(data)
        await interaction.response.send_message(f'✅ XP de {membre.mention} remis à zéro.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(Levels(bot))
