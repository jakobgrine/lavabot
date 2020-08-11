from . import converters
import datetime
import discord
from discord.ext import commands, menus
from .errors import CancelExecution
from functools import reduce
import math
from .player import Player
import random
from .track import Track
import typing
import validators
import wavelink


class QueuePageSource(menus.ListPageSource):

    def __init__(self, entries):
        super().__init__(entries, per_page=15)

    async def format_page(self, menu, page_entries):
        offset = menu.current_page * self.per_page
        tracks = [
            f'{i+1}. [{x.title}]({x.uri})'
            for i, x in enumerate(page_entries, start=offset)
        ]
        text = '\n'.join(tracks)

        if len(text) >= 2048:
            return ':x: An error occured.'

        embed = discord.Embed(title='Queue', description=text)
        embed.set_footer(
            text=
            'The queue entries could change while this message is displayed.')
        if self.is_paginating():
            embed.add_field(name='Queue Length',
                            value=len(self.entries),
                            inline=True)

        return embed


class Vote(menus.Menu):

    def __init__(self, text: str, *, threshold: int, timeout: int):
        super().__init__(timeout=timeout, delete_message_after=True)
        self.text = text
        self.threshold = threshold

        self.upvotes = set()
        self.downvotes = set()

    def reaction_check(self, payload: discord.RawReactionActionEvent):
        if payload.message_id != self.message.id:
            return False
        if payload.user_id not in (self.bot.owner_id, self._author_id):
            return False
        if payload.emoji not in self.buttons:
            return False

        # player = self.ctx.bot.wavelink.get_player(payload.guild_id, cls=Player)
        # if not player.channel_id:
        #     return False

        # channel = self.ctx.bot.get_channel(int(player.channel_id))
        # if not channel:
        #     return False

        # if player.is_connected and payload.member not in channel.members:
        #     return False

        return True

    @property
    def count(self):
        return len(self.upvotes) - len(self.downvotes)

    @property
    def content(self):
        return f'{self.text} You have {self.timeout} seconds to vote with reactions.\nNow at **{self.count}** of **{self.threshold}**.'

    async def send_initial_message(self, ctx: commands.Context,
                                   channel: discord.abc.Messageable):
        return await channel.send(self.content)

    @menus.button('\N{THUMBS UP SIGN}')
    async def do_upvote(self, payload: discord.RawReactionActionEvent):
        if payload.event_type == 'REACTION_ADD' and payload.user_id not in self.downvotes:
            self.upvotes.add(payload.user_id)
        elif payload.event_type == 'REACTION_REMOVE':
            self.upvotes.discard(payload.user_id)

        if self.count >= self.threshold:
            self.stop()

        await self.message.edit(content=self.content)

    @menus.button('\N{THUMBS DOWN SIGN}')
    async def do_downvote(self, payload: discord.RawReactionActionEvent):
        if payload.event_type == 'REACTION_ADD' and payload.user_id not in self.upvotes:
            self.downvotes.add(payload.user_id)
        elif payload.event_type == 'REACTION_REMOVE':
            self.downvotes.discard(payload.user_id)

        if self.count >= self.threshold:
            self.stop()

        await self.message.edit(content=self.content)

    async def prompt(self, ctx: commands.Context):
        self.upvotes.add(ctx.author.id)

        if self.count >= self.threshold:
            return True

        await self.start(ctx, wait=True)
        return self.count >= self.threshold


async def is_privileged(ctx: commands.Context) -> bool:
    """Check whether the user is the bot owner, an admin or a DJ."""
    member = ctx.author
    guild = member.guild

    if guild.owner == member:
        return True

    app_info = await ctx.bot.application_info()
    if member == app_info.owner:
        return True

    role_id = ctx.bot.config.get('dj_roles', {}).get(str(guild.id))
    role = guild.get_role(role_id)
    if role and member in role.members:
        return True

    raise commands.CheckFailure('You are not allowed to use this command.')


class Music(commands.Cog, wavelink.WavelinkMixin):
    """Use this bot to play music in a voice channel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        if not hasattr(bot, 'wavelink'):
            bot.wavelink = wavelink.Client(bot=bot)

        bot.loop.create_task(self.start_nodes())

    async def start_nodes(self):
        """Connect to the lavalink nodes."""
        await self.bot.wait_until_ready()

        lavalink_nodes = self.bot.config.get('lavalink_nodes')

        for node_config in lavalink_nodes:
            identifier = node_config['identifier']
            try:
                node = self.bot.wavelink.get_node(identifier)
                if node:
                    await node.destroy()

                await self.bot.wavelink.initiate_node(**node_config)
            except wavelink.errors.NodeOccupied:
                print(f'Node "{identifier}" already exists')

    async def stop_nodes(self):
        if not self.bot.wavelink.nodes:
            return

        nodes = self.bot.wavelink.nodes.copy().values()
        for node in nodes:
            await node.destroy()

    @wavelink.WavelinkMixin.listener('on_track_stuck')
    @wavelink.WavelinkMixin.listener('on_track_end')
    @wavelink.WavelinkMixin.listener('on_track_exception')
    async def _on_player_stop(self, node: wavelink.Node, payload):
        if payload.player.repeat_one:
            payload.player.queue.appendleft(payload.track)

        await payload.player.next_track()

    async def cog_before_invoke(self, ctx: commands.Context):
        try:
            player = ctx.bot.wavelink.get_player(ctx.guild.id,
                                                 cls=Player,
                                                 context=ctx)
        except wavelink.errors.ZeroConnectedNodes:
            await ctx.send(f':x: An error occured. Try again later.',
                           delete_after=5)
            raise CancelExecution

        if not player.channel_id:
            return

        channel = ctx.bot.get_channel(int(player.channel_id))
        if not channel:
            return

        if (player.is_connected and ctx.author not in channel.members and
                not await is_privileged(ctx)):
            await ctx.send(
                f':x: You have to be in **{channel.name}** to use voice commands.',
                delete_after=5)
            raise CancelExecution

    @commands.command(aliases=['join', 'summon'])
    @commands.guild_only()
    @commands.check(is_privileged)
    async def connect(self, ctx: commands.Context, *,
                      channel: typing.Optional[discord.VoiceChannel]):
        """Join a voice channel or move to another one if already connected."""
        if channel is None:
            if ctx.author.voice:
                channel = ctx.author.voice.channel
            else:
                await ctx.send(
                    ':x: You have to be in a voice channel or specify one.',
                    delete_after=5)
                return

        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        await player.connect(channel.id)
        await ctx.send(f':thumbsup: Connected to **{channel.name}**.',
                       delete_after=5)

        await player.update_now_playing_message()

    @commands.command(aliases=['leave'])
    @commands.guild_only()
    @commands.check(is_privileged)
    async def disconnect(self, ctx: commands.Context):
        """Leave the current voice channel."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_connected:
            await ctx.send(':x: The bot is not connected to a voice channel.',
                           delete_after=5)
            return

        await player.disconnect()
        await ctx.send(':mailbox_with_no_mail: Disconnected.', delete_after=5)

        await player.update_now_playing_message()

    @commands.command(aliases=['search', 'enqueue'])
    @commands.guild_only()
    async def play(self, ctx: commands.Context, *, query: str):
        """Play a track from a URL or a search query."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if not validators.url(query):
            query = f"ytsearch:{query}"

        result = None
        counter = 0
        while result is None and counter < 10:
            result = await ctx.bot.wavelink.get_tracks(query)
            counter += 1

        if isinstance(result, wavelink.TrackPlaylist):
            result = result.tracks
        elif result:
            result = result[:1]
        else:
            await ctx.send(f':x: No results.', delete_after=5)
            return

        tracks = [Track(x.id, x.info, requester=ctx.author) for x in result]

        player.queue.extend(tracks)

        track_count = len(tracks)

        if not player.is_connected:
            if not ctx.author.voice:
                await ctx.send(':x: Neither you nor I are in a voice channel.',
                               delete_after=5)
                return

            await player.connect(ctx.author.voice.channel.id)

        if not player.is_playing:
            await player.next_track()
            track_count -= 1

        if track_count > 1:
            await ctx.send(f'Enqueued {track_count} tracks.', delete_after=5)
        elif track_count > 0:
            track = tracks[0]

            duration = converters.format_timedelta(milliseconds=track.duration)

            embed = discord.Embed(title='Enqueued',
                                  description=f'[{track.title}]({track.uri})',
                                  timestamp=track.requested_at)
            embed.set_thumbnail(url=track.thumbnail_url)
            embed.add_field(name='Duration', value=duration, inline=True)
            embed.add_field(name='Position In Queue',
                            value=len(player.queue),
                            inline=True)
            embed.set_footer(text=f'Requested by {track.requester}',
                             icon_url=track.requester.avatar_url)

            await ctx.send(embed=embed, delete_after=5)
        else:
            await ctx.message.delete()

    @commands.command()
    @commands.guild_only()
    @commands.check(is_privileged)
    async def stop(self, ctx: commands.Context):
        """Stop the player, clear the queue and leave the voice channel."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_playing:
            await ctx.send(':x: There is nothing playing at the moment.',
                           delete_after=5)
            return

        await player.destroy()
        await ctx.send(':stop_button: Stopped.', delete_after=5)

    @commands.command()
    @commands.guild_only()
    @commands.check(is_privileged)
    async def pause(self, ctx: commands.Context):
        """Pause the player."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_playing:
            await ctx.send(':x: There is nothing playing at the moment.',
                           delete_after=5)
            return

        if player.is_paused:
            await ctx.send(':x: The player is already paused.', delete_after=5)
            return

        await player.set_pause(True)
        await ctx.send(':pause_button: Paused.', delete_after=5)

        await player.update_now_playing_message()

    @commands.command(aliases=['continue'])
    @commands.guild_only()
    @commands.check(is_privileged)
    async def resume(self, ctx: commands.Context):
        """Resume the player if it is currently paused."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_playing:
            await ctx.send(':x: There is nothing playing at the moment.',
                           delete_after=5)
            return

        if not player.is_paused:
            await ctx.send(':x: The player is not paused.', delete_after=5)
            return

        await player.set_pause(False)
        await ctx.send(':arrow_forward: Resumed.', delete_after=5)

        await player.update_now_playing_message()

    @commands.command(aliases=['next'])
    @commands.guild_only()
    async def skip(self, ctx: commands.Context):
        """Skip the currently playing track."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_playing:
            await ctx.send(':x: There is nothing playing at the moment.',
                           delete_after=5)
            return

        try:
            await is_privileged(ctx)
        except commands.CheckFailure:
            channel = ctx.bot.get_channel(int(player.channel_id))
            if not player.is_connected or not channel:
                await ctx.send(
                    ':x: The bot is not connected to a voice channel.',
                    delete_after=5)
                return

            threshold = reduce(lambda a, x: a + 1
                               if not x.bot else a, channel.members, 0)
            if threshold > 2:
                threshold = math.ceil(threshold / 2)

            vote = Vote(f'Skip?', threshold=threshold, timeout=30)
            result = await vote.prompt(ctx)
            await ctx.message.delete()

            if not result:
                return

        await player.stop()
        await ctx.send(':track_next: Skipped.', delete_after=5)

    @commands.command()
    @commands.guild_only()
    @commands.check(is_privileged)
    async def seek(self, ctx: commands.Context,
                   position: converters.TimeSpanConverter):
        """Seek to a position of the currently playing track."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_playing:
            await ctx.send(':x: There is nothing playing at the moment.',
                           delete_after=5)
            return

        ms = position / datetime.timedelta(milliseconds=1)
        position_str = converters.format_timedelta(milliseconds=ms)
        await player.seek(ms)
        await ctx.send(f':vhs: Seeked to **{position_str}**.', delete_after=5)

    @commands.command()
    @commands.guild_only()
    @commands.check(is_privileged)
    async def volume(self, ctx: commands.Context, volume: int):
        """Set the volume of the player."""
        if volume < 0 or volume > 1000:
            await ctx.send(':x: The volume has to be between 0 and 1000.',
                           delete_after=5)
            return

        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        await player.set_volume(volume)
        await ctx.send(f':loud_sound: Volume set to **{volume}**.',
                       delete_after=5)

    @commands.command(aliases=['np', 'now', 'playing'])
    @commands.guild_only()
    async def nowplaying(self, ctx: commands.Context):
        """Show information about the currently playing track."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if not player.is_playing:
            await ctx.send(':x: There is nothing playing at the moment.',
                           delete_after=5)
            return

        track = player.current
        position = converters.format_timedelta(milliseconds=player.position)
        duration = converters.format_timedelta(milliseconds=track.duration)
        embed = discord.Embed(title='Now Playing',
                              description=f'[{track.title}]({track.uri})',
                              timestamp=track.requested_at)
        embed.set_thumbnail(url=track.thumbnail_url)
        embed.add_field(name='Position', value=position, inline=True)
        embed.add_field(name='Duration', value=duration, inline=True)
        embed.set_footer(text=f'Requested by {track.requester}',
                         icon_url=track.requester.avatar_url)

        await ctx.send(embed=embed, delete_after=5)

    @commands.command(aliases=['q'])
    @commands.guild_only()
    async def queue(self, ctx: commands.Context):
        """Show the entries of the queue."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if len(player.queue) < 1:
            await ctx.send('The queue is empty.', delete_after=5)
            return

        source = QueuePageSource(list(player.queue))
        pages = menus.MenuPages(source, delete_message_after=True)
        await pages.start(ctx, wait=True)
        await ctx.message.delete()

    @commands.command(aliases=['random', 'randomize', 'rand'])
    @commands.guild_only()
    @commands.check(is_privileged)
    async def shuffle(self, ctx: commands.Context):
        """Shuffle the queue."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)
        if len(player.queue) < 1:
            await ctx.send(':x: The queue is empty.', delete_after=5)
            return

        random.shuffle(player.queue)
        await ctx.send(':game_die: Shuffled queue.', delete_after=5)

    @commands.command(aliases=['loop'])
    @commands.guild_only()
    @commands.check(is_privileged)
    async def repeat(self, ctx: commands.Context,
                     enable: typing.Optional[bool]):
        """Toggle whether the playing track should be repeated."""
        player = ctx.bot.wavelink.get_player(ctx.guild.id, cls=Player)

        if enable is None:
            enable = not player.repeat_one

        text = 'enabled' if enable else 'disabled'

        if player.repeat_one == enable:
            await ctx.send(f':x: Repeat is already {text}.', delete_after=5)
            return

        player.repeat_one = enable
        await ctx.send(f':repeat_one: Repeat {text}.', delete_after=5)

        await player.update_now_playing_message()


def setup(bot: commands.Bot):
    bot.add_cog(Music(bot))
