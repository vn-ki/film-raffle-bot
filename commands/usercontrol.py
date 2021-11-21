from discord.ext import commands
import discord


class Usercontrol(commands.Cog):
    def __init__(self, db):
        self.db = db

    @commands.command(name='fr-ban')
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
        await ctx.channel.send("Ho Ho Ho. You've been too naughty.")


    @commands.command(name='fr-unban')
    async def unban(self, ctx, *, member: discord.Member):
        """
        Unban a user. Good job on being nice.
        """
        naughty = await self.db.get_user_naughty(ctx.guild.id, member.id)
        if not naughty:
            await ctx.channel.send("User not on naughty list.")
            return
        await self.db.remove_user_from_naughty_list(ctx.guild.id, member.id)
        await ctx.channel.send("Good job getting off the naughty list.")
