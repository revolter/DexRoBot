# -*- coding: utf-8 -*-

import enum
import logging
import typing

import requests
import requests_cache
import telegram.ext

import constants

logger = logging.getLogger(__name__)


class AnalyticsType(enum.Enum):
    EMPTY_QUERY = 'empty_query'
    INLINE_QUERY = 'inline_query'
    COMMAND = 'command'
    MESSAGE = 'message'


class AnalyticsHandler:
    def __init__(self) -> None:
        self.googleToken: typing.Optional[str] = None
        self.userAgent: typing.Optional[str] = None

    def __google_track(self, analytics_type: AnalyticsType, user: telegram.User, data: typing.Optional[str]) -> None:
        if not self.googleToken:
            return

        url = constants.GOOGLE_ANALYTICS_BASE_URL.format(self.googleToken, user.id, analytics_type.value, data)

        with requests_cache.disabled():
            response = requests.get(url, headers={'User-Agent': self.userAgent or 'TelegramBot'})

            if response.status_code != 200:
                logger.error('Google analytics error: {}'.format(response.status_code))

    @telegram.ext.dispatcher.run_async
    def track(self, analytics_type: AnalyticsType, user: telegram.User, data: typing.Optional[str]) -> None:
        self.__google_track(analytics_type, user, data)
