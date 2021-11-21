import functools

from discord.ext import commands

from config import CONFIG


def privileged():
    async def predicate(ctx):
        if ctx.guild == None:
            return False

        found_user_in_priv = False
        for role in CONFIG["GUILD"]["privileged-roles"]:
            priv_role = ctx.guild.get_role(role)
            if priv_role:
                if ctx.author in priv_role.members:
                    found_user_in_priv = True
                    break
        return found_user_in_priv
    return commands.check(predicate)


def only_in_raffle_channel():
    async def predicate(ctx):
        return ctx.channel.id == CONFIG["GUILD"]["film-raffle-channel-id"]
    return commands.check(predicate)

def only_in_debug_channel():
    async def predicate(ctx):
        return ctx.channel.id == CONFIG["GUILD"].get("debug-channel-id") or ctx.channel.id == CONFIG["GUILD"]["film-raffle-channel-id"]
    return commands.check(predicate)

def typing_indicator():
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(ctx, *args):
            async with ctx.typing():
                return await func(ctx, *args)
        return wrapped
    return wrapper
