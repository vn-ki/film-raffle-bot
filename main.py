import asyncio
import discord
import logging
import random
import copy

from discord.ext import commands

from config import CONFIG
from lb_bot import get_movie_title
from db import Database

client = discord.Client()

db = Database(
    CONFIG["DATABASE"]["db-name"],
    CONFIG["DATABASE"]["db-host"],
    CONFIG["DATABASE"]["db-username"],
    CONFIG["DATABASE"]["db-password"],
    debug=True,
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

    async def send_all_reccs(self):
        raffle_channel = self.get_channel(
            CONFIG["GUILD"]["all-recs-channel-id"])
        recs = db.get_all_reccs()
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

            roll_msg += f'{d_sender.name} » {d_receiver.name} | {rec.recomm}\n'
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
        lb_user1 = db.get_user(user1.id)
        lb_user2 = db.get_user(user2.id)
        message = f"""
__**Film Raffle Assignment**__
The time has come! Please provide your recommendation in the r/Letterboxd server within 24 hours of this message.

**You’ve been paired with:** {user2.mention}
""".lstrip()
        # XXX: What if the message goes past the 2000 char limit
        # TODO: Fix that
        if lb_user2:
            if lb_user2.lb_username != None:
                message += f"**Their Letterboxd username is: {lb_user2.lb_username}**\n"
            if lb_user2.note:
                message += f"**Additional notes: {lb_user2.note}**\n"

            if lb_user1 and lb_user1.lb_username and lb_user2.lb_username:
                message += f'You can use lb-compare to quickly filter films you’ve seen that they haven’t: https://lb-compare.herokuapp.com/{lb_user1.lb_username}/vs/{lb_user2.lb_username} .'
            else:
                message += '\n\nBe sure to add your letterboxd username using `!setlb` command.'

        message += f'\n\nTo submit your recommendation, head to the r/Letterboxd server {raffle_channel.mention} channel and use the `!f` command. Remember to tag your partner and let them know why you chose the film!'

        await user1.send(message)

    def create_random_mapping(self, users):
        """
        Creates a random mapping between users
        """
        # users would be Discord usernames
        random.shuffle(users)
        choose = copy.copy(users)
        randomized_list = []

        for member in users:
            members = copy.copy(users)
            members.pop(members.index(member))
            chosen = random.choice(list(set(choose) & set(members)))
            randomized_list.append((member, chosen))
            choose.pop(choose.index(chosen))
        return randomized_list

    async def create_user_if_not_exist(self, user):
        dbuser = db.get_user(user.id)
        if dbuser is None:
            db.add_user(user.id)
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

    def check_raffle_channel(self, payload) -> bool:
        # TODO: sanitize the input??
        # make the input id??
        return payload.channel.id == self.raffle_channel_id

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

@bot.command(name='fr-start')
@privileged()
@only_in_raffle_channel()
async def raffle_start(ctx):
    """
    Starts the film raffle. Sends a message with a reaction to join.
    """
    # clear all existing ones
    await bot.clear_raffle_role(ctx.guild)

    raffle_channel = bot.get_channel(bot.raffle_channel_id)
    new_message = await raffle_channel.send("React to me!")
    await new_message.add_reaction(emoji=bot.emoji_for_role)
    bot.role_message_id = new_message.id
    bot.raffle_rolled = False


@bot.command(name='fr-roll')
@privileged()
@only_in_raffle_channel()
async def roll_raffle(ctx):
    """
    Roll the raffle.
    """
    db.clear_raffle_db()
    guild = ctx.guild
    raffle_role = guild.get_role(bot.raffle_role_id)
    users = [member for member in raffle_role.members if not member.bot]
    if len(users) < 2:
        await ctx.channel.send("Not enough users for rolling the raffle.")
        return
    await ctx.channel.send("The Senate knows what's best for you. :dewit:")
    roll_msg = ''
    rando_list = bot.create_random_mapping(users)

    for pair in rando_list:
        db.add_raffle_entry(pair[0].id, pair[1].id)
        # Doesn't ping users
        roll_msg += '{} -> {}\n'.format(pair[0].mention, pair[1].mention)
        # This length is due to Discord forbidding messages greater than 2k chars
        if len(roll_msg) > 1950:
            await ctx.channel.send(roll_msg)
            roll_msg = ''

    if len(roll_msg) > 0:
        await ctx.channel.send(roll_msg)
    # TODO: Put chat in cfg
    await ctx.channel.send("That's all folks! If there's an issue contact the mods, otherwise have fun!")
    bot.raffle_rolled = True

    ping_tasks = [bot.ping_user(guild, pair[0], pair[1])
                  for pair in rando_list]
    await asyncio.wait(ping_tasks)

@bot.command(name='fr-role-swap')
@privileged()
@only_in_raffle_channel()
async def role_swap(ctx):
    guild = ctx.guild
    raffle_role = guild.get_role(raffle_role_id)
    mia_members = raffle_role.members
    mia_member_id_set = set([member.id for member in mia_members])
    async def assign_remove_role(member):
        await member.remove_roles(raffle_role)
        raffle = db.get_raffle_entry_by_sender(member.id)
        receiver_id = int(raffle.receiver_id)
        if receiver_id in mia_member_id_set:
            return
        receiver = guild.get_member(receiver_id)
        if not receiver:
            return
        await receiver.add_roles(raffle_role)

    tasks = [asyncio.create_task(assign_remove_role(member))
             for member in mia_members]
    if tasks:
        await asyncio.wait(tasks)
    await bot.send_all_reccs()

@bot.command(name='dump-reccs')
@only_in_raffle_channel()
@privileged()
async def dump_reccs(ctx):
    """
    Pretty prints all the reccomendations till now.
    """
    await bot.send_all_reccs()

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
    db.recomm_movie(ctx.author.id, movie_title)


@bot.command()
async def setlb(ctx, lb_username):
    """
    Use !setlb followed by your Letterboxd username to link your Letterboxd profile. This is mandatory.
    """
    user = db.get_user(ctx.author.id)
    if user is None:
        db.add_user(ctx.author.id, lb_username, None)
        await ctx.channel.send("Username set successfuly")
    else:
        db.update_user(ctx.author.id, lb_username=lb_username)
        await ctx.channel.send("Username updated successfuly")


@bot.command()
async def setnotes(ctx, *, note):
    """
    Use !setnotes followed by any preferences you may have (streaming services, preferred length, genre/mood, etc.) This is optional.
    """
    user = db.get_user(ctx.author.id)
    if user is None:
        db.add_user(ctx.author.id, None, note)
        await ctx.channel.send("Note set successfuly")
    else:
        db.update_user(ctx.author.id, note=note)
        await ctx.channel.send("Note updated successfuly")

bot.run(CONFIG["BOT"]["bot-token"])
