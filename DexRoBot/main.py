#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from uuid import uuid4

import argparse
import configparser
import html
import logging
import re

from botanio import botan
from bs4 import BeautifulSoup, element
from telegram import InlineQueryResultArticle, InputTextMessageContent, ParseMode
from telegram.ext import CommandHandler, InlineQueryHandler, Updater
from telegram.constants import MAX_MESSAGE_LENGTH

import requests

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)

DEX_URL_FORMAT = 'https://dexonline.ro/definitie/{}/json'
DEX_DEFINITIONS_XPATH = '//div[@id="resultsTab"]/div[@class="defWrapper"]/p[@class="def"]'
DEX_THUMBNAIL_URL = 'https://dexonline.ro/img/logo/logo-og.png'
DEX_SOURCES_URL = 'https://dexonline.ro/surse'
DEX_AUTHOR_URL = 'https://dexonline.ro/utilizator'

ALL_SIGNS_REGEX = re.compile(r'[@\$#]')

AT_SIGN_REGEX = re.compile(r'@([^@]+)@')
DOLLAR_SIGN_REGEX = re.compile(r'\$([^\$]+)\$')
POUND_SIGN_REGEX = re.compile(r'(?<!\\)#((?:[^#\\]|\\.)*)(?<!\\)#')

BOLD_TAG_REPLACE = r'<b>\1</b>'
ITALIC_TAG_REPLACE = r'<i>\1</i>'

DANGLING_TAG_REGEX = re.compile(r'<([^\/>]+)>[^<]*$')

MESSAGE_TITLE_LENGTH_LIMIT = 50
MESSAGES_COUNT_LIMIT = 50

def inline_query_handler(bot, update):
    inlineQuery = update.inline_query

    if not args.fragment:
        if args.query:
            query = args.query
        else:
            query = inlineQuery.query

        if not query:
            logger.warn('Empty query')

            return

    user = inlineQuery.from_user

    if BOTAN_TOKEN:
        botanTrack = botan.track(BOTAN_TOKEN, user, {'query': query}, 'inline_query')

        logger.info('Botan track: {}'.format(botanTrack))

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
        dexDefinitionId = dexRawDefinition['id']
        dexDefinitionSourceName = dexRawDefinition['sourceName']
        dexDefinitionAuthor = dexRawDefinition['userNick']
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

        dexDefinitionUrl = '{}/{}'.format(dexUrl, dexDefinitionId)
        dexAuthorUrl = '{}/{}'.format(DEX_AUTHOR_URL, dexDefinitionAuthor)

        dexDefinitionFooter = '{}\nsursa: <a href="{}">{}</a> adăugată de: <a href="{}">{}</a>'.format(dexDefinitionUrl, DEX_SOURCES_URL, dexDefinitionSourceName, dexAuthorUrl, dexDefinitionAuthor)

        textLimit = MAX_MESSAGE_LENGTH

        textLimit -= 1 # newline between text and url
        textLimit -= len(dexDefinitionFooter) # definition footer
        textLimit -= 4 # possible end tag
        textLimit -= 3 # ellipsis

        dexDefinitionHTMLRep = dexDefinitionHTMLRep[:textLimit]

        if args.debug:
            logger.warn('Text limit: {}'.format(textLimit))

        danglingTagsGroups = DANGLING_TAG_REGEX.search(dexDefinitionHTMLRep)

        if danglingTagsGroups is not None:
            startTagName = danglingTagsGroups.group(1)

            dexDefinitionHTMLRep = '{}...</{}>'.format(dexDefinitionHTMLRep, startTagName)

        if args.debug:
            logger.info('URL: {}'.format(dexDefinitionUrl))

        dexDefinitionHTMLRep = '{}\n{}'.format(dexDefinitionHTMLRep, dexDefinitionFooter)

        if args.debug:
            logger.info('Result: {}: {}'.format(index, dexDefinitionHTMLRep))

        dexDefinitionResult = InlineQueryResultArticle(
            id=uuid4(),
            title=dexDefinitionTitle,
            thumb_url=DEX_THUMBNAIL_URL,
            input_message_content=InputTextMessageContent(
                message_text=dexDefinitionHTMLRep,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        )

        results.append(dexDefinitionResult)

    results = results[:MESSAGES_COUNT_LIMIT + 1]

    if args.debug:
        inlineQuery.answer(results, cache_time=0)
    else:
        inlineQuery.answer(results)

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

    updater = Updater(botToken)

    dispatcher = updater.dispatcher

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

                updater.start_webhook(listen='0.0.0.0', port=port, url_path=botToken, key=key, cert=cert, webhook_url=url)
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

        update.inline_query.answer = (lambda *args, **kwargs: None)

        inline_query_handler(None, update)
    else:
        main()

