import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')

def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

config = load_config()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class TicketBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=config.get('prefix', '!'),
            intents=intents,
            help_command=None,
        )
        self.config = config

    async def setup_hook(self):
        cogs_dir = os.path.join(os.path.dirname(__file__), 'cogs')
        for filename in sorted(os.listdir(cogs_dir)):
            if filename.endswith('.py') and not filename.startswith('_'):
                ext = f'cogs.{filename[:-3]}'
                try:
                    await self.load_extension(ext)
                    print(f'  ✅ {filename}')
                except Exception as e:
                    print(f'  ❌ {filename}: {e}')

        guild_id = self.config.get('guild_id')
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f'✅ Commandes synchronisées sur le serveur {guild_id}')
        else:
            await self.tree.sync()
            print('✅ Commandes synchronisées globalement (peut prendre 1h)')

    async def on_ready(self):
        print(f'\n{"═" * 45}')
        print(f'  Bot     : {self.user}')
        print(f'  ID      : {self.user.id}')
        print(f'  Servers : {len(self.guilds)}')
        print(f'{"═" * 45}\n')
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name='📩 Tickets | /help',
            ),
        )

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send('❌ Tu n\'as pas la permission d\'utiliser cette commande.', ephemeral=True)
        else:
            raise error


bot = TicketBot()

if __name__ == '__main__':
    token = os.getenv('TOKEN')
    if not token:
        print('❌ Erreur : Remplis ton token dans le fichier .env')
        sys.exit(1)
    print('Chargement des extensions...')
    bot.run(token, log_handler=None)
