import asyncio
import discord
import logging
import random
import copy
import re
import os
import csv
import functools
from datetime import datetime, timedelta, timezone
from io import StringIO

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
logger = logging.getLogger('raffle_bot')


class MyClient(commands.Bot):
    def __init__(self, raffle_channel_id, raffle_role_id, *args, **kwargs):
        self.raffle_channel_id = raffle_channel_id
        self.raffle_role_id = raffle_role_id
        super().__init__(*args, **kwargs)

        self.emoji_for_role = discord.PartialEmoji(name='🎟️')
        self.raffle_rolled = False

        # ID of the message that can be reacted to to add/remove a role.
        self.role_message_id = 0

    async def clear_raffle_role(self, guild):
        raffle_role = guild.get_role(self.raffle_role_id)
        tasks = [asyncio.create_task(member.remove_roles(
            raffle_role)) for member in raffle_role.members]
        if tasks:
            await asyncio.wait(tasks)

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

    def raffle_entries_to_orig_entry_list(self, raffle_entries):
        # TODO: this is duplication of above code. fix this.
        lookup = {}
        entry_map = {}
        for entry in raffle_entries:
            lookup[entry.sender_id] = entry
            entry_map[entry.sender_id] = entry.receiver_id
        first = raffle_entries[0].sender_id
        lst = [lookup[first]]
        curr = entry_map[first]
        while curr != first:
            lst.append(lookup[curr])
            curr = entry_map[curr]
        return lst

    async def create_user_if_not_exist(self, user):
        dbuser = await db.get_user(user.id)
        if dbuser is None:
            await db.add_user(user.id)
        if dbuser is None or dbuser.lb_username is None:
            await user.send(CONFIG["CHAT"]["DM_INTRO"])

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Gives a role based on a reaction emoji."""
        if not await self.check_emoji_payload(payload):
            return

        guild = self.get_guild(payload.guild_id)

        role = guild.get_role(self.raffle_role_id)
        if role is None:
            logger.error("could not find role to add")
            return
        await self.create_user_if_not_exist(payload.member)
        try:
            await payload.member.add_roles(role)
            logger.info(f'role assigned to {payload.member.name}')
        except discord.HTTPException:
            logger.error("error while adding role")
            raise

    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """
        Removes a role based on a reaction emoji.
        """
        if not await self.check_emoji_payload(payload):
            return

        guild = self.get_guild(payload.guild_id)
        role = guild.get_role(self.raffle_role_id)
        if role is None:
            logger.error("role is not defined")
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            logger.warning(f"member of id '{payload.user_id}' not found")
            return False

        try:
            await member.remove_roles(role)
            logger.info(f'role removed from {member.name}')
        except discord.HTTPException:
            pass

    async def check_emoji_payload(self, payload: discord.RawReactionActionEvent) -> bool:
        """
        Check if emoji is the one we care about and all it's properties are correct.
        """
        db_guild = await db.get_guild(payload.guild_id)
        logger.info(f'got emoji payload: db_guild={db_guild}')
        if db_guild.raffle_message_id is None:
            logger.info(f'guild={payload.guild_id} no raffle message_id')
            return
        # only care about the message
        if payload.message_id != int(db_guild.raffle_message_id):
            logger.info(f'payload message id={payload.message_id} does not match raffle_message_id={db_guild.raffle_message_id}')
            return False
        # dont add role to the bot
        if payload.member == self.user:
            return False

        if payload.emoji != self.emoji_for_role:
            logger.warning(f"payload emoji does not match: {payload.emoji}")
            return False

        guild = self.get_guild(payload.guild_id)
        if guild is None:
            logger.error("guild of f{payload.guild_id} not found")
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

def only_in_debug_channel():
    async def predicate(ctx):
        return ctx.channel.id == CONFIG["GUILD"].get("debug-channel-id") or ctx.channel.id == raffle_channel_id
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
        logger.warn("don't have perms for pinning message")


# TODO: use discord.py Cogs for these commands
@bot.command(name='fr-start')
@privileged()
@only_in_raffle_channel()
@typing_indicator()
async def raffle_start(ctx):
    """
    Starts the film raffle. Sends a message with a reaction to join.
    """
    await add_guild_if_not_exists(ctx.guild.id)
    await db.guild_set_raffle_rolled(ctx.guild.id, False)
    # clear all existing ones
    await bot.clear_raffle_role(ctx.guild)
    await unpin_all_bot_messages(ctx)

    guild = ctx.guild
    raffle_role = guild.get_role(bot.raffle_role_id)
    raffle_channel = bot.get_channel(bot.raffle_channel_id)

    today = datetime.now(timezone.utc)
    coming_monday = today + timedelta(days=((7 + (0 - today.weekday())) % 7))
    coming_monday = coming_monday.replace(hour=13, minute=0, second=0, microsecond=0)
    coming_monday_timestamp = int(coming_monday.timestamp())

    new_message = await raffle_channel.send(f"""__**Film Raffle Signups**__
Want to participate in the next round? Simply react {bot.emoji_for_role} below to join! After you react, please double-check that you have the “{raffle_role.mention}” role. If you don’t, please unreact and react again until you have the role. Please note that you must be able to provide a film recommendation within 24 hours of the raffle, which will occur on **<t:{coming_monday_timestamp}:F>**. Once you have received your film suggestion, we ask that you watch and review (even just a few thoughts) before the next raffle in two weeks' time. Keep an eye out for a DM for more info. Happy raffling!""")
    await new_message.add_reaction(emoji=bot.emoji_for_role)
    await silent_pin_message(new_message)
    await db.start_raffle(guild.id, new_message.id)


async def add_guild_if_not_exists(guild_id):
    guild = await db.get_guild(guild_id)
    if guild is None:
        await db.add_guild(guild_id)

async def send_roll_msg(map_list, channel):
    pin_tasks = []
    roll_msg = ''
    for pair in map_list:
        if pair[0] is None or pair[1] is None:
            # XXX: this is a hack :'
            logger.error(f'pair[0]={pair[0]} pair[1]={pair[1]}')
            user = None
            if pair[0]:
                user = pair[0].mention
            if pair[1]:
                user = pair[1].mention
            # one of the user couldnt be found, because they probably left he server
            roll_msg += '{user} could not be matched because "reasons". Contact the bot admin and threat him to write better code.'
            continue
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
    guild = ctx.guild
    raffle_role = guild.get_role(bot.raffle_role_id)
    users = [member for member in raffle_role.members if not member.bot]
    if len(users) < 2:
        await ctx.channel.send("Not enough users for rolling the raffle.")
        return

    await db.clear_raffle_db(guild.id)
    emoji = bot.get_emoji(774310027359158273)
    if not emoji:
        emoji = ''
    await ctx.channel.send(f"The Senate knows what's best for you. {emoji}")
    rando_list = bot.create_random_mapping(users)
    await send_roll_msg(rando_list, ctx.channel)

    await db.add_raffle_entries([
        Raffle(guild_id=str(guild.id), sender_id=str(pair[0].id), receiver_id=str(pair[1].id), recomm=None)
        for pair in rando_list
    ])
    # TODO: Put chat in cfg
    await ctx.channel.send("That's all folks! If there's an issue contact the mods, otherwise have fun!")

    await db.guild_set_raffle_rolled(guild.id, True)
    await db.guild_remove_raffle_message_id(guild.id)

    ping_tasks = [bot.ping_user(guild, pair[0], pair[1])
                  for pair in rando_list]
    await asyncio.wait(ping_tasks)


def get_entry_map(raffle_entries):
    entry_map = {}
    for entry in raffle_entries:
        entry_map[entry.sender_id] = entry.receiver_id
    return entry_map


@bot.command(name='debug')
@privileged()
@only_in_debug_channel()
async def debug(ctx):
    guild = ctx.guild

    raffle_role = guild.get_role(raffle_role_id)
    # mia_members = raffle_role.members
    mia_members = await db.get_mia(guild.id)
    mia_member_id_set = set([str(member.sender_id) for member in mia_members])
    logger.info(f'mia_member_id_set={mia_member_id_set}')

    raffle_entries = await db.get_all_reccs(guild.id)
    for entry in raffle_entries:
        if ctx.guild.get_member(int(entry.sender_id)) is None:
            logger.info(f'user with id={entry.sender_id} left the server')
            mia_member_id_set.add(str(entry.sender_id))
    logger.info(f'final mia_member_id_set={mia_member_id_set}')

    message = 'MIA\n'
    for mia in mia_member_id_set:
        try:
            user = await bot.fetch_user(mia)
        except discord.NotFound:
            continue
        message += f'{user.name}\n'
    await ctx.channel.send(message)

@bot.command(name='fr-reroll')
@privileged()
@only_in_raffle_channel()
async def reroll(ctx):
    """
    Removes the role from MIA person and assigns the role to their raffle partner if they are not MIA.
    """
    if not (await db.get_guild(ctx.guild.id)).raffle_rolled:
        await ctx.channel.send("Cannot re-roll before rolling.")
        return

    guild = ctx.guild
    raffle_role = guild.get_role(raffle_role_id)
    # mia_members = raffle_role.members
    mia_members = await db.get_mia(guild.id)
    mia_member_id_set = set([str(member.sender_id) for member in mia_members])

    raffle_entries = await db.get_all_reccs(guild.id)
    for entry in raffle_entries:
        if ctx.guild.get_member(int(entry.sender_id)) is None:
            mia_member_id_set.add(str(entry.sender_id))

    if len(raffle_entries) - len(mia_member_id_set) < 2:
        await ctx.channel.send("Too few people to re-roll.")
        return

    entry_map = get_entry_map(raffle_entries)
    entry_list = bot.raffle_entries_to_list(raffle_entries)
    await db.remove_all_raffle_entries_by_users(guild.id, [member for member in mia_member_id_set])

    new_entry_list = [uid for uid in entry_list if uid not in mia_member_id_set]
    new_pairings = []
    i = 0
    tasks = []

    for i in range(-1, len(new_entry_list)-1):
        curr = new_entry_list[i]
        next_ = new_entry_list[i+1]
        if entry_map[curr] != next_:
            tasks.append(asyncio.create_task(db.add_raffle_entry(guild.id, curr, next_)))
            new_pairings.append((ctx.guild.get_member(int(curr)), ctx.guild.get_member(int(next_))))

    for pair in new_pairings:
        tasks.append(asyncio.create_task(pair[0].add_roles(raffle_role)))
        tasks.append(asyncio.create_task(bot.ping_user(guild, pair[0], pair[1])))
    if new_pairings:
        await send_roll_msg(new_pairings, ctx.channel)
    else:
        await ctx.channel.send("No one to pair")

    if tasks:
        await asyncio.wait(tasks)

@bot.command(name='dump-recs')
@only_in_debug_channel()
@privileged()
@typing_indicator()
async def dump_reccs(ctx):
    """
    Pretty prints all the recommendations till now.
    """
    recs = await db.get_all_reccs(ctx.guild.id)
    if len(recs) == 0:
        return
    roll_msg = ''
    csv_content = StringIO()
    csv_writer = csv.DictWriter(csv_content, fieldnames=['Position', 'Name', 'Year', 'Description'])
    csv_writer.writeheader()
    recs = bot.raffle_entries_to_orig_entry_list(recs)
    logger.info(f'dump-recs: recs={recs}')

    def linkify_user(name, lb_username):
        if lb_username is None:
            return name
        return f'<a href="https://letterboxd.com/{lb_username}">{name}</a>'
    for position, rec in enumerate(recs):
        if rec.recomm == None:
            logger.info('no reccom found so skipping')
            continue

        d_sender = bot.get_user(int(rec.sender.user_id))
        d_receiver = bot.get_user(int(rec.receiver.user_id))
        if d_sender == None or d_receiver == None:
            logger.error("sender or receiver not found. this shouldnt happen really.")
            continue

        movie_title = rec.recomm

        sender_name = d_sender.name
        if rec.sender.lb_username:
            sender_name += f' ({rec.sender.lb_username})'
        receiver_name = d_receiver.name
        if rec.receiver.lb_username:
            receiver_name += f' ({rec.receiver.lb_username})'
        roll_msg += f'{sender_name} » {receiver_name} | {movie_title}\n'

        # TODO: refactor
        movie_split = movie_title.rsplit('(', 1)
        if len(movie_split) == 2:
            movie, year = movie_split
        else:
            movie, year = movie_title, ''
        year = year.strip(')')
        if len(year) != 4:
            movie = movie_title
            year = ''
        sender_link = linkify_user(d_sender.name, rec.sender.lb_username)
        receiver_link = linkify_user(d_receiver.name, rec.receiver.lb_username)
        csv_writer.writerow({
            "Position": position,
            "Name": movie,
            "Year": year,
            "Description": f'{sender_link} » {receiver_link}'
        })

    csv_content.seek(0)
    await ctx.channel.send("", file=discord.File(StringIO(roll_msg), "recs.txt"))
    await ctx.channel.send("", file=discord.File(csv_content, "recs.csv"))


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
    message = '**Please provide film raffle recommendations to your raffle partner**\n\n'

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
    if not (await db.get_guild(ctx.guild.id)).raffle_rolled:
        return
    movie_title = ''
    raffle_channel = bot.get_channel(raffle_channel_id)
    try:
        movie_title = await get_movie_title(movie_query)
    except Exception as e:
        logger.error(f"error occured while getting '{movie_query}'")

    if movie_title == '':
        movie_title = movie_query

    raffle_role = ctx.guild.get_role(raffle_role_id)
    await ctx.author.remove_roles(raffle_role)
    await db.recomm_movie(ctx.guild.id, ctx.author.id, movie_title)
    raffle_entry = await db.get_raffle_entry_by_sender(ctx.guild.id, ctx.author.id)
    sender = ctx.guild.get_member(int(raffle_entry.sender_id))
    receiver = ctx.guild.get_member(int(raffle_entry.receiver_id))
    if receiver is None:
        await raffle_channel.send(f"Your raffle partner seems to have left the server. Guess they don't like you. Don't worry, I do :). So sit tight and wait for the re-rolling tomorrow.")
        return
    await raffle_channel.send(f'{sender.mention} recommended {receiver.mention} "{movie_title}"')


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.channel.send("Command is missing a required argument.")
    elif isinstance(error, commands.CheckFailure):
        logger.warn("Check failed.")
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
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(formatter)

    root = logging.getLogger('raffle_bot')
    root.setLevel(os.environ.get("LOGLEVEL", "DEBUG"))
    root.addHandler(handler)
    sqla = logging.getLogger('sqlalchemy.engine.Engine')
    sqla.setLevel("INFO")
    sqla.addHandler(handler)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        loop.run_until_complete(bot.close())
        # cancel all tasks lingering
    finally:
        loop.close()
# bot.run(CONFIG["BOT"]["bot-token"])
