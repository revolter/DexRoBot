from peewee import IntegerField


def migrate(migrator, database, fake=False, **kwargs):
    if fake is True:
        return

    subscription = IntegerField(default=0)

    migrator.add_columns(
        model='user',
        subscription=subscription
    )
