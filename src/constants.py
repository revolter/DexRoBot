# -*- coding: utf-8 -*-

from datetime import timedelta

import re

GOOGLE_HEADERS = {'User-Agent': 'DexRoBot'}

#: See also: https://developers.google.com/analytics/devguides/collection/protocol/v1/parameters
GOOGLE_ANALYTICS_BASE_URL = 'https://www.google-analytics.com/collect?v=1&t=event&tid={}&cid={}&ec={}&ea={}'

LOGS_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

GENERIC_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

DEX_BASE_URL = 'https://dexonline.ro'

DEX_API_URL_FORMAT = '{}/{}'.format(DEX_BASE_URL, 'definitie/{}/json')
DEX_SEARCH_URL_FORMAT = '{}/{}'.format(DEX_BASE_URL, 'text/{}')

DEX_THUMBNAIL_URL = 'https://dexonline.ro/img/logo/logo-og.png'
DEX_SOURCES_URL = 'https://dexonline.ro/surse'
DEX_AUTHOR_URL = 'https://dexonline.ro/utilizator'

DANGLING_TAG_REGEX = re.compile(r'<([^/>]+)>[^<]*$')
UNFINISHED_TAG_REGEX = re.compile(r'</?(?:\w+)?$')

UNICODE_SUPERSCRIPTS = '⁰¹²³⁴⁵⁶⁷⁸⁹'

MESSAGE_TITLE_LENGTH_LIMIT = 50
MESSAGES_COUNT_LIMIT = 50

RESULTS_CACHE_TIME = timedelta(weeks=1)

PREVIOUS_PAGE_ICON = '⬅'
PREVIOUS_OVERLAP_PAGE_ICON = '↪'
NEXT_PAGE_ICON = '➡'
NEXT_OVERLAP_PAGE_ICON = '↩'
