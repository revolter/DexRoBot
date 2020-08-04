#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import telegram
import telegram.ext


class QueueBot(telegram.Bot):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._is_messages_queued_default = True
        self._msg_queue = telegram.ext.MessageQueue()

    def stop(self) -> None:
        try:
            self._msg_queue.stop()
        except:
            pass

    @telegram.ext.messagequeue.queuedmessage
    def queue_message(self, *args, **kwargs) -> telegram.Message:
        return super().send_message(*args, **kwargs)

    @telegram.ext.messagequeue.queuedmessage
    def queue_photo(self, *args, **kwargs) -> telegram.Message:
        return super().send_photo(*args, **kwargs)
