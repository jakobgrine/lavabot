import config
from bot import Bot
from help_command import CustomHelpCommand

cfg = config.load_config()

bot = Bot(command_prefix=cfg.get('command_prefix'),
          help_command=CustomHelpCommand())
bot.config = cfg

for ext in cfg.get('active_extensions', []):
    bot.load_extension(ext)

bot.run(cfg.get('discord_token'))
