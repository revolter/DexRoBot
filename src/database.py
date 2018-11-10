# -*- coding: utf-8 -*-

from datetime import datetime
from uuid import uuid4

import logging

from peewee import (
    Model,
    DateTimeField, TextField, BigIntegerField,
    PeeweeException
)
from peewee_migrate import Migrator, Router
from playhouse.sqlite_ext import RowIDField, SqliteExtDatabase

from constants import GENERIC_DATE_TIME_FORMAT

logger = logging.getLogger(__name__)

database = SqliteExtDatabase('dex.sqlite')

database.connect()

migrator = Migrator(database)

router = Router(database, migrate_table='migration', logger=logger)


class BaseModel(Model):
    rowid = RowIDField()

    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField()

    class Meta:
        database = database


class User(BaseModel):
    id = TextField(primary_key=False, unique=True, default=uuid4)
    telegram_id = BigIntegerField(unique=True)
    telegram_username = TextField(null=True)

    def get_markdown_description(self):
        username = '`@{}`'.format(self.telegram_username) if self.telegram_username else '-'

        return '{0.rowid}. | [{0.telegram_id}](tg://user?id={0.telegram_id}) | {1}'.format(self, username)

    def get_created_at(self):
        return self.created_at.strftime(GENERIC_DATE_TIME_FORMAT)

    def get_updated_at(self):
        return self.updated_at.strftime(GENERIC_DATE_TIME_FORMAT)

    @classmethod
    def get_user_by_telegram_id(cls, id):
        try:
            return User.get(User.telegram_id == id)
        except Exception as error:
            logger.error('Database error: "{}" for id: {}'.format(error, id))

            return None

    @classmethod
    def create_user(cls, id, username):
        current_date_time = datetime.now()

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
        except PeeweeException as error:
            logger.error('Database error: "{}" for id: {} and username: {}'.format(error, id, username))

        return None

    @classmethod
    def get_users_table(cls):
        users_table = ''

        try:
            for user in reversed(cls.select().order_by(User.created_at.desc()).limit(10)):
                users_table = '{}\n{} | {} | {}'.format(
                    users_table,

                    user.get_markdown_description(),

                    user.get_created_at(),
                    user.get_updated_at()
                )
        except PeeweeException:
            pass

        if not users_table:
            users_table = 'No users'

        return users_table

migrator.create_table(User)

router.migrator = migrator
router.run()
