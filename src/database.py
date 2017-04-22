#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
from uuid import uuid4

import logging

from peewee import (
    Model,
    DateTimeField, TextField, BigIntegerField,
    PeeweeException, DoesNotExist
)
from playhouse.sqlite_ext import SqliteExtDatabase

logger = logging.getLogger(__name__)

database = SqliteExtDatabase('dex.sqlite')


class BaseModel(Model):
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField()

    class Meta:
        database = database


class User(BaseModel):
    id = TextField(primary_key=True, unique=True, default=uuid4)
    telegram_id = BigIntegerField()
    telegram_username = TextField()

database.connect()

User.create_table(True)

def create_user(id, username):
    current_date_time = datetime.now()

    try:
        try:
            db_user = User.get(User.telegram_id == id)

            db_user.telegram_username = username
            db_user.updated_at = current_date_time
        except (PeeweeException, DoesNotExist):
            db_user = User.create(telegram_id=id, telegram_username=username, updated_at=current_date_time)

        if db_user:
            db_user.save()
    except PeeweeException as error:
        logger.error('Database error: {}'.format(error))


def get_users_table():
    users_table = ''

    for user in User.select():
        users_table = '{0}\n{1.telegram_id} | @{1.telegram_username} | {1.created_at}'.format(users_table, user)

    if not users_table:
        users_table = 'No users'

    return users_table
