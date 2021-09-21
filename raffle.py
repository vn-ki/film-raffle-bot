from typing import List
import discord
from .db import Raffle


class FilmRaffle:
    def __init__(self, db, guild):
        self.db = db
        self.guild_id = guild

    async def rolled(self):
        await guild = self.db.get_guild(self.guild_id)
        return guild.raffle_rolled

    def create_random_mapping(self, users: List[discord.User]):
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

    def start_raffle(self, users: List[discord.User]):
        rando_list = self.create_random_mapping(users)
        await self.db.add_raffle_entries([
            Raffle(guild_id=str(guild.id), sender_id=str(pair[0].id), receiver_id=str(pair[1].id), recomm=None)
            for pair in rando_list
        ])
        return rando_list

    def reroll(self, mia_users: List[int]):
