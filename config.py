import os

CONFIG = {}

CONFIG["GUILD"] = {
    "film-raffle-role-id": int(os.getenv('RAFFLE_ROLE_ID')),
    "film-raffle-channel-id": int(os.getenv('RAFFLE_CHANNEL_ID')),
    # where to dumb all recs till now before clearing
    "all-recs-channel-id": int(os.getenv('RAFFLE_CHANNEL_ID')),
    "debug-channel-id": int(os.getenv('RAFFLE_DEBUG_CHANNEL_ID', 0)),
    "privileged-roles": [int(id_) for id_ in os.getenv('PRIVILEGED_ROLES').split(',')],
}

CONFIG["CHAT"] = {
    "DM_HELP": '''
```
!help: Prints this help message
!setlb your-lb-user-name a-short-note: Sets your username and a small note (containing your streaming preferences, or any other preferences).
```
    ''',
    "DM_INTRO": """
__**Welcome to Film Raffle!**__
Set up your raffle profile to be included in the next round. This information will be sent directly to your raffle partner as context for their recommendation. Reply directly to this message to run the following command(s):

**1.** Use `!setlb `followed by your Letterboxd username to link your Letterboxd profile. This is mandatory.
Example:
```
!setlb dirkdiggler
```

**2.** Use `!setnotes` followed by any preferences you may have (streaming services, preferred length, genre/mood, etc.) This is optional.
Example:
```
!setnotes I have Netflix, HBO Max, and Prime in the US. Prefer something under 2 hours and any genre but horror.
```

**3.** You’re all set! You’ll receive a DM with your partner and more information on the day of the raffle.
    """,
    "ADMIN_HELP": """
```
!fr-start: Start the film raffle with a raffle message.
!fr-roll: Roll the raffle. Will clear all reccs till now.
!dump-reccs: Get all reccs in pretty printed format.
```
    """
}

CONFIG["BOT"] = {
    "bot-token": os.getenv("BOT_TOKEN"),
}

CONFIG["DATABASE"] = {
    "db-username": os.getenv('DB_USERNAME'),
    "db-password": os.getenv('DB_PASSWORD'),
    "db-host": os.getenv('DB_HOST'),
    "db-name": os.getenv('DB_NAME'),
}
