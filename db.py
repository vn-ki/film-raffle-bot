from sqlalchemy import create_engine, Column, Text, ForeignKey, select, insert, update, delete, or_, Boolean
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

import logging
logger = logging.getLogger('raffle_bot.db')


Base = declarative_base()


class User(Base):
    __tablename__ = "User"

    user_id = Column(Text, primary_key=True)
    lb_username = Column(Text, unique=True, nullable=True)
    note = Column(Text, nullable=True)

class Guild(Base):
    __tablename__ = 'Guild'

    guild_id = Column(Text, primary_key=True)
    raffle_message_id = Column(Text, nullable=True)
    raffle_rolled = Column(Boolean, default=False)


class Raffle(Base):
    __tablename__ = "Raffle"

    sender_id = Column(Text, ForeignKey('User.user_id'), primary_key=True)
    receiver_id = Column(Text, ForeignKey('User.user_id'), primary_key=True)
    guild_id = Column(Text, ForeignKey('Guild.guild_id'))
    recomm = Column(Text, nullable=True)
    recomm_identifier = Column(Text, nullable=True)

    sender = relationship("User", foreign_keys=[
                          sender_id], backref=backref("given_recomm", uselist=False), lazy='subquery')
    receiver = relationship("User", foreign_keys=[receiver_id], backref=backref(
        "received_recomm", uselist=False), lazy='subquery')

    def __repr__(self):
        return f'RaffleEntry<sender_id={self.sender_id} receiver_id={self.receiver_id} recomm="{self.recomm}">'


class Database:
    Session = None
    Engine = None
    engine_url = None

    def __init__(self, db_name, db_host, db_username, db_password, debug=False):
        self.engine_url = f'postgresql+asyncpg://{db_username}:{db_password}@{db_host}/{db_name}'
        if debug:
            self.engine_url = 'sqlite+aiosqlite:///./test.db'

    async def init(self):
        # echo=True in the meanwhile for debugging
        self.Engine = create_async_engine(self.engine_url)

        async with self.Engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.Session = sessionmaker(
            bind=self.Engine, expire_on_commit=False, class_=AsyncSession)

    async def get_guild(self, guild_id):
        guild_id = str(guild_id)
        async with self.Session() as session:
            result = await session.execute(select(Guild).filter_by(guild_id=guild_id))
            return result.scalar_one_or_none()

    async def add_guild(self, guild_id):
        """Add new user to database"""
        guild_id = str(guild_id)
        async with self.Session() as session:
            stmt = insert(Guild).values(guild_id=guild_id)
            await session.execute(stmt)
            await session.commit()

    async def start_raffle(self, guild_id, message_id):
        """Add new user to database"""
        guild_id = str(guild_id)
        message_id = str(message_id)
        async with self.Session() as session:
            result = await session.execute(select(Guild).filter_by(
                guild_id=guild_id))
            guild = result.scalar_one_or_none()
            if guild is None:
                logger.warning(f"guild with id {guild_id} not found")

            guild.raffle_message_id = message_id
            guild.raffle_rolled = False
            await session.commit()

    async def guild_remove_raffle_message_id(self, guild_id):
        """Add new user to database"""
        guild_id = str(guild_id)
        async with self.Session() as session:
            result = await session.execute(select(Guild).filter_by(
                guild_id=guild_id))
            guild = result.scalar_one_or_none()
            if guild is None:
                logger.warning(f"guild with id {guild_id} not found")

            guild.raffle_message_id = None
            await session.commit()

    async def guild_set_raffle_rolled(self, guild_id, rolled):
        """Add new user to database"""
        guild_id = str(guild_id)
        async with self.Session() as session:
            result = await session.execute(select(Guild).filter_by(
                guild_id=guild_id))
            guild = result.scalar_one_or_none()
            if guild is None:
                logger.warning(f"guild with id {guild_id} not found")

            guild.raffle_rolled = rolled
            await session.commit()

    async def add_user(self, user_id, lb_username=None, note=None):
        """Add new user to database"""
        user_id = str(user_id)
        async with self.Session() as session:
            stmt = insert(User).values(user_id=user_id,
                                       lb_username=lb_username, note=note)
            await session.execute(stmt)
            await session.commit()

    async def update_user(self, user_id, *, lb_username=None, note=None):
        """Add new user to database"""
        user_id = str(user_id)
        async with self.Session() as session:
            result = await session.execute(select(User).filter_by(
                user_id=user_id))
            user = result.scalar_one_or_none()

            if lb_username != None:
                user.lb_username = lb_username
            if note != None:
                user.note = note
            await session.commit()

    async def get_user(self, user_id):
        user_id = str(user_id)
        async with self.Session() as session:
            result = await session.execute(select(User).filter_by(user_id=user_id))
            return result.scalar_one_or_none()

    async def add_raffle_entries(self, entries):
        async with self.Session() as session:
            session.add_all(entries)
            await session.commit()

    async def add_raffle_entry(self, guild_id, sender_id, receiver_id):
        """Add new raffle entry to database"""
        sender_id = str(sender_id)
        receiver_id = str(receiver_id)
        guild_id = str(guild_id)
        async with self.Session() as session:
            await session.execute(insert(Raffle).values(
                guild_id=guild_id, sender_id=sender_id, receiver_id=receiver_id))
            await session.commit()

    # Update raffle entry with movie recommendation
    async def recomm_movie(self, guild_id, sender_id, recomm, recomm_identifier):
        sender_id = str(sender_id)
        guild_id = str(guild_id)
        async with self.Session() as session:
            result = await session.execute(select(Raffle).filter_by(guild_id=guild_id).filter_by(
                sender_id=sender_id))
            result = result.scalar_one_or_none()
            if result is None:
                logger.warning('raffle entry not found')
                return
            result.recomm = recomm
            result.recomm_identifier = recomm_identifier

            await session.commit()

    # Get recommendation made BY a user
    async def get_all_reccs(self, guild_id):
        guild_id = str(guild_id)
        async with self.Session() as session:
            result = await session.execute(select(Raffle).filter_by(guild_id=guild_id))
            return result.scalars().all()

    async def get_mia(self, guild_id):
        guild_id = str(guild_id)
        async with self.Session() as session:
            result = await session.execute(select(Raffle).filter_by(guild_id=guild_id).filter_by(recomm=None))
            return result.scalars().all()

    # Get recommendation made BY a user
    async def get_raffle_entry_by_sender(self, guild_id, sender_id):
        guild_id = str(guild_id)
        sender_id = str(sender_id)
        async with self.Session() as session:
            result = await session.execute(select(Raffle).filter_by(guild_id=guild_id).filter_by(
                sender_id=sender_id))
            return result.scalar_one_or_none()

    # Get recommendation made TO a user
    async def get_raffle_entry_by_receiver(self, guild_id, receiver_id):
        guild_id = str(guild_id)
        receiver_id = str(receiver_id)
        async with self.Session() as session:
            result = await session.execute(select(Raffle).filter_by(guild_id=guild_id).filter_by(
                receiver_id=receiver_id))
            return result.scalar_one_or_none()

    async def remove_all_raffle_entries_by_users(self, guild_id, user_ids):
        guild_id = str(guild_id)
        user_ids = [str(user_id) for user_id in user_ids]
        async with self.Session() as session:
            stmts = delete(Raffle).filter_by(guild_id=guild_id).where(or_(Raffle.sender_id.in_(
                user_ids), Raffle.receiver_id.in_(user_ids)))
            await session.execute(stmts)
            await session.commit()

    # Delete all recommendations
    async def clear_raffle_db(self, guild_id):
        guild_id = str(guild_id)
        async with self.Session() as session:
            await session.execute(delete(Raffle).filter_by(guild_id=guild_id))

            await session.commit()
