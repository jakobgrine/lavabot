import datetime
from discord.ext import commands
from .utils import parse_timedelta


class TimeSpanConverter(commands.Converter):

    async def convert(self, ctx: commands.Context,
                      argument: str) -> datetime.timedelta:
        timedelta = parse_timedelta(argument)
        if timedelta is None:
            raise commands.BadArgument(f'Timespan "{argument}" is invalid')

        return timedelta
