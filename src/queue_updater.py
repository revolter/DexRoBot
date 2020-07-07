#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram.ext import Updater

from queue_bot import QueueBot


class QueueUpdater(Updater):
    def __init__(self, bot: QueueBot, *args, **kwargs):
        super().__init__(bot=bot, *args, **kwargs)

    def signal_handler(self, signum, frame):
        super().signal_handler(signum, frame)

        self.bot.stop()
