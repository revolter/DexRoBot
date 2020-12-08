#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import queue
import typing

import telegram.ext


class QueueBot(telegram.Bot):
    def __init__(self, exception_handler: typing.Callable[[int, Exception], None], *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._is_messages_queued_default = True
        self._msg_queue = telegram.ext.MessageQueue()

        self.exception_handler = exception_handler

    def stop(self) -> None:
        try:
            self._msg_queue.stop()
        except (queue.Full, RuntimeError, ValueError):
            pass

    @telegram.ext.messagequeue.queuedmessage
    def queue_message(self, chat_id, *args, **kwargs) -> telegram.Message:
        try:
            return super().send_message(chat_id=chat_id, *args, **kwargs)
        except Exception as exception:
            self.exception_handler(chat_id, exception)

    @telegram.ext.messagequeue.queuedmessage
    def queue_photo(self, chat_id, *args, **kwargs) -> telegram.Message:
        try:
            return super().send_photo(chat_id=chat_id, *args, **kwargs)
        except Exception as exception:
            self.exception_handler(chat_id, exception)
