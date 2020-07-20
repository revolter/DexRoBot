# -*- coding: utf-8 -*-

import datetime

import regex

#: See also: https://developers.google.com/analytics/devguides/collection/protocol/v1/parameters
GOOGLE_ANALYTICS_BASE_URL = 'https://www.google-analytics.com/collect?v=1&t=event&tid={}&cid={}&ec={}&ea={}'

LOGS_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

GENERIC_DATE_FORMAT = '%Y-%m-%d'
GENERIC_DATE_TIME_FORMAT = '{} %H:%M:%S'.format(GENERIC_DATE_FORMAT)

EPOCH_DATE = datetime.datetime(1970, 1, 1)

DEX_BASE_URL = 'https://dexonline.ro'

DEX_API_JSON_PATH = '/json'
DEX_API_SUFFIX_REGEX = regex.compile(r'{}(\?t=\d+)?'.format(DEX_API_JSON_PATH))

DEX_DEFINITION_API_URL_FORMAT = '{}/definitie/{{}}{}'.format(DEX_BASE_URL, DEX_API_JSON_PATH)
DEX_WORD_OF_THE_DAY_URL = '{}/cuvantul-zilei{}?t={{}}'.format(DEX_BASE_URL, DEX_API_JSON_PATH)
DEX_SEARCH_URL_FORMAT = '{}/text/{{}}'.format(DEX_BASE_URL)

DEX_THUMBNAIL_URL = 'https://dexonline.ro/img/logo/logo-og.png'
DEX_SOURCES_URL = 'https://dexonline.ro/surse'
DEX_AUTHOR_URL = 'https://dexonline.ro/utilizator'

BOT_START_URL_FORMAT = 'https://telegram.me/{}?start={}'

WORD_REGEX = regex.compile(r'(?P<word>[\p{L}\p{M}\p{N}]+)|(?P<other>\P{L}+)')

UNICODE_SUPERSCRIPTS = {
    # Source: https://www.fileformat.info/info/unicode/block/superscripts_and_subscripts/list.htm.

    '0': '⁰',
    '1': '¹',
    '2': '²',
    '3': '³',
    '4': '⁴',
    '5': '⁵',
    '6': '⁶',
    '7': '⁷',
    '8': '⁸',
    '9': '⁹',

    '+': '⁺',
    '-': '⁻',
    '=': '⁼',

    '(': '⁽',
    ')': '⁾',

    # Source: https://www.fileformat.info/info/unicode/category/Lm/list.htm.

    'a': 'ᵃ',
    'b': 'ᵇ',
    'c': 'ᶜ',
    'd': 'ᵈ',
    'e': 'ᵉ',
    'f': 'ᶠ',
    'g': 'ᵍ',
    'h': 'ʰ',
    'i': 'ⁱ',
    'j': 'ʲ',
    'k': 'ᵏ',
    'l': 'ˡ',
    'm': 'ᵐ',
    'n': 'ⁿ',
    'o': 'ᵒ',
    'p': 'ᵖ',
    'r': 'ʳ',
    's': 'ˢ',
    't': 'ᵗ',
    'u': 'ᵘ',
    'v': 'ᵛ',
    'w': 'ʷ',
    'x': 'ˣ',
    'y': 'ʸ',
    'z': 'ᶻ',

    'A': 'ᴬ',
    'B': 'ᴮ',
    'D': 'ᴰ',
    'E': 'ᴱ',
    'G': 'ᴳ',
    'H': 'ᴴ',
    'I': 'ᴵ',
    'J': 'ᴶ',
    'K': 'ᴷ',
    'L': 'ᴸ',
    'M': 'ᴹ',
    'N': 'ᴺ',
    'O': 'ᴼ',
    'P': 'ᴾ',
    'R': 'ᴿ',
    'T': 'ᵀ',
    'U': 'ᵁ',
    'V': 'ⱽ',
    'W': 'ᵂ'
}

ELLIPSIS = '…'
DEFINITION_AND_FOOTER_SEPARATOR = '\n\n'

MESSAGE_TITLE_LENGTH_LIMIT = 50

RESULTS_CACHE_TIME = datetime.timedelta(weeks=1)

PREVIOUS_PAGE_ICON = '⬅'
PREVIOUS_OVERLAP_PAGE_ICON = '↪'
NEXT_PAGE_ICON = '➡'
NEXT_OVERLAP_PAGE_ICON = '↩'

_LINKS_TOOGLE_TEXT_FORMAT = '🔗: {}'
LINKS_TOGGLE_ON_TEXT = _LINKS_TOOGLE_TEXT_FORMAT.format('off')
LINKS_TOGGLE_OFF_TEXT = _LINKS_TOOGLE_TEXT_FORMAT.format('on')

BUTTON_DATA_QUERY_KEY = 'q'
BUTTON_DATA_OFFSET_KEY = 'o'
BUTTON_DATA_LINKS_TOGGLE_KEY = 'l'

BUTTON_DATA_IS_SUBSCRIPTION_ONBOARDING_KEY = 'so'
BUTTON_DATA_SUBSCRIPTION_STATE_KEY = 's'
