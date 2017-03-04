#!/usr/bin/env python
# -*- coding: utf-8 -*-

from uuid import uuid4

import logging
import re
import sys

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
    query = update.inline_query.query

    if not query:
        return

    utf8Parser = etree.XMLParser(encoding='utf-8')

    dexUrl = DEX_URL_FORMAT.format(query)
    dexPage = html.fromstring(requests.get(dexUrl).text)
    dexDefinitions = dexPage.xpath(DEX_DEFINITIONS_XPATH)

    results = list()

    for dexDefinition in dexDefinitions:
        dexDefinitionText = dexDefinition.text_content().strip()
        dexDefinitionResultText = dexDefinitionText
        dexDefinitionResultContentText = '{}\n{}'.format(dexUrl, dexDefinitionResultText)

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

    update.inline_query.answer(results)

def error_handler(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))

def main():
    updater = Updater(BOT_TOKEN)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(InlineQueryHandler(inline_query_handler))
    dispatcher.add_error_handler(error_handler)

    updater.start_polling()

    logger.info('Bot started. Press Ctrl-C to stop.')

    updater.idle()

if __name__ == '__main__':
    if sys.argv[1] == '-d':
        logger.info('Debug')

        class Dummy(object):
            pass

        update = Dummy()

        update.inline_query = Dummy()

        update.inline_query.query = sys.argv[2]
        update.inline_query.answer = lambda *args: None

        inline_query_handler(None, update)
    else:
        main()

