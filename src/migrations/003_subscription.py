import typing

import peewee
import peewee_migrate


def migrate(migrator: peewee_migrate.Migrator, database: peewee.Database, fake=False, **kwargs: typing.Any) -> None:
    if fake is True:
        return

    subscription = peewee.IntegerField(default=0)

    migrator.add_columns(
        model='user',
        subscription=subscription
    )
