#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from uuid import uuid4

import argparse
import configparser
import html
import logging
import re

from bs4 import BeautifulSoup, element
from telegram import InlineQueryResultArticle, InputTextMessageContent, ParseMode
from telegram.ext import CommandHandler, InlineQueryHandler, Updater

import requests

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)

DEX_URL_FORMAT = 'https://dexonline.ro/definitie/{}/json'
DEX_DEFINITIONS_XPATH = '//div[@id="resultsTab"]/div[@class="defWrapper"]/p[@class="def"]'
DEX_THUMBNAIL_URL = 'https://dexonline.ro/img/logo/logo-og.png'

ALL_SIGNS_REGEX = re.compile(r'[@\$#]')

AT_SIGN_REGEX = re.compile(r'@([^@]+)@')
DOLLAR_SIGN_REGEX = re.compile(r'\$([^\$]+)\$')
POUND_SIGN_REGEX = re.compile(r'(?<!\\)#((?:[^#\\]|\\.)*)(?<!\\)#')

BOLD_TAG_REPLACE = r'<b>\1</b>'
ITALIC_TAG_REPLACE = r'<i>\1</i>'

DANGLING_TAG_REGEX = re.compile(r'<([^\/>]+)>[^<]*$')

MESSAGE_TITLE_LENGTH_LIMIT = 50
MESSAGE_TEXT_LENGTH_LIMIT = 4096
MESSAGES_COUNT_LIMIT = 50

def inline_query_handler(bot, update):
    if not args.fragment:
        if args.query:
            query = args.query
        else:
            query = update.inline_query.query

        if not query:
            logger.warn('Empty query')

            return

    if args.fragment:
        dexUrl = 'debug'

        dexRawDefinitions = [{
            'internalRep': args.fragment
        }]
    else:
        dexAPIUrl = DEX_URL_FORMAT.format(query)

        dexRawResponse = requests.get(dexAPIUrl).json()

        dexRawDefinitions = dexRawResponse['definitions']

        dexUrl = dexAPIUrl[:- 5] # /json

    if args.index is not None:
        if args.index >= len(dexRawDefinitions):
            logger.warn('Index out of bounds')

            return

        dexRawDefinitions = [dexRawDefinitions[args.index]]

    results = list()

    for dexRawDefinition in dexRawDefinitions:
        dexDefinitionInternalRep = dexRawDefinition['internalRep']

        index = dexRawDefinitions.index(dexRawDefinition)

        dexDefinitionTitle = dexDefinitionInternalRep

        dexDefinitionTitle = ALL_SIGNS_REGEX.sub('', dexDefinitionTitle)

        if args.debug:
            dexDefinitionTitle = '{}: {}'.format(index, dexDefinitionTitle)

        dexDefinitionTitle = dexDefinitionTitle[:MESSAGE_TITLE_LENGTH_LIMIT + 1]

        if len(dexDefinitionTitle) >= MESSAGE_TITLE_LENGTH_LIMIT:
            dexDefinitionTitle[:-3] # ellipsis
            dexDefinitionTitle = '{}...'.format(dexDefinitionTitle)

        dexDefinitionHTMLRep = dexDefinitionInternalRep

        dexDefinitionHTMLRep = dexDefinitionHTMLRep.replace('&#', '&\#') # escape # characters

        dexDefinitionHTMLRep = html.escape(dexDefinitionHTMLRep) # escape html entities

        dexDefinitionHTMLRep = AT_SIGN_REGEX.sub(BOLD_TAG_REPLACE, dexDefinitionHTMLRep) # replace @ pairs with b html tags
        dexDefinitionHTMLRep = DOLLAR_SIGN_REGEX.sub(ITALIC_TAG_REPLACE, dexDefinitionHTMLRep) # replace $ pairs with i hmtl tags
        dexDefinitionHTMLRep = POUND_SIGN_REGEX.sub(ITALIC_TAG_REPLACE, dexDefinitionHTMLRep) # replace # pairs with i hmtl tags

        dexDefinitionHTMLRep = dexDefinitionHTMLRep.replace('\#', '#') # unescape # characters

        dexDefinitionHTMLRep = html.unescape(dexDefinitionHTMLRep) # unescape html entities

        dexDefinitionHTML = BeautifulSoup(dexDefinitionHTMLRep, 'html.parser')

        # remove nested tags
        for tag in dexDefinitionHTML:
            if not isinstance(tag, element.NavigableString):
                if len(tag.contents) > 0:
                    for subtag in tag.contents:
                        if not isinstance(subtag, element.NavigableString):
                            subtag.unwrap()

        dexDefinitionHTMLRep = str(dexDefinitionHTML)

        textLimit = MESSAGE_TEXT_LENGTH_LIMIT

        textLimit -= 1 # newline between text and url
        textLimit -= len(dexUrl) # definition url
        textLimit -= 4 # possible end tag
        textLimit -= 3 # ellipsis

        dexDefinitionHTMLRep = dexDefinitionHTMLRep[:textLimit]

        logger.warn('Text limit: {}'.format(textLimit))

        danglingTagsGroups = DANGLING_TAG_REGEX.search(dexDefinitionHTMLRep)

        if danglingTagsGroups is not None:
            startTagName = danglingTagsGroups.group(1)

            dexDefinitionHTMLRep = '{}...</{}>'.format(dexDefinitionHTMLRep, startTagName)

        logger.info('URL: {}'.format(dexUrl))

        dexDefinitionHTMLRep = '{}\n{}'.format(dexDefinitionHTMLRep, dexUrl)

        logger.info('Result: {}: {}'.format(index, dexDefinitionHTMLRep))

        dexDefinitionResult = InlineQueryResultArticle(
            id=uuid4(),
            title=dexDefinitionTitle,
            thumb_url=DEX_THUMBNAIL_URL,
            input_message_content=InputTextMessageContent(
                message_text=dexDefinitionHTMLRep,
                parse_mode=ParseMode.HTML
            )
        )

        results.append(dexDefinitionResult)

    results = results[:MESSAGES_COUNT_LIMIT + 1]

    if args.debug:
        update.inline_query.answer(results, cache_time=0)
    else:
        update.inline_query.answer(results)

def error_handler(bot, update, error):
    logger.error('Update "{}" caused error "{}"'.format(update, error))

def main():
    try:
        config = configparser.ConfigParser()

        config.read('config.cfg')

        botToken = config['Telegram']['Key']
    except:
        logger.error('Missing bot token')

        return

    if not botToken:
        logger.error('Missing bot token')

        return

    updater = Updater(botToken)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(InlineQueryHandler(inline_query_handler))
    dispatcher.add_error_handler(error_handler)

    if args.debug:
        updater.start_polling(timeout=0.01)
    else:
        updater.start_polling()

    logger.info('Bot started. Press Ctrl-C to stop.')

    updater.idle()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-d', '--debug', action='store_true')

    parser.add_argument('-q', '--query')
    parser.add_argument('-i', '--index', type=int)
    parser.add_argument('-f', '--fragment')

    args = parser.parse_args()

    if args.debug:
        logger.info('Debug')

    if args.query or args.fragment:
        class Dummy:
            pass

        update = Dummy()

        update.inline_query = Dummy()

        update.inline_query.answer = lambda *args, **kwargs: None

        inline_query_handler(None, update)
    else:
        main()

