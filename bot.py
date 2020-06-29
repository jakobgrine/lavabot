from discord.ext import commands
from cogs.music import errors
import sys
import traceback
import wavelink


class Context(commands.Context):

    async def send(self, content=None, *, both=True, **kwargs):
        ret = await super().send(content=content, **kwargs)
        delete_after = kwargs.get('delete_after', None)
        if delete_after is not None and both:
            await self.message.delete(delay=delete_after)
        return ret


class Bot(commands.Bot):

    async def get_context(self, message, *, cls=Context):
        return await super().get_context(message, cls=cls)

    async def on_command_error(self, ctx: commands.Context,
                               exception: commands.CommandError):
        if isinstance(exception, errors.CancelExecution):
            return

        traceback.print_exception(type(exception),
                                  exception,
                                  exception.__traceback__,
                                  file=sys.stderr)

        text = str(exception).replace('"', '`')
        await ctx.send(f':x: {text}', delete_after=5)
