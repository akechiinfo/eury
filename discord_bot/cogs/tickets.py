import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select, Modal, TextInput
import json
import os
import asyncio
from datetime import datetime, timezone

# ─────────────────────── helpers ───────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
TICKETS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'tickets.json')
COUNTER_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'counter.json')


def _legal_buttons() -> list[Button]:
    """Retourne les boutons ToS + Confidentialité si configurés."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        legal = cfg.get('legal', {})
        buttons = []
        tos = legal.get('tos_url', '')
        prv = legal.get('privacy_url', '')
        if tos and not tos.startswith('https://TON'):
            buttons.append(Button(label='📜 Conditions', url=tos, style=discord.ButtonStyle.link, row=1))
        if prv and not prv.startswith('https://TON'):
            buttons.append(Button(label='🔒 Confidentialité', url=prv, style=discord.ButtonStyle.link, row=1))
        return buttons
    except Exception:
        return []


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(data):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_tickets():
    os.makedirs(os.path.dirname(TICKETS_PATH), exist_ok=True)
    if os.path.exists(TICKETS_PATH):
        with open(TICKETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_tickets(data):
    os.makedirs(os.path.dirname(TICKETS_PATH), exist_ok=True)
    with open(TICKETS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def next_ticket_number():
    os.makedirs(os.path.dirname(COUNTER_PATH), exist_ok=True)
    if os.path.exists(COUNTER_PATH):
        with open(COUNTER_PATH, 'r') as f:
            data = json.load(f)
    else:
        data = {'count': 0}
    data['count'] += 1
    with open(COUNTER_PATH, 'w') as f:
        json.dump(data, f)
    return data['count']


TICKET_CATEGORIES = {
    'support':      {'label': '🛠️ Support Général',  'emoji': '🛠️', 'color': discord.Color.blue()},
    'bug':          {'label': '🐛 Rapport de Bug',   'emoji': '🐛', 'color': discord.Color.red()},
    'partnership':  {'label': '🤝 Partenariat',      'emoji': '🤝', 'color': discord.Color.green()},
    'payment':      {'label': '💳 Paiement',         'emoji': '💳', 'color': discord.Color.gold()},
    'other':        {'label': '📋 Autre',            'emoji': '📋', 'color': discord.Color.greyple()},
}

# ────────────────────── transcript ──────────────────────

async def generate_transcript(channel: discord.TextChannel) -> discord.File:
    messages = []
    async for msg in channel.history(limit=500, oldest_first=True):
        messages.append(msg)

    now = datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')

    rows = ''
    for msg in messages:
        ts = msg.created_at.strftime('%d/%m/%Y %H:%M')
        avatar = msg.author.display_avatar.url if msg.author.display_avatar else ''
        content = discord.utils.escape_mentions(msg.content or '')
        content = content.replace('\n', '<br>')
        for a in msg.attachments:
            if a.content_type and a.content_type.startswith('image/'):
                content += f'<br><img src="{a.url}" style="max-width:400px;border-radius:4px;">'
            else:
                content += f'<br><a href="{a.url}">{a.filename}</a>'
        for e in msg.embeds:
            title = e.title or ''
            desc = e.description or ''
            content += f'<br><div class="embed"><strong>{title}</strong><br>{desc}</div>'

        rows += f"""
        <div class="msg">
          <img src="{avatar}" class="avatar">
          <div class="content">
            <span class="author">{msg.author.display_name}</span>
            <span class="ts">{ts}</span>
            <div class="text">{content}</div>
          </div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Transcript — #{channel.name}</title>
<style>
  body{{background:#36393f;color:#dcddde;font-family:'Segoe UI',sans-serif;margin:0;padding:20px}}
  h1{{color:#fff;border-bottom:2px solid #7289da;padding-bottom:10px}}
  .info{{color:#72767d;font-size:13px;margin-bottom:20px}}
  .msg{{display:flex;gap:12px;margin:10px 0;padding:8px;border-radius:4px}}
  .msg:hover{{background:#3e4147}}
  .avatar{{width:40px;height:40px;border-radius:50%;flex-shrink:0}}
  .content{{flex:1}}
  .author{{font-weight:700;color:#fff;margin-right:8px}}
  .ts{{color:#72767d;font-size:12px}}
  .text{{margin-top:4px;line-height:1.5;word-break:break-word}}
  .embed{{background:#2f3136;border-left:4px solid #7289da;padding:8px 12px;border-radius:4px;margin-top:4px}}
  a{{color:#00aff4}}
</style>
</head>
<body>
<h1>📋 Transcript — #{channel.name}</h1>
<div class="info">Généré le {now} · {len(messages)} messages</div>
{''.join(rows) if rows else '<p style="color:#72767d">Aucun message.</p>'}
</body>
</html>"""

    buf = html.encode('utf-8')
    return discord.File(fp=__import__('io').BytesIO(buf), filename=f'transcript-{channel.name}.html')

# ─────────────────────── modals ─────────────────────────

class TicketReasonModal(Modal, title='Ouvrir un ticket'):
    reason = TextInput(
        label='Décris ton problème',
        style=discord.TextStyle.paragraph,
        placeholder='Ex: J\'ai un problème avec…',
        min_length=10,
        max_length=500,
    )

    def __init__(self, category: str):
        super().__init__()
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await create_ticket(interaction, self.category, str(self.reason))


class CloseReasonModal(Modal, title='Fermer le ticket'):
    reason = TextInput(
        label='Raison de fermeture (optionnel)',
        style=discord.TextStyle.short,
        placeholder='Ex: Problème résolu',
        required=False,
        max_length=200,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await close_ticket(interaction, str(self.reason) or 'Aucune raison fournie')

# ─────────────────────── views ──────────────────────────

class CategorySelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=info['label'],
                value=key,
                emoji=info['emoji'],
            )
            for key, info in TICKET_CATEGORIES.items()
        ]
        super().__init__(
            placeholder='📩 Choisis une catégorie…',
            options=options,
            custom_id='ticket:category_select',
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        await interaction.response.send_modal(TicketReasonModal(category))


class TicketPanelView(View):
    # NON PERSISTANT (pas enregistré dans add_view)
    def __init__(self):
        super().__init__(timeout=0)
        self.add_item(CategorySelect())
        for btn in _legal_buttons():
            self.add_item(btn)


class TicketControlsView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🔒 Fermer', style=discord.ButtonStyle.red, custom_id='ticket:close')
    async def close_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CloseReasonModal())

    @discord.ui.button(label='✋ Claim', style=discord.ButtonStyle.blurple, custom_id='ticket:claim')
    async def claim_btn(self, interaction: discord.Interaction, button: Button):
        cfg = load_config()
        support_role_id = cfg['ticket_settings'].get('support_role_id')

        if support_role_id:
            role = interaction.guild.get_role(int(support_role_id))
            if role and role not in interaction.user.roles:
                await interaction.response.send_message(
                    '❌ Seul le staff peut claim un ticket.', ephemeral=True
                )
                return

        tickets = load_tickets()
        ch_id = str(interaction.channel.id)
        if ch_id not in tickets:
            await interaction.response.send_message('❌ Canal non reconnu.', ephemeral=True)
            return

        if tickets[ch_id].get('claimed_by'):
            await interaction.response.send_message(
                f'❌ Ticket déjà claim par <@{tickets[ch_id]["claimed_by"]}>.', ephemeral=True
            )
            return

        tickets[ch_id]['claimed_by'] = interaction.user.id
        save_tickets(tickets)

        embed = discord.Embed(
            description=f'✋ Ticket claim par {interaction.user.mention}',
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label='📋 Transcript', style=discord.ButtonStyle.grey, custom_id='ticket:transcript')
    async def transcript_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer(ephemeral=True)
        file = await generate_transcript(interaction.channel)
        await interaction.followup.send('📋 Voici le transcript :', file=file, ephemeral=True)


class DeleteConfirmView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🗑️ Supprimer définitivement', style=discord.ButtonStyle.red, custom_id='ticket:delete_confirm')
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message('🗑️ Suppression dans 3 secondes…')
        await asyncio.sleep(3)
        tickets = load_tickets()
        ch_id = str(interaction.channel.id)
        tickets.pop(ch_id, None)
        save_tickets(tickets)
        await interaction.channel.delete(reason='Ticket supprimé')

    @discord.ui.button(label='Annuler', style=discord.ButtonStyle.grey, custom_id='ticket:delete_cancel')
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message('❌ Suppression annulée.', ephemeral=True)
        self.stop()

# ─────────────────── ticket logic ───────────────────────

async def create_ticket(interaction: discord.Interaction, category: str, reason: str):
    cfg = load_config()
    ts = cfg['ticket_settings']
    guild = interaction.guild
    user = interaction.user

    tickets = load_tickets()
    user_open = [
        t for t in tickets.values()
        if t.get('author_id') == user.id and t.get('status') == 'open'
    ]
    max_t = ts.get('max_tickets_per_user', 1)
    if len(user_open) >= max_t:
        await interaction.followup.send(
            f'❌ Tu as déjà **{max_t}** ticket(s) ouvert(s). Ferme-le avant d\'en ouvrir un nouveau.',
            ephemeral=True,
        )
        return

    cat_info = TICKET_CATEGORIES.get(category, TICKET_CATEGORIES['other'])
    ticket_num = next_ticket_number()
    channel_name = f'ticket-{ticket_num:04d}-{user.display_name[:15].lower().replace(" ", "-")}'

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
        ),
        guild.me: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }

    support_role_id = ts.get('support_role_id')
    if support_role_id:
        role = guild.get_role(int(support_role_id))
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                attach_files=True,
                manage_messages=True,
            )

    category_channel = None
    if ts.get('category_id'):
        category_channel = guild.get_channel(int(ts['category_id']))

    channel = await guild.create_text_channel(
        name=channel_name,
        overwrites=overwrites,
        category=category_channel,
        topic=f'Ticket #{ticket_num:04d} | {cat_info["label"]} | {user}',
        reason=f'Ticket ouvert par {user}',
    )

    tickets[str(channel.id)] = {
        'channel_id': channel.id,
        'author_id': user.id,
        'author_name': str(user),
        'category': category,
        'reason': reason,
        'number': ticket_num,
        'status': 'open',
        'claimed_by': None,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'guild_id': guild.id,
    }
    save_tickets(tickets)

    embed = discord.Embed(
        title=f'{cat_info["emoji"]} Ticket #{ticket_num:04d} — {cat_info["label"]}',
        description=(
            f'Bonjour {user.mention} ! 👋\n\n'
            f'**Catégorie :** {cat_info["label"]}\n'
            f'**Raison :** {reason}\n\n'
            f'Le staff va te répondre dès que possible.\n'
            f'Pour fermer ce ticket, clique sur 🔒 **Fermer**.'
        ),
        color=cat_info['color'],
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.set_footer(text=f'Ticket #{ticket_num:04d}')

    view = TicketControlsView()
    msg = await channel.send(
        content=f'{user.mention}' + (f' | <@&{support_role_id}>' if support_role_id else ''),
        embed=embed,
        view=view,
    )
    await msg.pin()

    await interaction.followup.send(
        f'✅ Ton ticket a été créé : {channel.mention}', ephemeral=True
    )

    await send_ticket_log(interaction.client, guild, tickets[str(channel.id)], action='open', actor=user)


async def close_ticket(interaction: discord.Interaction, reason: str):
    tickets = load_tickets()
    ch_id = str(interaction.channel.id)

    if ch_id not in tickets:
        await interaction.followup.send('❌ Ce canal n\'est pas un ticket.', ephemeral=True)
        return

    ticket = tickets[ch_id]
    if ticket['status'] == 'closed':
        await interaction.followup.send('❌ Ce ticket est déjà fermé.', ephemeral=True)
        return

    ticket['status'] = 'closed'
    ticket['closed_by'] = interaction.user.id
    ticket['close_reason'] = reason
    ticket['closed_at'] = datetime.now(timezone.utc).isoformat()
    save_tickets(tickets)

    file = await generate_transcript(interaction.channel)

    cfg = load_config()
    ts_ch_id = cfg['ticket_settings'].get('transcript_channel_id')
    transcript_msg = None
    if ts_ch_id:
        ts_channel = interaction.guild.get_channel(int(ts_ch_id))
        if ts_channel:
            transcript_msg = await ts_channel.send(
                content=f'📋 Transcript — #{interaction.channel.name}', file=file
            )

    embed = discord.Embed(
        title='🔒 Ticket fermé',
        description=(
            f'**Fermé par :** {interaction.user.mention}\n'
            f'**Raison :** {reason}\n\n'
            f'Ce ticket sera supprimé dans **5 secondes**.\n'
            + (f'[📋 Transcript]({transcript_msg.jump_url})' if transcript_msg else '')
        ),
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc),
    )
    view = DeleteConfirmView()
    await interaction.channel.send(embed=embed, view=view)

    author = interaction.guild.get_member(ticket['author_id'])
    if author:
        await interaction.channel.set_permissions(author, send_messages=False)

    await send_ticket_log(interaction.client, interaction.guild, ticket, action='close', actor=interaction.user)

    await asyncio.sleep(5)
    try:
        tickets = load_tickets()
        tickets.pop(ch_id, None)
        save_tickets(tickets)
        await interaction.channel.delete(reason='Ticket fermé automatiquement')
    except discord.NotFound:
        pass


async def send_ticket_log(bot, guild, ticket_data, action: str, actor: discord.Member):
    cfg = load_config()
    log_ch_id = cfg['ticket_settings'].get('log_channel_id')
    if not log_ch_id:
        return
    log_channel = guild.get_channel(int(log_ch_id))
    if not log_channel:
        return

    cat = ticket_data.get('category', 'other')
    cat_info = TICKET_CATEGORIES.get(cat, TICKET_CATEGORIES['other'])

    if action == 'open':
        color = discord.Color.green()
        title = '📩 Ticket Ouvert'
    else:
        color = discord.Color.red()
        title = '🔒 Ticket Fermé'

    embed = discord.Embed(title=title, color=color, timestamp=datetime.now(timezone.utc))
    embed.add_field(name='Numéro', value=f'#{ticket_data["number"]:04d}', inline=True)
    embed.add_field(name='Catégorie', value=cat_info['label'], inline=True)
    embed.add_field(name='Auteur', value=f'<@{ticket_data["author_id"]}>', inline=True)
    embed.add_field(name='Acteur', value=actor.mention, inline=True)
    embed.add_field(name='Raison', value=ticket_data.get('reason', '—'), inline=False)
    if action == 'close':
        embed.add_field(name='Raison fermeture', value=ticket_data.get('close_reason', '—'), inline=False)
    embed.set_footer(text=f'ID auteur: {ticket_data["author_id"]}')

    await log_channel.send(embed=embed)

# ─────────────────────── cog ────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Persistent views (sans boutons URL)
        self.bot.add_view(TicketControlsView())
        self.bot.add_view(DeleteConfirmView())

    tickets_group = app_commands.Group(name='ticket', description='Commandes du système de tickets')

    @tickets_group.command(name='setup', description='Configure le panel de tickets dans ce canal')
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_setup(self, interaction: discord.Interaction):
        cfg = load_config()
        legal = cfg.get('legal', {})
        tos_url = legal.get('tos_url', '')
        prv_url = legal.get('privacy_url', '')

        legal_line = ''
        links = []
        if tos_url and not tos_url.startswith('https://TON'):
            links.append(f'[Conditions d\'utilisation]({tos_url})')
        if prv_url and not prv_url.startswith('https://TON'):
            links.append(f'[Politique de confidentialité]({prv_url})')
        if links:
            legal_line = '\n\n> 📜 En ouvrant un ticket, tu acceptes nos ' + ' et notre '.join(links) + '.'

        embed = discord.Embed(
            title='📩 Support — Ouvre un Ticket',
            description=(
                '**Bienvenue sur le support !**\n\n'
                'Sélectionne la catégorie qui correspond à ta demande '
                'dans le menu ci-dessous pour créer un ticket privé.\n\n'
                '🛠️ Support Général · 🐛 Bug · 🤝 Partenariat · 💳 Paiement · 📋 Autre\n\n'
                '> ⚠️ N\'ouvre pas de ticket pour rien.'
                + legal_line
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text='Clique sur le menu pour commencer')

        view = TicketPanelView()
        msg = await interaction.channel.send(embed=embed, view=view)

        cfg['ticket_settings']['panel_channel_id'] = interaction.channel.id
        cfg['ticket_settings']['panel_message_id'] = msg.id
        save_config(cfg)

        await interaction.response.send_message('✅ Panel de tickets créé !', ephemeral=True)

    @tickets_group.command(name='config', description='Configure les paramètres du système de tickets')
    @app_commands.describe(
        categorie='Catégorie Discord pour les tickets',
        log_channel='Canal pour les logs',
        support_role='Rôle du staff',
        transcript_channel='Canal pour les transcripts',
        max_tickets='Nombre max de tickets par utilisateur',
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_config(
        self,
        interaction: discord.Interaction,
        categorie: discord.CategoryChannel = None,
        log_channel: discord.TextChannel = None,
        support_role: discord.Role = None,
        transcript_channel: discord.TextChannel = None,
        max_tickets: app_commands.Range[int, 1, 5] = None,
    ):
        cfg = load_config()
        ts = cfg['ticket_settings']
        changed = []

        if categorie:
            ts['category_id'] = categorie.id
            changed.append(f'Catégorie → {categorie.mention}')
        if log_channel:
            ts['log_channel_id'] = log_channel.id
            changed.append(f'Logs → {log_channel.mention}')
        if support_role:
            ts['support_role_id'] = support_role.id
            changed.append(f'Rôle staff → {support_role.mention}')
        if transcript_channel:
            ts['transcript_channel_id'] = transcript_channel.id
            changed.append(f'Transcripts → {transcript_channel.mention}')
        if max_tickets is not None:
            ts['max_tickets_per_user'] = max_tickets
            changed.append(f'Max tickets → {max_tickets}')

        save_config(cfg)

        if changed:
            desc = '\n'.join(f'✅ {c}' for c in changed)
        else:
            desc = 'Aucun paramètre modifié.'

        embed = discord.Embed(title='⚙️ Configuration Tickets', description=desc, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tickets_group.command(name='status', description='Affiche la configuration actuelle')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_status(self, interaction: discord.Interaction):
        cfg = load_config()
        ts = cfg['ticket_settings']
        tickets = load_tickets()
        open_count = sum(1 for t in tickets.values() if t.get('status') == 'open')

        def fmt(val, prefix='<#'):
            return f'{prefix}{val}>' if val else '`Non configuré`'

        embed = discord.Embed(title='⚙️ Statut Tickets', color=discord.Color.blurple())
        embed.add_field(name='Catégorie', value=fmt(ts.get('category_id'), '<#'), inline=True)
        embed.add_field(name='Canal logs', value=fmt(ts.get('log_channel_id')), inline=True)
        embed.add_field(name='Transcripts', value=fmt(ts.get('transcript_channel_id')), inline=True)
        embed.add_field(
            name='Rôle staff',
            value=f'<@&{ts["support_role_id"]}>' if ts.get('support_role_id') else '`Non configuré`',
            inline=True,
        )
        embed.add_field(name='Max / user', value=str(ts.get('max_tickets_per_user', 1)), inline=True)
        embed.add_field(name='Tickets ouverts', value=str(open_count), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tickets_group.command(name='add', description='Ajoute un utilisateur au ticket actuel')
    @app_commands.describe(membre='Le membre à ajouter')
    async def ticket_add(self, interaction: discord.Interaction, membre: discord.Member):
        tickets = load_tickets()
        if str(interaction.channel.id) not in tickets:
            await interaction.response.send_message('❌ Ce canal n\'est pas un ticket.', ephemeral=True)
            return

        await interaction.channel.set_permissions(
            membre,
            read_messages=True,
            send_messages=True,
            attach_files=True,
        )
        embed = discord.Embed(
            description=f'✅ {membre.mention} a été ajouté au ticket par {interaction.user.mention}.',
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @tickets_group.command(name='remove', description='Retire un utilisateur du ticket actuel')
    @app_commands.describe(membre='Le membre à retirer')
    async def ticket_remove(self, interaction: discord.Interaction, membre: discord.Member):
        tickets = load_tickets()
        if str(interaction.channel.id) not in tickets:
            await interaction.response.send_message('❌ Ce canal n\'est pas un ticket.', ephemeral=True)
            return

        ticket = tickets[str(interaction.channel.id)]
        if membre.id == ticket.get('author_id'):
            await interaction.response.send_message('❌ Tu ne peux pas retirer l\'auteur du ticket.', ephemeral=True)
            return

        await interaction.channel.set_permissions(membre, overwrite=None)
        embed = discord.Embed(
            description=f'✅ {membre.mention} a été retiré du ticket par {interaction.user.mention}.',
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)

    @tickets_group.command(name='close', description='Ferme le ticket actuel')
    @app_commands.describe(raison='Raison de la fermeture')
    async def ticket_close(self, interaction: discord.Interaction, raison: str = 'Aucune raison fournie'):
        tickets = load_tickets()
        if str(interaction.channel.id) not in tickets:
            await interaction.response.send_message('❌ Ce canal n\'est pas un ticket.', ephemeral=True)
            return
        await interaction.response.defer()
        await close_ticket(interaction, raison)

    @tickets_group.command(name='delete', description='Supprime le ticket actuel immédiatement')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_delete(self, interaction: discord.Interaction):
        tickets = load_tickets()
        ch_id = str(interaction.channel.id)
        if ch_id not in tickets:
            await interaction.response.send_message('❌ Ce canal n\'est pas un ticket.', ephemeral=True)
            return

        embed = discord.Embed(
            title='⚠️ Supprimer le ticket',
            description='Es-tu sûr de vouloir supprimer ce ticket ? Cette action est **irréversible**.',
            color=discord.Color.red(),
        )
        view = DeleteConfirmView()
        await interaction.response.send_message(embed=embed, view=view)

    @tickets_group.command(name='list', description='Liste tous les tickets ouverts')
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_list(self, interaction: discord.Interaction):
        tickets = load_tickets()
        open_tickets = [t for t in tickets.values() if t.get('status') == 'open']

        if not open_tickets:
            await interaction.response.send_message('📭 Aucun ticket ouvert.', ephemeral=True)
            return

        embed = discord.Embed(
            title=f'📋 Tickets ouverts ({len(open_tickets)})',
            color=discord.Color.blurple(),
        )
        for t in open_tickets[:20]:
            cat = TICKET_CATEGORIES.get(t['category'], {})
            claim = f' · Claim: <@{t["claimed_by"]}>' if t.get('claimed_by') else ''
            embed.add_field(
                name=f'#{t["number"]:04d} — {cat.get("label", t["category"])}',
                value=f'<@{t["author_id"]}> · <#{t["channel_id"]}>{claim}',
                inline=False,
            )

        if len(open_tickets) > 20:
            embed.set_footer(text=f'… et {len(open_tickets) - 20} autres')

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
