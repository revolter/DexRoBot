# -*- coding: utf-8 -*-

from enum import Enum

import logging

from botanio import botan

import requests
import requests_cache

from constants import GOOGLE_HEADERS, GOOGLE_ANALYTICS_BASE_URL

logger = logging.getLogger(__name__)


class AnalyticsType(Enum):
    EMPTY_QUERY = 'empty_query'
    INLINE_QUERY = 'inline_query'
    COMMAND = 'command'
    MESSAGE = 'message'


class Analytics:
    def __init__(self):
        self.botanToken = None
        self.googleToken = None

    def __botan_track(self, analytics_type, user, data):
        if not self.botanToken:
            return

        params = {
            'query': data
        }

        botan_track = botan.track(self.botanToken, user, params, analytics_type.value)

        if not botan_track:
            logger.error('Botan analytics error')
        elif botan_track['status'] != 'accepted':
            logger.error('Botan analytics error: {}'.format(botan_track))

    def __google_track(self, analytics_type, user, data):
        if not self.googleToken:
            return

        url = GOOGLE_ANALYTICS_BASE_URL.format(self.googleToken, user.id, analytics_type.value, data)

        with requests_cache.disabled():
            response = requests.get(url, headers=GOOGLE_HEADERS)

            if response.status_code != 200:
                logger.error('Google analytics error: {}'.format(response.status_code))

    def track(self, analytics_type, user, data):
        self.__botan_track(analytics_type, user, data)
        self.__google_track(analytics_type, user, data)
