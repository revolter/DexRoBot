#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram.bot import Bot
from telegram.ext import messagequeue


class QueueBot(Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._is_messages_queued_default = True
        self._msg_queue = messagequeue.MessageQueue()

    def stop(self):
        try:
            self._msg_queue.stop()
        except:
            pass

    @messagequeue.queuedmessage
    def queue_message(self, *args, **kwargs):
        return super().send_message(*args, **kwargs)
