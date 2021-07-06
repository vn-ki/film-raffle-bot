from sqlalchemy import create_engine, Column, Text, ForeignKey, select
from sqlalchemy.orm import relationship, backref, sessionmaker
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
Session = None
Engine = None


class User(Base):
    __tablename__ = "User"

    user_id = Column(Text, primary_key=True)
    lb_username = Column(Text, unique=True, nullable=False)
    note = Column(Text, nullable=True)


class Raffle(Base):
    __tablename__ = "Raffle"

    sender_id = Column(Text, ForeignKey('User.user_id'), primary_key=True)
    receiver_id = Column(Text, ForeignKey('User.user_id'), primary_key=True)
    recomm = Column(Text, nullable=True)

    sender = relationship("User", foreign_keys=[
                          sender_id], backref=backref("given_recomm", uselist=False))
    receiver = relationship("User", foreign_keys=[receiver_id], backref=backref(
        "received_recomm", uselist=False))


# Initialize database connection
def initialize_db(db_name, db_host, db_username, db_password):
    engine_url = f'postgresql+psycopg2://{db_username}:{db_password}@{db_host}/{db_name}'
    # echo=True in the meanwhile for debugging
    Engine = create_engine(engine_url, echo=True)

    Base.metadata.create_all(bind=Engine)
    Session = sessionmaker(bind=Engine)

# Add new user to database
def add_user(user_id, lb_username, note=None):
    session = Session()

    user = User()

    user.user_id = user_id
    user.lb_username = lb_username
    user.note = note

    session.add(user)
    session.commit()

    session.close()

# Add new raffle entry to database
def add_raffle_entry(sender_id, receiver_id):
    session = Session()

    raffle = Raffle()

    raffle.sender_id = sender_id
    raffle.receiver_id = receiver_id

    session.add(raffle)
    session.commit()

    session.close()

# Update raffle entry with movie recommendation
def recomm_movie(sender_id, recomm):
    session = Session()

    result = session.query(Raffle).filter_by(sender_id=sender_id).one_or_none()
    result.recomm = recomm

    session.commit()

    session.close()

# Get recommendation made BY a user
def get_recomm_by_sender(sender_id):
    session = Session()

    result = session.query(Raffle).filter_by(sender_id=sender_id).one_or_none()

    session.close()

    return result

# Get recommendation made TO a user
def get_recomm_by_receiver(receiver_id):
    session = Session()

    result = session.query(Raffle).filter_by(
        receiver_id=receiver_id).one_or_none()

    session.close()

    return result

# Delete all recommendations
def empty_recomms(receiver_id):
    session = Session()

    session.query(Raffle).delete()

    session.commit()
    session.close()
