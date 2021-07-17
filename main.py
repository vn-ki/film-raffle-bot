import asyncio
import discord
import logging
import random
import copy
import re
import os
import functools

from discord.ext import commands

from config import CONFIG
from lb_bot import get_movie_title
from db import Database, Raffle

from commands.userdata import Userdata

client = discord.Client()

db = Database(
    CONFIG["DATABASE"]["db-name"],
    CONFIG["DATABASE"]["db-host"],
    CONFIG["DATABASE"]["db-username"],
    CONFIG["DATABASE"]["db-password"],
    debug=os.getenv("DEBUG", False),
)


class MyClient(commands.Bot):
    def __init__(self, raffle_channel_id, raffle_role_id, *args, **kwargs):
        self.raffle_channel_id = raffle_channel_id
        self.raffle_role_id = raffle_role_id
        super().__init__(*args, **kwargs)

        self.emoji_for_role = discord.PartialEmoji(name='🎞')
        self.raffle_rolled = False

        # ID of the message that can be reacted to to add/remove a role.
        self.role_message_id = 0

    async def clear_raffle_role(self, guild):
        raffle_role = guild.get_role(self.raffle_role_id)
        tasks = [asyncio.create_task(member.remove_roles(
            raffle_role)) for member in raffle_role.members]
        if tasks:
            await asyncio.wait(tasks)

    def prettyprint_movie(self, movie_title):
        """
        Converts movie title year to movie title (year)
        """
        split = movie_title.rsplit(' ', 1)
        if len(split) < 2:
            return movie_title
        year = split[1]
        if re.fullmatch(r'\d{4}', year):
            return f'{split[0]} ({year})'
        return movie_title

    async def send_all_reccs(self):
        raffle_channel = self.get_channel(
            CONFIG["GUILD"]["all-recs-channel-id"])
        recs = await db.get_all_reccs()
        if len(recs) == 0:
            return
        roll_msg = ''
        for rec in recs:
            if rec.recomm == None:
                continue
            d_sender = self.get_user(int(rec.sender.user_id))
            d_receiver = self.get_user(int(rec.receiver.user_id))
            if d_sender == None or d_receiver == None:
                logging.error(
                    "sender or receiver not found. this shouldnt happen really.")
                continue

            movie_title = self.prettyprint_movie(rec.recomm)

            roll_msg += f'{d_sender.name} » {d_receiver.name} | {movie_title}\n'
            if len(roll_msg) > 1950:
                await raffle_channel.send(roll_msg)
                roll_msg = ''

        if len(roll_msg) > 0:
            await raffle_channel.send(roll_msg)

    async def ping_user(self, guild, user1, user2):
        member = guild.get_member(user1.id)
        raffle_channel = guild.get_channel(self.raffle_channel_id)

        if member is None:
            return
        lb_user1 = await db.get_user(user1.id)
        lb_user2 = await db.get_user(user2.id)
        message = f"""
__**Film Raffle Assignment**__
The time has come! Please provide your recommendation in the r/Letterboxd server within 24 hours of this message.

**You’ve been paired with:** {user2.mention} (if you cannot see the username check the pinned message in {raffle_channel.mention})
""".lstrip()
        # XXX: What if the message goes past the 2000 char limit
        # TODO: Fix that
        if lb_user2:
            if lb_user2.lb_username != None:
                message += f"**Their Letterboxd username is: {lb_user2.lb_username}**\n"
            if lb_user2.note:
                message += f"**Additional notes: {lb_user2.note}**\n"

            if lb_user1 and lb_user1.lb_username:
                if lb_user2.lb_username:
                    message += f'You can use lb-compare to quickly filter films you’ve seen that they haven’t: https://lb-compare.herokuapp.com/{lb_user1.lb_username}/vs/{lb_user2.lb_username}\n'
            else:
                message += '\n**Be sure to add your letterboxd username using `!setlb` command.**\n'

        message += f'\nTo submit your recommendation, head to the r/Letterboxd server {raffle_channel.mention} channel and use the `!f` command. Remember to tag your partner and let them know why you chose the film!'

        await user1.send(message)

    def create_random_mapping(self, users):
        """
        Creates a random mapping between users

        This creates a ring of users. The algo does this by shuffling the user list
        and adding an edge from ith user to i+1 th user if i!=n. For the last user, an edge
        is added to the first user.
        """
        # users would be Discord usernames
        random.shuffle(users)
        randomized_list = []
        for i in range(len(users)-1):
            randomized_list.append((users[i], users[i+1]))
        randomized_list.append((users[-1], users[0]))
        return randomized_list

    def raffle_entries_to_list(self, raffle_entries):
        entry_map = {}
        for entry in raffle_entries:
            entry_map[entry.sender_id] = entry.receiver_id
        first = raffle_entries[0].sender_id
        lst = [first]
        curr = entry_map[first]
        while curr != first:
            lst.append(curr)
            curr = entry_map[curr]
        return lst

    async def create_user_if_not_exist(self, user):
        dbuser = await db.get_user(user.id)
        if dbuser is None:
            await db.add_user(user.id)
            await user.send(CONFIG["CHAT"]["DM_INTRO"])

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Gives a role based on a reaction emoji."""
        if not self.check_emoji_payload(payload):
            return

        guild = self.get_guild(payload.guild_id)

        role = guild.get_role(self.raffle_role_id)
        if role is None:
            logging.error("could not find role to add")
            return
        await self.create_user_if_not_exist(payload.member)
        try:
            await payload.member.add_roles(role)
        except discord.HTTPException:
            logging.error("error while adding role")
            raise

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """
        Removes a role based on a reaction emoji.
        """
        if not self.check_emoji_payload(payload):
            return

        guild = self.get_guild(payload.guild_id)
        role = guild.get_role(self.raffle_role_id)
        if role is None:
            logging.error("role is not defined")
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            logging.warning(f"member of id '{payload.user_id}' not found")
            return False

        try:
            await member.remove_roles(role)
        except discord.HTTPException:
            pass

    def check_emoji_payload(self, payload: discord.RawReactionActionEvent) -> bool:
        """
        Check if emoji is the one we care about and all it's properties are correct.
        """
        # only care about the message
        if payload.message_id != self.role_message_id:
            return False
        # dont add role to the bot
        if payload.member == self.user:
            return False

        if payload.emoji != self.emoji_for_role:
            logging.warning(f"payload emoji does not match: {payload.emoji}")
            return False

        guild = self.get_guild(payload.guild_id)
        if guild is None:
            logging.error("guild of f{payload.guild_id} not found")
            return False

        return True


intents = discord.Intents.default()
intents.members = True

raffle_channel_id = CONFIG["GUILD"]["film-raffle-channel-id"]
raffle_role_id = CONFIG["GUILD"]["film-raffle-role-id"]

bot = MyClient(raffle_channel_id, raffle_role_id, command_prefix='!', intents=intents)


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
        return ctx.channel.id == raffle_channel_id
    return commands.check(predicate)


def typing_indicator():
    def wrapper(func):
        @functools.wraps(func)
        async def wrapped(ctx, *args):
            async with ctx.typing():
                return await func(ctx, *args)
        return wrapped
    return wrapper


async def silent_pin_message(message: discord.Message):
    try:
        await message.pin()
    except discord.Forbidden:
        logging.warn("don't have perms for pinning message")


# TODO: use discord.py Cogs for these commands
@bot.command(name='fr-start')
@privileged()
@only_in_raffle_channel()
@typing_indicator()
async def raffle_start(ctx):
    """
    Starts the film raffle. Sends a message with a reaction to join.
    """
    # clear all existing ones
    await bot.clear_raffle_role(ctx.guild)
    await unpin_all_bot_messages(ctx)

    raffle_channel = bot.get_channel(bot.raffle_channel_id)
    emoji = bot.get_emoji(774310027472404490)
    if not emoji:
        emoji = ''
    new_message = await raffle_channel.send(f"React to me! {emoji}")
    await new_message.add_reaction(emoji=bot.emoji_for_role)
    await silent_pin_message(new_message)
    bot.role_message_id = new_message.id
    bot.raffle_rolled = False


async def send_roll_msg(map_list, channel):
    pin_tasks = []
    roll_msg = ''
    for pair in map_list:
        # Doesn't ping users
        roll_msg += '{} » {}\n'.format(pair[0].mention, pair[1].mention)
        # This length is due to Discord forbidding messages greater than 2k chars
        if len(roll_msg) > 1950:
            message = await channel.send(roll_msg)
            pin_tasks.append(asyncio.create_task(silent_pin_message(message)))
            roll_msg = ''

    if len(roll_msg) > 0:
        message = await channel.send(roll_msg)
        pin_tasks.append(asyncio.create_task(silent_pin_message(message)))
    await asyncio.wait(pin_tasks)


async def unpin_all_bot_messages(ctx):
    pins = await ctx.channel.pins()
    tasks = []
    for message in pins:
        if message.author == bot.user:
            tasks.append(asyncio.create_task(message.unpin()))
    if tasks:
        await asyncio.wait(tasks)


@bot.command(name='fr-roll')
@privileged()
@only_in_raffle_channel()
async def roll_raffle(ctx):
    """
    Roll the raffle. **DANGER** This clears all existing raffle entries. Use `dump-recs` first.
    """
    await db.clear_raffle_db()
    guild = ctx.guild
    raffle_role = guild.get_role(bot.raffle_role_id)
    users = [member for member in raffle_role.members if not member.bot]
    if len(users) < 2:
        await ctx.channel.send("Not enough users for rolling the raffle.")
        return
    emoji = bot.get_emoji(774310027359158273)
    if not emoji:
        emoji = ''
    await ctx.channel.send(f"The Senate knows what's best for you. {emoji}")
    rando_list = bot.create_random_mapping(users)
    await send_roll_msg(rando_list, ctx.channel)

    await db.add_raffle_entries([
        Raffle(sender_id=str(pair[0].id), receiver_id=str(pair[1].id), recomm=None)
        for pair in rando_list
    ])
    # TODO: Put chat in cfg
    await ctx.channel.send("That's all folks! If there's an issue contact the mods, otherwise have fun!")
    bot.raffle_rolled = True

    ping_tasks = [bot.ping_user(guild, pair[0], pair[1])
                  for pair in rando_list]
    await asyncio.wait(ping_tasks)


def get_entry_map(raffle_entries):
    entry_map = {}
    for entry in raffle_entries:
        entry_map[entry.sender_id] = entry.receiver_id
    return entry_map

@bot.command(name='fr-reroll')
@privileged()
@only_in_raffle_channel()
async def reroll(ctx):
    """
    Removes the role from MIA person and assigns the role to their raffle partner if they are not MIA.
    """
    if not bot.raffle_rolled:
        await ctx.channel.send("Cannot re-roll before rolling.")
        return

    guild = ctx.guild
    raffle_role = guild.get_role(raffle_role_id)
    mia_members = raffle_role.members
    mia_member_id_set = set([str(member.id) for member in mia_members])

    raffle_entries = await db.get_all_reccs()
    entry_map = get_entry_map(raffle_entries)
    entry_list = bot.raffle_entries_to_list(raffle_entries)
    await db.remove_all_raffle_entries_by_users([str(member.id) for member in mia_members])

    new_entry_list = [uid for uid in entry_list if uid not in mia_member_id_set]
    new_pairings = []
    i = 0
    tasks = []

    for i in range(-1, len(new_entry_list)-1):
        curr = new_entry_list[i]
        next_ = new_entry_list[i+1]
        if entry_map[curr] != next_:
            tasks.append(asyncio.create_task(db.add_raffle_entry(curr, next_)))
            new_pairings.append((ctx.guild.get_member(int(curr)), ctx.guild.get_member(int(next_))))

    for pair in new_pairings:
        tasks.append(asyncio.create_task(pair[0].add_roles(raffle_role)))
        tasks.append(asyncio.create_task(ping_user(guild, pair[0], pair[1])))
    if new_pairings:
        await send_roll_msg(new_pairings, ctx.channel)
    else:
        await ctx.channel.send("No one to pair")

    if tasks:
        await asyncio.wait(tasks)

@bot.command(name='dump-recs')
@only_in_raffle_channel()
@privileged()
@typing_indicator()
async def dump_reccs(ctx):
    """
    Pretty prints all the reccomendations till now.
    """
    await bot.send_all_reccs()


@bot.command(name='warn-mia')
@only_in_raffle_channel()
@privileged()
@typing_indicator()
async def warn_mia(ctx):
    """
    Warn people who are MIA by pinging them.
    """
    # TODO: handle 2000 character limit
    raffle_role = ctx.guild.get_role(raffle_role_id)
    raffle_channel = bot.get_channel(raffle_channel_id)
    message = '**Please provide film raffle reccomendations to your raffle partner**\n\n'

    for member in raffle_role.members:
        message += f'{member.mention}\n'
        if len(message) > 1950:
            await raffle_channel.send(message)
            message = ''
    if len(message) > 0:
        await raffle_channel.send(message)


@bot.command(name='f', aliases=['film', 'kino'])
@only_in_raffle_channel()
async def recc_intercept(ctx, *, movie_query):
    if not bot.raffle_rolled:
        return
    movie_title = ''
    try:
        movie_title = await get_movie_title(movie_query)
    except Exception as e:
        logging.error(f"error occured while getting '{movie_query}'")

    if movie_title == '':
        movie_title = movie_query

    raffle_role = ctx.guild.get_role(raffle_role_id)
    await ctx.author.remove_roles(raffle_role)
    await db.recomm_movie(ctx.author.id, movie_title)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.channel.send("Command is missing a required argument.")
    elif isinstance(error, commands.CheckFailure):
        logging.warn("Check failed.")
    elif isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.CommandInvokeError):
        await ctx.channel.send("Command crashed.")
        raise error
    else:
        raise error


bot.add_cog(Userdata(db))

async def main():
    await db.init()
    await bot.start(CONFIG["BOT"]["bot-token"])

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        loop.run_until_complete(bot.close())
        # cancel all tasks lingering
    finally:
        loop.close()
# bot.run(CONFIG["BOT"]["bot-token"])
