#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from uuid import uuid4

import argparse
import configparser
import logging
import re

from botanio import botan

from lxml import etree, html

from telegram import InlineQueryResultArticle, InputTextMessageContent, ParseMode
from telegram.ext import CommandHandler, InlineQueryHandler, Updater
from telegram.constants import MAX_MESSAGE_LENGTH

import requests

BOTAN_TOKEN = None
GOOGLE_TOKEN = None

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

logging.basicConfig(format=LOGS_FORMAT, level=logging.INFO)

logger = logging.getLogger(__name__)

errorHandler = logging.FileHandler('errors.log')
errorHandler.setFormatter(logging.Formatter(LOGS_FORMAT))
errorHandler.setLevel(logging.ERROR)

logger.addHandler(errorHandler)

def start_handler(bot, update):
    message = update.message
    command = message.text
    chatId = message.chat_id

    query = COMMAND_QUERY_EXTRACT_REGEX.sub('', command)

    if not query:
        return

    url = DEX_SEARCH_URL_FORMAT.format(query)

    reply = 'Niciun rezultat găsit pentru "{}". Incearcă o căutare in tot textul definițiilor [aici]({}).'.format(query, url)

    bot.sendMessage(
        chat_id=chatId,
        text=reply,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=False
    )

def inline_query_handler(bot, update):
    inlineQuery = update.inline_query

    if args.fragment:
        query = None
    else:
        if args.query:
            query = args.query
        else:
            query = inlineQuery.query

        if not query:
            logger.warning('Empty query')

            return

    user = inlineQuery.from_user

    if not args.server:
        userIdentification = '#{}'.format(user.id)
        userName = None

        if user.first_name and user.last_name:
            userName = '{} {}'.format(user.first_name, user.last_name)
        elif user.first_name:
            userName = user.first_name
        elif user.last_name:
            userName = user.last_name

        if userName:
            userIdentification = '{}: {}'.format(userIdentification, userName)

        if user.username:
            userIdentification = '{} (@{})'.format(userIdentification, user.username)

        userIdentification = '{}:'.format(userIdentification)

        logger.info('{} {}'.format(userIdentification, query))

    if args.fragment:
        dexUrl = 'debug'

        dexRawDefinitions = [{
            'id': 0,
            'htmlRep': args.fragment,
            'sourceName': None,
            'userNick': None
        }]
    else:
        dexAPIUrl = DEX_API_URL_FORMAT.format(query)

        dexRawResponse = requests.get(dexAPIUrl).json()

        dexRawDefinitions = dexRawResponse['definitions']

        dexUrl = dexAPIUrl[:-5] # /json

    # set the index of the definitions
    for index in range(len(dexRawDefinitions)):
        dexRawDefinitions[index]['index'] = index

    if args.index is not None:
        if args.index >= len(dexRawDefinitions):
            logger.warning('Index out of bounds')

            return

        dexRawDefinitions = [dexRawDefinitions[args.index]]

    results = list()

    offsetString = update.inline_query.offset
    offset = 0

    if offsetString:
        offset = int(offsetString)

        if offset < len(dexRawDefinitions):
            dexRawDefinitions = dexRawDefinitions[offset + 1:]
    else:
        if BOTAN_TOKEN:
            botanTrack = botan.track(BOTAN_TOKEN, user, {'query': query}, 'inline_query')

            logger.info('Botan track: {}'.format(botanTrack))

        if GOOGLE_TOKEN:
            googleAnalyticsURL = GOOGLE_ANALYTICS_BASE_URL.format(GOOGLE_TOKEN, user.id, 'inline_query', query)

            googleAnalyticsResponse = requests.get(googleAnalyticsURL, headers=GOOGLE_HEADERS)

            if not str(googleAnalyticsResponse.status_code).startswith('2'):
                logger.error('Google analytics error: {}: {}').format(googleAnalyticsResponse.status_code, googleAnalyticsResponse.text)

    for dexRawDefinition in dexRawDefinitions:
        dexDefinitionIndex = dexRawDefinition['index']

        dexDefinitionId = dexRawDefinition['id']
        dexDefinitionSourceName = dexRawDefinition['sourceName']
        dexDefinitionAuthor = dexRawDefinition['userNick']
        dexDefinitionHTMLRep = dexRawDefinition['htmlRep']

        elements = html.fragments_fromstring(dexDefinitionHTMLRep)

        dexDefinitionHTML = ''
        dexDefinitionTitle = ''

        for child in elements:
            etree.strip_tags(child, '*')

            if not child.tag in ['b', 'i']:
                child.tag = 'i'

            child.attrib.clear() # etree.strip_attributes(child, '*') should work too

            childString = html.tostring(child).decode()

            dexDefinitionHTML = '{}{}'.format(dexDefinitionHTML, childString)

            dexDefinitionTitle = '{}{}'.format(dexDefinitionTitle, child.text_content())

            if child.tail:
                dexDefinitionTitle = '{}{}'.format(dexDefinitionTitle, child.tail)

        if args.debug:
            dexDefinitionTitle = '{}: {}'.format(dexDefinitionIndex, dexDefinitionTitle)

        dexDefinitionTitle = dexDefinitionTitle[:MESSAGE_TITLE_LENGTH_LIMIT + 1]

        if len(dexDefinitionTitle) >= MESSAGE_TITLE_LENGTH_LIMIT:
            dexDefinitionTitle[:-3] # ellipsis
            dexDefinitionTitle = '{}...'.format(dexDefinitionTitle)

        dexDefinitionUrl = '{}/{}'.format(dexUrl, dexDefinitionId)
        dexAuthorUrl = '{}/{}'.format(DEX_AUTHOR_URL, dexDefinitionAuthor)

        dexDefinitionFooter = '{}\nsursa: <a href="{}">{}</a> adăugată de: <a href="{}">{}</a>'.format(dexDefinitionUrl, DEX_SOURCES_URL, dexDefinitionSourceName, dexAuthorUrl, dexDefinitionAuthor)

        textLimit = MAX_MESSAGE_LENGTH

        textLimit -= 1 # newline between text and url
        textLimit -= len(dexDefinitionFooter) # definition footer
        textLimit -= 4 # possible end tag
        textLimit -= 3 # ellipsis

        dexDefinitionHTML = dexDefinitionHTML[:textLimit]

        dexDefinitionHTML = UNFINISHED_TAG_REGEX.sub('', dexDefinitionHTML)

        danglingTagsGroups = DANGLING_TAG_REGEX.search(dexDefinitionHTML)

        if danglingTagsGroups is not None:
            startTagName = danglingTagsGroups.group(1)

            dexDefinitionHTML = '{}...</{}>'.format(dexDefinitionHTML, startTagName)

        dexDefinitionHTML = '{}\n{}'.format(dexDefinitionHTML, dexDefinitionFooter)

        if args.debug:
            logger.info('Result: {}: {}'.format(dexDefinitionIndex, dexDefinitionHTML))

        dexDefinitionResult = InlineQueryResultArticle(
            id=uuid4(),
            title=dexDefinitionTitle,
            thumb_url=DEX_THUMBNAIL_URL,
            input_message_content=InputTextMessageContent(
                message_text=dexDefinitionHTML,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        )

        results.append(dexDefinitionResult)

    resultsCount = len(results)

    noResultsText = None
    noResultsParameter = None

    if resultsCount == 0:
        noResultsText = 'Niciun rezultat'
        noResultsParameter = query
    else:
        results = results[:MESSAGES_COUNT_LIMIT + 1]

    cacheTime = 24 * 60 * 60

    if args.debug:
        cacheTime = 0

    nextOffset = None

    if resultsCount > len(results):
        nextOffset = offset + MESSAGES_COUNT_LIMIT

    inlineQuery.answer(
        results,
        cache_time=cacheTime,
        next_offset=nextOffset,
        switch_pm_text=noResultsText,
        switch_pm_parameter=noResultsParameter
    )

def error_handler(bot, update, error):
    logger.error('Update "{}" caused error "{}"'.format(update, error))

def main():
    try:
        config = configparser.ConfigParser()

        config.read('config.cfg')

        botToken = config['Telegram']['Key' if args.server else 'TestKey']
    except:
        logger.error('Missing bot token')

        return

    if not botToken:
        logger.error('Missing bot token')

        return

    try:
        config = configparser.ConfigParser()

        config.read('config.cfg')

        global BOTAN_TOKEN

        BOTAN_TOKEN = config['Botan']['Key']
    except:
        logger.info('Missing Botan token')

    try:
        config = configparser.ConfigParser()

        config.read('config.cfg')

        global GOOGLE_TOKEN

        GOOGLE_TOKEN = config['Google']['Key']
    except:
        logger.info('Missing Google Analytics token')

    updater = Updater(botToken)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_handler))

    dispatcher.add_handler(InlineQueryHandler(inline_query_handler))
    dispatcher.add_error_handler(error_handler)

    if args.debug:
        logger.info('Started polling')

        updater.start_polling(timeout=0.01)
    else:
        if args.server and not args.polling:
            logger.info('Started webhook')

            if config:
                webhook = config['Webhook']

                port = int(webhook['Port'])
                key = webhook['Key']
                cert = webhook['Cert']
                url = webhook['Url'] + botToken

                if args.set_webhook:
                    logger.info('Updated webhook')
                else:
                    updater.bot.setWebhook = (lambda *args, **kwargs: None)

                updater.start_webhook(
                    listen='0.0.0.0',
                    port=port,
                    url_path=botToken,
                    key=key,
                    cert=cert,
                    webhook_url=url
                )
            else:
                logger.error('Missing bot webhook config')

                return
        else:
            logger.info('Started polling')

            updater.start_polling()

    logger.info('Bot started. Press Ctrl-C to stop.')

    updater.idle()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-d', '--debug', action='store_true')

    parser.add_argument('-q', '--query')
    parser.add_argument('-i', '--index', type=int)
    parser.add_argument('-f', '--fragment')

    parser.add_argument('-p', '--polling', action='store_true')
    parser.add_argument('-sw', '--set-webhook', action='store_true')
    parser.add_argument('-s', '--server', action='store_true')

    args = parser.parse_args()

    if args.debug:
        logger.info('Debug')

    if args.query or args.fragment:
        class Dummy:
            pass

        update = Dummy()

        update.inline_query = Dummy()

        update.inline_query.from_user = Dummy()
        update.inline_query.offset = None
        update.inline_query.answer = (lambda *args, **kwargs: None)

        update.inline_query.from_user.id = None
        update.inline_query.from_user.first_name = None
        update.inline_query.from_user.last_name = None
        update.inline_query.from_user.username = None

        inline_query_handler(None, update)
    else:
        main()
