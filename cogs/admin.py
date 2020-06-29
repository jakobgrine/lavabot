import discord
from discord.ext import commands, menus

# class Confirm(menus.Menu):

#     def __init__(self, content):
#         super().__init__(timeout=5, delete_message_after=True)
#         self.content = content
#         self.result = None

#     async def send_initial_message(self, ctx: commands.Context, channel):
#         return await channel.send(self.content)

#     @menus.button('\N{WHITE HEAVY CHECK MARK}')
#     async def do_confirm(self, payload: discord.RawReactionActionEvent):
#         self.result = True
#         self.stop()

#     @menus.button('\N{CROSS MARK}')
#     async def do_deny(self, payload: discord.RawReactionActionEvent):
#         self.result = False
#         self.stop()

#     async def prompt(self, ctx: commands.Context):
#         await self.start(ctx, wait=True)
#         return self.result


class Admin(commands.Cog):

    @commands.command()
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context):
        """Shut the bot down."""
        # confirm = await Confirm('Shut down the bot?').prompt(ctx)
        await ctx.message.delete()

        # if not confirm:
        #     return

        await ctx.bot.change_presence(status=discord.Status.offline)

        music_cog = ctx.bot.get_cog('Music')
        if music_cog:
            await music_cog.stop_nodes()

        await ctx.bot.logout()

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx: commands.Context, extension: str):
        """Hot reload an extension."""
        if not extension in ctx.bot.extensions:
            await ctx.send(f':x: Extension `{extension}` not found.',
                           delete_after=5)
            return

        ctx.bot.reload_extension(extension)
        await ctx.send(f':recycle: Reloaded `{extension}`.', delete_after=5)


def setup(bot: commands.Bot):
    bot.add_cog(Admin())
