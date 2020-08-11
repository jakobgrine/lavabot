import asyncio
import async_timeout
from collections import deque
from . import converters
import copy
import datetime
import discord
from discord.ext import commands, menus
import re
import wavelink


class PlayerControl(menus.Menu):

    def __init__(self, player, *args, **kwargs):
        super().__init__(*args, **kwargs, timeout=None)

        self.player = player

    def get_context(self, payload: discord.RawReactionActionEvent):
        ctx = copy.copy(self.ctx)
        ctx.author = payload.member
        return ctx

    def reaction_check(self, payload: discord.RawReactionActionEvent):
        if payload.message_id != self.message.id:
            return False
        if payload.event_type == 'REACTION_ADD' and payload.member.bot:
            return False
        if payload.emoji not in self.buttons:
            return False
        return True

    async def do(self, payload: discord.RawReactionActionEvent,
                 command_name: str):
        if payload.event_type != 'REACTION_ADD':
            return
        await self.message.remove_reaction(payload.emoji, payload.member)

        ctx = self.get_context(payload)
        ctx.command = self.bot.get_command(command_name)
        await self.bot.invoke(ctx)

    @menus.button('\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}')
    async def do_pause_play(self, payload: discord.RawReactionActionEvent):
        await self.do(payload, 'resume' if self.player.is_paused else 'pause')

    @menus.button('\N{BLACK SQUARE FOR STOP}')
    async def do_stop(self, payload: discord.RawReactionActionEvent):
        await self.do(payload, 'stop')

    @menus.button('\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}')
    async def do_skip(self, payload: discord.RawReactionActionEvent):
        await self.do(payload, 'skip')

    @menus.button(
        '\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS WITH CIRCLED ONE OVERLAY}'
    )
    async def do_repeat(self, payload: discord.RawReactionActionEvent):
        await self.do(payload, 'repeat')

    # @menus.button('\N{GAME DIE}')
    # async def do_shuffle(self, payload: discord.RawReactionActionEvent):
    #     await self.do(payload, 'shuffle')

    # @menus.button('\N{CLOSED MAILBOX WITH LOWERED FLAG}')
    # async def do_disconnect(self, payload: discord.RawReactionActionEvent):
    #     await self.do(payload, 'disconnect')


class Player(wavelink.Player):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.context: commands.Context = kwargs.get('context', None)

        self.updating = False

        self.queue = deque()
        self.repeat_one = False

        self.now_playing_message: discord.Message = None
        self.control_menu: PlayerControl = None

    async def next_track(self):
        """Play the next track in the queue."""
        if self.is_playing:
            return

        if len(self.queue) < 1:
            await self.destroy()
            return

        track = self.queue.popleft()
        await self.play(track)

        await self.update_now_playing_message()

    async def update_now_playing_message(self):
        """Update the information in the 'now playing' message or send new a one."""
        if self.updating:
            return

        track = self.current
        if track is None:
            return

        self.updating = True

        print(track.duration)
        duration = converters.format_timedelta(milliseconds=track.duration)
        embed = discord.Embed(title='Now Playing',
                              description=f'[{track.title}]({track.uri})',
                              timestamp=track.requested_at)
        embed.set_thumbnail(url=track.thumbnail_url)
        embed.add_field(name='Duration', value=duration, inline=True)
        embed.set_footer(text=f'Requested by {track.requester}',
                         icon_url=track.requester.avatar_url)

        if not self.is_connected:
            embed.add_field(name='State', value='Disconnected', inline=True)
        elif self.is_paused:
            embed.add_field(name='State', value='Paused', inline=True)

        if self.repeat_one:
            embed.add_field(name='Repeat', value='Enabled', inline=True)

        if not self.now_playing_message:
            self.now_playing_message = await self.context.send(embed=embed)

            self.control_menu = PlayerControl(player=self,
                                              message=self.now_playing_message)
            await self.control_menu.start(self.context)
        else:
            await self.now_playing_message.edit(embed=embed)

        self.updating = False

    async def destroy(self):
        """Delete the 'now playing' message and destroy the player."""
        if self.now_playing_message:
            self.control_menu.stop()
            self.control_menu = None

            await self.now_playing_message.delete()
            self.now_playing_message = None

        try:
            await super().destroy()
        except KeyError:
            pass
