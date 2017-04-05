#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re

GOOGLE_HEADERS = {'User-Agent': 'DexRoBot'}

GOOGLE_ANALYTICS_BASE_URL = "https://www.google-analytics.com/collect?v=1&tid={}&cid={}&t=event&ec={}&ea={}"

LOGS_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'

DEX_BASE_URL = 'https://dexonline.ro'

DEX_API_URL_FORMAT = '{}/{}'.format(DEX_BASE_URL, 'definitie/{}/json')
DEX_SEARCH_URL_FORMAT = '{}/{}'.format(DEX_BASE_URL, 'text/{}')

DEX_THUMBNAIL_URL = 'https://dexonline.ro/img/logo/logo-og.png'
DEX_SOURCES_URL = 'https://dexonline.ro/surse'
DEX_AUTHOR_URL = 'https://dexonline.ro/utilizator'

DANGLING_TAG_REGEX = re.compile(r'<([^/>]+)>[^<]*$')
UNFINISHED_TAG_REGEX = re.compile(r'</?(?:\w+)?$')

COMMAND_QUERY_EXTRACT_REGEX = re.compile(r'/\w+\s*')

MESSAGE_TITLE_LENGTH_LIMIT = 50
MESSAGES_COUNT_LIMIT = 50
