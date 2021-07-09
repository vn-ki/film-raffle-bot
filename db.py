from sqlalchemy import create_engine, Column, Text, ForeignKey, select
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

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

    def __init__(self, db_name, db_host, db_username, db_password, debug=False):
        engine_url = f'postgresql+psycopg2://{db_username}:{db_password}@{db_host}/{db_name}'
        if debug:
            engine_url = 'sqlite:///./test.db'
        # echo=True in the meanwhile for debugging
        self.Engine = create_engine(engine_url, echo=False)

        Base.metadata.create_all(bind=self.Engine)
        self.Session = sessionmaker(bind=self.Engine)

    def add_user(self, user_id, lb_username=None, note=None):
        """Add new user to database"""
        with self.Session() as session:
            user = User()

            user.user_id = user_id
            user.lb_username = lb_username
            user.note = note

            session.add(user)
            session.commit()

    def update_user(self, user_id, *, lb_username=None, note=None):
        """Add new user to database"""
        with self.Session() as session:
            user = session.query(User).filter_by(user_id=user_id).one_or_none()
            if lb_username != None:
                user.lb_username = lb_username
            if note != None:
                user.note = note
            session.commit()

    def get_user(self, user_id):
        with self.Session() as session:
            return session.query(User).filter_by(user_id=user_id).one_or_none()

    def add_raffle_entry(self, sender_id, receiver_id):
        """Add new raffle entry to database"""
        with self.Session() as session:
            raffle = Raffle()

            raffle.sender_id = sender_id
            raffle.receiver_id = receiver_id

            session.add(raffle)
            session.commit()

    # Update raffle entry with movie recommendation
    def recomm_movie(self, sender_id, recomm):
        with self.Session() as session:
            result = session.query(Raffle).filter_by(sender_id=sender_id).one_or_none()
            result.recomm = recomm

            session.commit()

    # Get recommendation made BY a user
    def get_all_reccs(self):
        with self.Session() as session:
            result = session.query(Raffle).all()
            return result

    # Get recommendation made BY a user
    def get_raffle_entry_by_sender(self, sender_id):
        with self.Session() as session:
            result = session.query(Raffle).filter_by(sender_id=sender_id).one_or_none()
            return result

    # Get recommendation made TO a user
    def get_raffle_entry_by_receiver(self, receiver_id):
        with self.Session() as session:
            result = session.query(Raffle).filter_by(
                receiver_id=receiver_id).one_or_none()
            return result

    # Delete all recommendations
    def clear_raffle_db(self):
        with self.Session() as session:
            session.query(Raffle).delete()

            session.commit()
