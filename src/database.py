# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime
import enum
import logging
import typing
import uuid

import peewee
import peewee_migrate
import playhouse.sqlite_ext

import constants

logger = logging.getLogger(__name__)

database = peewee.SqliteDatabase('dex.sqlite')

database.connect()

router = peewee_migrate.Router(database, migrate_table='migration', logger=logger)


def get_current_datetime() -> str:
    return datetime.datetime.now().strftime(constants.GENERIC_DATE_TIME_FORMAT)


class BaseModel(peewee.Model):
    rowid = playhouse.sqlite_ext.RowIDField()

    created_at = peewee.DateTimeField(default=get_current_datetime)
    updated_at = peewee.DateTimeField()

    class Meta:
        database = database


class User(BaseModel):
    class Subscription(enum.Enum):
        undetermined = 0
        accepted = 1
        denied = 2
        revoked = 3

    id = peewee.TextField(unique=True, default=uuid.uuid4)
    telegram_id = peewee.BigIntegerField(unique=True)
    telegram_username = peewee.TextField(null=True)
    subscription = peewee.IntegerField(default=0)

    def get_markdown_description(self) -> str:
        username = '`@{}`'.format(self.telegram_username) if self.telegram_username else '-'

        return '{0.rowid}. | [{0.telegram_id}](tg://user?id={0.telegram_id}) | {1} | {2}'.format(self, username, User.Subscription(self.subscription).name)

    def get_created_at(self) -> str:
        date = typing.cast(datetime.datetime, self.created_at)

        return date.strftime(constants.GENERIC_DATE_TIME_FORMAT)

    def get_updated_ago(self) -> str:
        if self.updated_at == self.created_at:
            return '-'

        delta_seconds = round((datetime.datetime.now() - self.updated_at).total_seconds())
        time_ago = str(datetime.datetime.fromtimestamp(delta_seconds) - constants.EPOCH_DATE)

        return '{} ago'.format(time_ago)

    @classmethod
    def create_or_update_user(cls, id: int, username: str) -> typing.Optional[User]:
        current_date_time = get_current_datetime()

        try:
            defaults = {
                'telegram_username': username,

                'updated_at': current_date_time
            }

            (db_user, is_created) = cls.get_or_create(telegram_id=id, defaults=defaults)

            db_user.telegram_username = username
            db_user.updated_at = current_date_time

            db_user.save()

            if is_created:
                return db_user
        except peewee.PeeweeException as error:
            logger.error('Database error: "{}" for id: {} and username: {}'.format(error, id, username))

        return None

    @classmethod
    def get_users_table(cls, sorted_by_updated_at=False, include_only_subscribed=False) -> str:
        users_table = ''

        try:
            sort_field = cls.updated_at if sorted_by_updated_at else cls.created_at

            query = cls.select()

            if sorted_by_updated_at:
                query = query.where(cls.created_at != cls.updated_at)

            if include_only_subscribed:
                query = query.where(cls.subscription == cls.Subscription.accepted.value)

            query = query.order_by(sort_field.desc()).limit(10)

            for user in reversed(query):
                users_table += '\n{} | {} | {}'.format(
                    user.get_markdown_description(),

                    user.get_created_at(),
                    user.get_updated_ago()
                )
        except peewee.PeeweeException:
            pass

        if not users_table:
            users_table = 'No users'

        return users_table


migrator = router.migrator

migrator.create_table(User)

router.run()
