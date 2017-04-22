#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from uuid import uuid4

import logging

from peewee import (
    Model,
    TextField, BigIntegerField,
    PeeweeException, DoesNotExist
)
from playhouse.sqlite_ext import SqliteExtDatabase

logger = logging.getLogger(__name__)

database = SqliteExtDatabase('dex.sqlite')


class BaseModel(Model):
    class Meta:
        database = database


class User(BaseModel):
    id = TextField(primary_key=True, unique=True, default=uuid4())
    telegram_id = BigIntegerField()
    telegram_username = TextField()

database.connect()

User.create_table(True)

def create_user(id, username):
    try:
        try:
            db_user = User.get(User.telegram_id == id)

            db_user.telegram_username = username
        except (PeeweeException, DoesNotExist):
            db_user = User.create(telegram_id=id, telegram_username=username)

        if db_user:
            db_user.save()
    except PeeweeException as error:
        logger.error('Database error: {}'.format(error))
