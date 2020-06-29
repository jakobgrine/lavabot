from discord.ext import commands


class CancelExecution(commands.CommandError):
    """Error raised when a command should be stopped from executing any further."""
    pass
