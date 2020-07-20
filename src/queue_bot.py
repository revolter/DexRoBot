#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import telegram
import telegram.ext


class QueueBot(telegram.bot.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._is_messages_queued_default = True
        self._msg_queue = telegram.ext.messagequeue.MessageQueue()

    def stop(self):
        try:
            self._msg_queue.stop()
        except:
            pass

    @telegram.ext.messagequeue.queuedmessage
    def queue_message(self, *args, **kwargs):
        return super().send_message(*args, **kwargs)

    @telegram.ext.messagequeue.queuedmessage
    def queue_photo(self, *args, **kwargs):
        return super().send_photo(*args, **kwargs)
