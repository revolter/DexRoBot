#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from enum import Enum

from botanio import botan

import requests
import requests_cache

from constants import GOOGLE_HEADERS, GOOGLE_ANALYTICS_BASE_URL

class AnalyticsType(Enum):
    INLINE_QUERY = 'inline_query'

class Analytics:
    def __botan_track(self, type, user, data):
        if not self.botanToken:
            return

        botan_track = botan.track(self.botanToken, user, {'query': data}, type.value)

        if not botan_track:
            self.logger.error('Botan analytics error')
        elif botan_track['status'] != 'accepted':
            self.logger.error('Botan analytics error: {}'.format(botan_track))

    def __google_track(self, type, user, data):
        if not self.googleToken:
            return

        url = GOOGLE_ANALYTICS_BASE_URL.format(self.googleToken, user.id, type.value, data)

        with requests_cache.disabled():
            response = requests.get(url, headers=GOOGLE_HEADERS)

            if response.status_code != 200:
                self.logger.error('Google analytics error: {}'.format(response.status_code))

    def track(self, type, user, data):
        self.__botan_track(type, user, data)
        self.__google_track(type, user, data)
