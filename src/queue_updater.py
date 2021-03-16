#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import types

import telegram.ext

import queue_bot


class QueueUpdater(telegram.ext.Updater):
    def __init__(self, bot: queue_bot.QueueBot, *args, **kwargs) -> None:
        self.queue_bot = bot

        super().__init__(bot=bot, *args, **kwargs)  # type: ignore[misc]

    def signal_handler(self, signum: int, frame: types.FrameType) -> None:
        super().signal_handler(signum, frame)

        self.queue_bot.stop()
