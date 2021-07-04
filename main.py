import discord
from configparser import ConfigParser
import logging
import random
import copy

cfg = ConfigParser()
cfg.read('cfg.ini')

client = discord.Client()


class MyClient(discord.Client):
    def __init__(self, raffle_channel_id, raffle_role_id, *args, **kwargs):
        self.raffle_channel_id = raffle_channel_id
        self.raffle_role_id = raffle_role_id
        super().__init__(*args, **kwargs)

        self.emoji_for_role = discord.PartialEmoji(name='🎞')

        # ID of the message that can be reacted to to add/remove a role.
        self.role_message_id = 0

    async def on_message(self, message):
        if message.author == self.user:
            return
        # TODO: check user perms
        print(self.raffle_channel_id)
        if message.content.startswith('!fr-start'):
            await self.start_film_raffle()
        elif message.content.startswith('!fr-roll'):
            await self.roll_film_raffle(message)

    async def start_film_raffle(self):
        """
        Starts the film raffle.
        Sends a message with the text with a reaction
        """
        raffle_channel = self.get_channel(self.raffle_channel_id)
        new_message = await raffle_channel.send("React to me!")
        await new_message.add_reaction(emoji=self.emoji_for_role)
        self.role_message_id = new_message.id

    async def roll_film_raffle(self, message):
        guild = message.guild
        await message.channel.send("The Senate knows what's best for you. :dewit:")
        raffle_role = guild.get_role(self.raffle_role_id)
        users = [member for member in raffle_role.members if not member.bot]
        roll_msg = ''
        rando_list = self.create_random_mapping(users)

        for pair in rando_list:
            # Doesn't ping users
            roll_msg += '{} -> {}\n'.format(pair[0].mention, pair[1].mention)
            # This length is due to Discord forbidding messages greater than 2k chars
            if len(roll_msg) > 1950:
                await message.channel.send(roll_msg)
                roll_msg = ''

        if len(roll_msg) > 0:
            await message.channel.send(roll_msg)
        # TODO: Put chat in cfg
        await message.channel.send("That's all folks! If there's an issue contact the mods, otherwise have fun!")

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

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Gives a role based on a reaction emoji."""
        if not self.check_emoji_payload(payload):
            return

        guild = self.get_guild(payload.guild_id)

        role = guild.get_role(self.raffle_role_id)
        if role is None:
            logging.error("could not find role to add")
            return

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

raffle_channel_id = int(cfg.get("GUILD", "film-raffle-channel-id"))
raffle_role_id = int(cfg.get("GUILD", "film-raffle-role-id"))

client = MyClient(raffle_channel_id, raffle_role_id, intents=intents)
client.run(cfg.get("BOT", "bot-token"))
