import peewee


def migrate(migrator, database, fake=False, **kwargs):
    if fake is True:
        return

    subscription = peewee.IntegerField(default=0)

    migrator.add_columns(
        model='user',
        subscription=subscription
    )
