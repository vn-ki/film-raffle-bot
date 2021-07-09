from sqlalchemy import create_engine, Column, Text, ForeignKey, select, insert, update, delete
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession


Base = declarative_base()


class User(Base):
    __tablename__ = "User"

    user_id = Column(Text, primary_key=True)
    lb_username = Column(Text, unique=True, nullable=True)
    note = Column(Text, nullable=True)


class Raffle(Base):
    __tablename__ = "Raffle"

    sender_id = Column(Text, ForeignKey('User.user_id'), primary_key=True)
    receiver_id = Column(Text, ForeignKey('User.user_id'), primary_key=True)
    recomm = Column(Text, nullable=True)

    sender = relationship("User", foreign_keys=[
                          sender_id], backref=backref("given_recomm", uselist=False), lazy='subquery')
    receiver = relationship("User", foreign_keys=[receiver_id], backref=backref(
        "received_recomm", uselist=False), lazy='subquery')


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
        self.Engine = create_async_engine(self.engine_url, echo=True)

        async with self.Engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        self.Session = sessionmaker(
            bind=self.Engine, expire_on_commit=False, class_=AsyncSession)

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

    async def add_raffle_entry(self, sender_id, receiver_id):
        """Add new raffle entry to database"""
        sender_id = str(sender_id)
        receiver_id = str(receiver_id)
        async with self.Session() as session:
            await session.execute(insert(Raffle).values(
                sender_id=sender_id, receiver_id=receiver_id))
            await session.commit()

    # Update raffle entry with movie recommendation
    async def recomm_movie(self, sender_id, recomm):
        sender_id = str(sender_id)
        async with self.Session() as session:
            result = await session.execute(select(Raffle).filter_by(
                sender_id=sender_id))
            result = result.scalar_one_or_none()
            result.recomm = recomm

            await session.commit()

    # Get recommendation made BY a user
    async def get_all_reccs(self):
        async with self.Session() as session:
            result = await session.execute(select(Raffle))
            return result.scalars().all()

    # Get recommendation made BY a user
    async def get_raffle_entry_by_sender(self, sender_id):
        sender_id = str(sender_id)
        async with self.Session() as session:
            result = await session.execute(select(Raffle).filter_by(
                sender_id=sender_id))
            return result.scalar_one_or_none()

    # Get recommendation made TO a user
    async def get_raffle_entry_by_receiver(self, receiver_id):
        receiver_id = str(receiver_id)
        async with self.Session() as session:
            result = await session.execute(select(Raffle).filter_by(
                receiver_id=receiver_id))
            return result.scalar_one_or_none()

    # Delete all recommendations
    async def clear_raffle_db(self):
        async with self.Session() as session:
            await session.execute(delete(Raffle))

            await session.commit()
