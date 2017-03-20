#!/usr/bin/env python
# -*- coding: utf-8 -*-

from uuid import uuid4

import argparse
import logging
import re

from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import CommandHandler, InlineQueryHandler, Updater

from lxml import etree
from lxml import html

import requests

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

logger = logging.getLogger(__name__)

BOT_TOKEN = '348175336:AAE2DprB0kHWVSFNOKYD4wPK0goQ9fUFqEY'

DEX_URL_FORMAT = 'https://dexonline.ro/definitie/{}'
DEX_DEFINITIONS_XPATH = '//div[@id="resultsTab"]/div[@class="defWrapper"]/p[@class="def"]'

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

        dexDefinitions = [{
            'internalRep': args.fragment
        }]
    else:
        dexUrl = DEX_URL_FORMAT.format(query)

        utf8Parser = etree.XMLParser(encoding='utf-8')

        dexPage = html.fromstring(requests.get(dexUrl).text)
        dexDefinitions = dexPage.xpath(DEX_DEFINITIONS_XPATH)

    if args.index is not None:
        if args.index >= len(dexDefinitions):
            logger.warn('Index out of bounds')

            return

        dexDefinitions = [dexDefinitions[args.index]]

    results = list()

    for dexDefinition in dexDefinitions:
        dexDefinitionText = dexDefinition.text_content().strip()
        dexDefinitionResultText = dexDefinitionText
        dexDefinitionResultContentText = '{}\n{}'.format(dexUrl, dexDefinitionResultText)

        index = dexDefinitions.index(dexDefinition)

        if args.debug:
            dexDefinitionResultText = '{}: {}'.format(index, dexDefinitionResultText)

        logger.warn('RESULT: {}'.format(dexDefinitionResultText))

        dexDefinitionResult = InlineQueryResultArticle(
            id=uuid4(),
            title=dexDefinitionResultText,
            thumb_url='https://dexonline.ro/img/svg/logo-nav-narrow.svg',
            url=dexUrl,
            input_message_content=InputTextMessageContent(
                message_text=dexDefinitionResultContentText,
                parse_mode='HTML'
            )
        )

        results.append(dexDefinitionResult)

    if args.debug:
        update.inline_query.answer(results, cache_time=0)
    else:
        update.inline_query.answer(results)

def error_handler(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))

def main():
    updater = Updater(BOT_TOKEN)

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

