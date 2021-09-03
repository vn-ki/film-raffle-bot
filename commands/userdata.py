from discord.ext import commands
import discord


class Userdata(commands.Cog):
    def __init__(self, db):
        self.db = db

    @commands.command()
    async def setlb(self, ctx, lb_username):
        """
        Use !setlb followed by your Letterboxd username to link your Letterboxd profile. This is mandatory.
        """
        user = await self.db.get_user(ctx.author.id)
        if user is None:
            await self.db.add_user(ctx.author.id, lb_username, None)
            await ctx.channel.send("Username set successfully")
        else:
            await self.db.update_user(ctx.author.id, lb_username=lb_username)
            await ctx.channel.send("Username updated successfully")

    @commands.command()
    async def setnotes(self, ctx, *, note):
        """
        Use !setnotes followed by any preferences you may have (streaming services, preferred length, genre/mood, etc.) This is optional.
        """
        user = await self.db.get_user(ctx.author.id)
        if user is None:
            await self.db.add_user(ctx.author.id, None, note)
            await ctx.channel.send("Note set successfully")
        else:
            await self.db.update_user(ctx.author.id, note=note)
            await ctx.channel.send("Note updated successfully")


    @commands.command()
    async def showinfo(self, ctx):
        """
        Shows the current lb username and notes.
        """
        user = await self.db.get_user(ctx.author.id)
        message = ''
        if user:
            if user.lb_username:
                message += f'**Letterboxd username:** {user.lb_username}\n'
            if user.note:
                message += f'**Note**: {user.note}'
        if message:
            await ctx.channel.send(message)
        else:
            await ctx.channel.send('No info set.')