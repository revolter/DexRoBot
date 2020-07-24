# -*- coding: utf-8 -*-

import logging
from enum import Enum

import requests
import requests_cache
from telegram.ext.dispatcher import run_async

from constants import GOOGLE_ANALYTICS_BASE_URL

logger = logging.getLogger(__name__)


class AnalyticsType(Enum):
    EMPTY_QUERY = 'empty_query'
    INLINE_QUERY = 'inline_query'
    COMMAND = 'command'
    MESSAGE = 'message'


class AnalyticsHandler:
    def __init__(self):
        self.googleToken = None
        self.userAgent = None

    def __google_track(self, analytics_type, user, data):
        if not self.googleToken:
            return

        url = GOOGLE_ANALYTICS_BASE_URL.format(self.googleToken, user.id, analytics_type.value, data)

        with requests_cache.disabled():
            response = requests.get(url, headers={'User-Agent': self.userAgent or 'TelegramBot'})

            if response.status_code != 200:
                logger.error('Google analytics error: {}'.format(response.status_code))

    @run_async
    def track(self, analytics_type, user, data):
        self.__google_track(analytics_type, user, data)
