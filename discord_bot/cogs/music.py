"""
Système Musique :
  play (YouTube/recherche), pause, resume, skip, stop, queue, nowplaying, volume, loop
  Nécessite FFmpeg installé sur la machine.
"""

import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import asyncio, yt_dlp, json, os
from collections import deque

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extractflat': False,
}

FFMPEG_OPTIONS = {
    'before_options': (
        '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
        '-loglevel warning'
    ),
    'options': '-vn -b:a 128k',
}


class Song:
    def __init__(self, data: dict, requester: discord.Member):
        self.title = data.get('title', 'Inconnu')
        self.url = data.get('webpage_url') or data.get('url', '')
        self.stream_url = data.get('url', '')
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail', '')
        self.requester = requester
        self.channel = data.get('channel', 'Inconnu')

    def fmt_duration(self) -> str:
        d = int(self.duration or 0)
        m, s = divmod(d, 60)
        h, m = divmod(m, 60)
        return f'{h:02d}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


class MusicPlayer:
    def __init__(self, guild_id: int, bot):
        self.guild_id = guild_id
        self.bot = bot
        self.queue: deque[Song] = deque()
        self.current: Song | None = None
        self.loop = False
        self.volume = 0.5
        self._vc: discord.VoiceClient | None = None
        self._text_channel: discord.TextChannel | None = None
        self._task: asyncio.Task | None = None

    def get_vc(self, guild: discord.Guild) -> discord.VoiceClient | None:
        return guild.voice_client

    async def play_next(self, guild: discord.Guild):
        vc = self.get_vc(guild)
        if not vc:
            return

        if self.loop and self.current:
            song = self.current
        elif self.queue:
            song = self.queue.popleft()
        else:
            self.current = None
            if self._text_channel:
                e = discord.Embed(description='✅ File d\'attente terminée.', color=discord.Color.grey())
                try:
                    await self._text_channel.send(embed=e)
                except Exception:
                    pass
            return

        self.current = song

        try:
            source = discord.FFmpegPCMAudio(song.stream_url, **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source, volume=self.volume)

            def after(err):
                asyncio.run_coroutine_threadsafe(self.play_next(guild), self.bot.loop)

            vc.play(source, after=after)

            if self._text_channel:
                embed = discord.Embed(
                    title='🎵 En lecture',
                    description=f'[{song.title}]({song.url})',
                    color=discord.Color.green(),
                )
                embed.add_field(name='Durée', value=song.fmt_duration(), inline=True)
                embed.add_field(name='Artiste', value=song.channel, inline=True)
                embed.add_field(name='Demandé par', value=song.requester.mention, inline=True)
                embed.add_field(name='🔁 Loop', value='Oui' if self.loop else 'Non', inline=True)
                embed.add_field(name='🔊 Volume', value=f'{int(self.volume * 100)}%', inline=True)
                if song.thumbnail:
                    embed.set_thumbnail(url=song.thumbnail)
                try:
                    await self._text_channel.send(embed=embed)
                except Exception:
                    pass
        except Exception as e:
            if self._text_channel:
                await self._text_channel.send(f'❌ Erreur de lecture : `{e}`')
            await self.play_next(guild)


_players: dict[int, MusicPlayer] = {}


def get_player(guild_id: int, bot) -> MusicPlayer:
    if guild_id not in _players:
        _players[guild_id] = MusicPlayer(guild_id, bot)
    return _players[guild_id]


async def ensure_voice(interaction: discord.Interaction) -> discord.VoiceClient | None:
    if not interaction.user.voice:
        await interaction.followup.send('❌ Tu dois être dans un canal vocal.', ephemeral=True)
        return None

    vc = interaction.guild.voice_client
    if vc and vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)
        return vc

    if not vc:
        try:
            vc = await interaction.user.voice.channel.connect()
        except Exception as e:
            await interaction.followup.send(f'❌ Impossible de rejoindre le canal : `{e}`', ephemeral=True)
            return None

    return vc


async def fetch_song(query: str, requester: discord.Member) -> Song | None:
    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            if not query.startswith('http'):
                query = f'ytsearch:{query}'
            data = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
            if 'entries' in data:
                data = data['entries'][0]
            return Song(data, requester)
        except Exception:
            return None


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction, error):
        msg = '❌ Erreur : ' + str(error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass

    # ── /play ──────────────────────────────────────────
    @app_commands.command(name='play', description='Joue une musique (URL YouTube ou recherche)')
    @app_commands.describe(query='URL ou titre de la chanson')
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        vc = await ensure_voice(interaction)
        if not vc:
            return

        player = get_player(interaction.guild.id, self.bot)
        player._text_channel = interaction.channel

        embed_load = discord.Embed(
            description=f'🔍 Recherche de `{query}`…',
            color=discord.Color.yellow(),
        )
        await interaction.followup.send(embed=embed_load)

        song = await fetch_song(query, interaction.user)
        if not song:
            await interaction.followup.send('❌ Aucun résultat trouvé.', ephemeral=True)
            return

        if vc.is_playing() or vc.is_paused():
            player.queue.append(song)
            embed = discord.Embed(
                title='📋 Ajouté à la file',
                description=f'[{song.title}]({song.url})',
                color=discord.Color.blurple(),
            )
            embed.add_field(name='Durée', value=song.fmt_duration(), inline=True)
            embed.add_field(name='Position', value=str(len(player.queue)), inline=True)
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            await interaction.followup.send(embed=embed)
        else:
            player.queue.append(song)
            await player.play_next(interaction.guild)

    # ── /skip ──────────────────────────────────────────
    @app_commands.command(name='skip', description='Passe à la chanson suivante')
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            await interaction.response.send_message('❌ Rien en lecture.', ephemeral=True)
            return
        vc.stop()
        await interaction.response.send_message('⏭️ Chanson suivante.', ephemeral=True)

    # ── /pause ─────────────────────────────────────────
    @app_commands.command(name='pause', description='Met la musique en pause')
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message('⏸️ Pause.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Rien en lecture.', ephemeral=True)

    # ── /resume ────────────────────────────────────────
    @app_commands.command(name='resume', description='Reprend la lecture')
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message('▶️ Reprise.', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Rien en pause.', ephemeral=True)

    # ── /stop ──────────────────────────────────────────
    @app_commands.command(name='stop', description='Arrête la musique et vide la file')
    async def stop(self, interaction: discord.Interaction):
        player = get_player(interaction.guild.id, self.bot)
        player.queue.clear()
        player.current = None
        player.loop = False
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()
        _players.pop(interaction.guild.id, None)
        await interaction.response.send_message('⏹️ Arrêté et déconnecté.', ephemeral=True)

    # ── /queue ─────────────────────────────────────────
    @app_commands.command(name='queue', description='Affiche la file d\'attente')
    async def queue_cmd(self, interaction: discord.Interaction):
        player = get_player(interaction.guild.id, self.bot)
        embed = discord.Embed(title='📋 File d\'attente', color=discord.Color.blurple())

        if player.current:
            embed.add_field(
                name='🎵 En lecture',
                value=f'[{player.current.title}]({player.current.url}) `{player.current.fmt_duration()}`',
                inline=False,
            )

        if player.queue:
            lines = []
            for i, s in enumerate(list(player.queue)[:15], 1):
                lines.append(f'`{i}.` [{s.title[:50]}]({s.url}) `{s.fmt_duration()}`')
            embed.add_field(name=f'Suivant ({len(player.queue)})', value='\n'.join(lines), inline=False)
            if len(player.queue) > 15:
                embed.set_footer(text=f'… et {len(player.queue) - 15} autres')
        else:
            if not player.current:
                embed.description = '📭 File vide.'

        embed.add_field(name='🔁 Loop', value='Oui' if player.loop else 'Non', inline=True)
        embed.add_field(name='🔊 Volume', value=f'{int(player.volume * 100)}%', inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /nowplaying ────────────────────────────────────
    @app_commands.command(name='nowplaying', description='Affiche la chanson en cours')
    async def nowplaying(self, interaction: discord.Interaction):
        player = get_player(interaction.guild.id, self.bot)
        if not player.current:
            await interaction.response.send_message('❌ Rien en lecture.', ephemeral=True)
            return

        s = player.current
        embed = discord.Embed(
            title='🎵 En cours de lecture',
            description=f'[{s.title}]({s.url})',
            color=discord.Color.green(),
        )
        embed.add_field(name='Durée', value=s.fmt_duration(), inline=True)
        embed.add_field(name='Artiste', value=s.channel, inline=True)
        embed.add_field(name='Demandé par', value=s.requester.mention, inline=True)
        if s.thumbnail:
            embed.set_thumbnail(url=s.thumbnail)
        await interaction.response.send_message(embed=embed)

    # ── /volume ────────────────────────────────────────
    @app_commands.command(name='volume', description='Règle le volume (0-150)')
    @app_commands.describe(niveau='Volume en % (0-150)')
    async def volume(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 0, 150]):
        vc = interaction.guild.voice_client
        player = get_player(interaction.guild.id, self.bot)
        player.volume = niveau / 100

        if vc and vc.source:
            vc.source.volume = player.volume

        await interaction.response.send_message(f'🔊 Volume : **{niveau}%**', ephemeral=True)

    # ── /loop ──────────────────────────────────────────
    @app_commands.command(name='loop', description='Active/désactive le loop')
    async def loop_cmd(self, interaction: discord.Interaction):
        player = get_player(interaction.guild.id, self.bot)
        player.loop = not player.loop
        status = 'activé 🔁' if player.loop else 'désactivé'
        await interaction.response.send_message(f'Loop {status}.', ephemeral=True)

    # ── /shuffle ───────────────────────────────────────
    @app_commands.command(name='shuffle', description='Mélange la file d\'attente')
    async def shuffle(self, interaction: discord.Interaction):
        import random
        player = get_player(interaction.guild.id, self.bot)
        if len(player.queue) < 2:
            await interaction.response.send_message('❌ Pas assez de chansons dans la file.', ephemeral=True)
            return
        q_list = list(player.queue)
        random.shuffle(q_list)
        player.queue = deque(q_list)
        await interaction.response.send_message(f'🔀 {len(player.queue)} chanson(s) mélangées.', ephemeral=True)

    # ── /remove ────────────────────────────────────────
    @app_commands.command(name='remove', description='Retire une chanson de la file (par position)')
    @app_commands.describe(position='Position dans la file (commence à 1)')
    async def remove(self, interaction: discord.Interaction, position: int):
        player = get_player(interaction.guild.id, self.bot)
        if position < 1 or position > len(player.queue):
            await interaction.response.send_message('❌ Position invalide.', ephemeral=True)
            return
        q_list = list(player.queue)
        removed = q_list.pop(position - 1)
        player.queue = deque(q_list)
        await interaction.response.send_message(
            f'🗑️ Retiré : **{removed.title}**', ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Music(bot))
