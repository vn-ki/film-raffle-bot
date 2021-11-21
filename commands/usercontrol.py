from discord.ext import commands
import discord

from decorators import privileged, only_in_debug_channel


class Usercontrol(commands.Cog):
    def __init__(self, db):
        self.db = db

    @commands.command(name='fr-ban')
    @privileged()
    @only_in_debug_channel()
    async def ban(self, ctx, member: discord.Member, *, reason=None):
        """
        Ban a user from participating in the raffle. They can still shout in the server. !fr-ban @user
        """
        naughty = await self.db.get_user_naughty(ctx.guild.id, member.id)
        if naughty:
            await self.db.update_naughty_user(ctx.guild.id, member.id, reason)
            await ctx.channel.send("Naughty user reason updated.")
            return
        await self.db.add_user_to_naughty_list(ctx.guild.id, member.id, reason)
        await ctx.channel.send(f"Ho Ho Ho. You've been too naughty. {member.mention} banned from participating in raffle.")


    @commands.command(name='fr-unban')
    @privileged()
    @only_in_debug_channel()
    async def unban(self, ctx, *, member: discord.Member):
        """
        Unban a user. Good job on being nice.
        """
        naughty = await self.db.get_user_naughty(ctx.guild.id, member.id)
        if not naughty:
            await ctx.channel.send("User not on naughty list.")
            return
        await self.db.remove_user_from_naughty_list(ctx.guild.id, member.id)
        await ctx.channel.send(f"Good job getting off the naughty list. {member.mention} unbanned.")

    @commands.command(name='fr-naughty-list')
    @privileged()
    @only_in_debug_channel()
    async def naughty_list(self, ctx):
        """
        List the banned users.
        """
        naughty_list = await self.db.get_naughtly_list(ctx.guild.id)
        message = '**__Naughty list__**\n'
        for user in naughty_list:
            discord_user = ctx.guild.get_member(int(user.user_id))
            message += f'{discord_user.mention}'
            if user.reason:
                message += ": " + user.reason
            message += '\n'
        await ctx.channel.send(message)
