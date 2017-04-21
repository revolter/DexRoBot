#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import timedelta
from urllib.parse import quote
from uuid import uuid4

import argparse
import base64
import configparser
import logging
import os
import sys
import time

from lxml import etree, html

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle,
    InputTextMessageContent, ParseMode
)
from telegram.ext import CommandHandler, InlineQueryHandler, Updater
from telegram.constants import MAX_MESSAGE_LENGTH

import requests
import requests_cache

from analytics import Analytics
from constants import *
from utils import *

BOT_TOKEN = None

ADMIN_USER_ID = None

logging.basicConfig(format=LOGS_FORMAT, level=logging.INFO)

error_logging_handler = logging.FileHandler('errors.log')
error_logging_handler.setFormatter(logging.Formatter(LOGS_FORMAT))
error_logging_handler.setLevel(logging.ERROR)

logging.getLogger('').addHandler(error_logging_handler)

logger = logging.getLogger(__name__)

analytics = None


def start_command_handler(bot, update, args):
    message = update.message
    chat_id = message.chat_id

    analytics.track(AnalyticsType.COMMAND, message.from_user, message.text)

    query = ' '.join(args)

    try:
        query = base64.urlsafe_b64decode(query).decode('utf-8')
    except:
        pass

    if not query:
        reply_button = InlineKeyboardButton('Încearcă', switch_inline_query='cuvânt')
        reply_markup = InlineKeyboardMarkup([[reply_button]])

        bot.sendMessage(
            chat_id, (
                'Salut, sunt un bot care caută definiții pentru cuvinte folosind '
                '[dexonline.ro](http://dexonline.ro). '
                'Încearcă să scrii @DexRoBot _cuvânt_ în orice chat.'
            ),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

        return

    url = DEX_SEARCH_URL_FORMAT.format(quote(query))

    reply = (
        'Niciun rezultat găsit pentru "{}". '
        'Incearcă o căutare in tot textul definițiilor [aici]({}).'
    ).format(query, url)

    bot.sendMessage(
        chat_id=chat_id,
        text=reply,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )


def restart_command_handler(bot, update):
    message = update.message

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    bot.sendMessage(message.chat_id, 'Restarting...' if cli_args.debug else 'Restarting in 1 second...')

    time.sleep(0.2 if cli_args.debug else 1)

    os.execl(sys.executable, sys.executable, *sys.argv)


def logs_command_handler(bot, update):
    message = update.message
    chat_id = message.chat_id

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    try:
        bot.sendDocument(chat_id, document=open('errors.log', 'rb'))
    except:
        bot.sendMessage(chat_id, 'Log is empty')


def inline_query_handler(bot, update):
    inline_query = update.inline_query
    user = inline_query.from_user

    if cli_args.fragment:
        query = None
    else:
        if cli_args.query:
            query = cli_args.query
        else:
            query = inline_query.query

        if not query:
            logger.warning('Empty query')

            analytics.track(AnalyticsType.EMPTY_QUERY, user, None)

            return

    if not cli_args.server:
        user_identification = '#{}'.format(user.id)
        user_name = None

        if user.first_name and user.last_name:
            user_name = '{} {}'.format(user.first_name, user.last_name)
        elif user.first_name:
            user_name = user.first_name
        elif user.last_name:
            user_name = user.last_name

        if user_name:
            user_identification = '{}: {}'.format(user_identification, user_name)

        if user.username:
            user_identification = '{} (@{})'.format(user_identification, user.username)

        user_identification = '{}:'.format(user_identification)

        logger.info('{} {}'.format(user_identification, query))

    if cli_args.fragment:
        dex_url = 'debug'

        dex_raw_definitions = [{
            'id': 0,
            'htmlRep': cli_args.fragment,
            'sourceName': None,
            'userNick': None
        }]
    else:
        dex_api_url = DEX_API_URL_FORMAT.format(query)

        dex_raw_response = requests.get(dex_api_url).json()

        dex_raw_definitions = dex_raw_response['definitions']

        dex_url = dex_api_url[:-5]  # /json

    # set the index of the definitions
    for index in range(len(dex_raw_definitions)):
        dex_raw_definitions[index]['index'] = index

    if cli_args.index is not None:
        if cli_args.index >= len(dex_raw_definitions):
            logger.warning('Index out of bounds')

            return

        dex_raw_definitions = [dex_raw_definitions[cli_args.index]]

    results = list()

    offset_string = update.inline_query.offset
    offset = 0

    if offset_string:
        offset = int(offset_string)

        if offset < len(dex_raw_definitions):
            dex_raw_definitions = dex_raw_definitions[offset + 1:]
    else:
        analytics.track(AnalyticsType.INLINE_QUERY, user, query)

    for dex_raw_definition in dex_raw_definitions:
        dex_definition_index = dex_raw_definition['index']

        dex_definition_id = dex_raw_definition['id']
        dex_definition_source_name = dex_raw_definition['sourceName']
        dex_definition_author = dex_raw_definition['userNick']
        dex_definition_html_rep = dex_raw_definition['htmlRep']

        elements = html.fragments_fromstring(dex_definition_html_rep)

        dex_definition_html = ''
        dex_definition_title = ''

        for child in elements:
            for sup in child.findall('sup'):
                sup_number = int(sup.text_content())

                if 0 <= sup_number <= 9:
                    sup.text = UNICODE_SUPERSCRIPTS[sup_number]

            etree.strip_tags(child, '*')

            if child.tag not in ['b', 'i']:
                child.tag = 'i'

            child.attrib.clear()  # etree.strip_attributes(child, '*') should work too

            child_string = html.tostring(child).decode()

            dex_definition_html = '{}{}'.format(dex_definition_html, child_string)

            dex_definition_title = '{}{}'.format(dex_definition_title, child.text_content())

            if child.tail:
                dex_definition_title = '{}{}'.format(dex_definition_title, child.tail)

        if cli_args.debug:
            dex_definition_title = '{}: {}'.format(dex_definition_index, dex_definition_title)

        dex_definition_title = dex_definition_title[:MESSAGE_TITLE_LENGTH_LIMIT]

        if len(dex_definition_title) >= MESSAGE_TITLE_LENGTH_LIMIT:
            dex_definition_title = dex_definition_title[:-3]  # ellipsis
            dex_definition_title = '{}...'.format(dex_definition_title)

        dex_definition_url = '{}/{}'.format(dex_url.replace(' ', ''), dex_definition_id)
        dex_author_url = '{}/{}'.format(DEX_AUTHOR_URL, quote(dex_definition_author))

        dex_definition_footer = (
            '{}\nsursa: <a href="{}">{}</a> '
            'adăugată de: <a href="{}">{}</a>'
        ).format(
            dex_definition_url, DEX_SOURCES_URL, dex_definition_source_name,
            dex_author_url, dex_definition_author
        )

        text_limit = MAX_MESSAGE_LENGTH

        text_limit -= 1  # newline between text and url
        text_limit -= len(dex_definition_footer)  # definition footer
        text_limit -= 4  # possible end tag
        text_limit -= 3  # ellipsis

        dex_definition_html = dex_definition_html[:text_limit]

        dex_definition_html = UNFINISHED_TAG_REGEX.sub('', dex_definition_html)

        dangling_tags_groups = DANGLING_TAG_REGEX.search(dex_definition_html)

        if dangling_tags_groups is not None:
            start_tag_name = dangling_tags_groups.group(1)

            dex_definition_html = '{}...</{}>'.format(dex_definition_html, start_tag_name)

        dex_definition_html = '{}\n{}'.format(dex_definition_html, dex_definition_footer)

        if cli_args.debug:
            logger.info('Result: {}: {}'.format(dex_definition_index, dex_definition_html))

        dex_definition_result = InlineQueryResultArticle(
            id=uuid4(),
            title=dex_definition_title,
            thumb_url=DEX_THUMBNAIL_URL,
            url=dex_definition_url,
            hide_url=True,
            input_message_content=InputTextMessageContent(
                message_text=dex_definition_html,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        )

        results.append(dex_definition_result)

    results_count = len(results)

    no_results_text = None
    no_results_parameter = None

    if results_count == 0:
        no_results_text = 'Niciun rezultat'
        no_results_parameter = base64.urlsafe_b64encode(query.encode()).decode()
    else:
        results = results[:MESSAGES_COUNT_LIMIT]

    cache_time = 24 * 60 * 60

    if cli_args.debug:
        cache_time = 0

    next_offset = None

    if results_count > len(results):
        next_offset = offset + MESSAGES_COUNT_LIMIT

    inline_query.answer(
        results,
        cache_time=cache_time,
        next_offset=next_offset,
        switch_pm_text=no_results_text,
        switch_pm_parameter=no_results_parameter
    )


def error_handler(bot, update, error):
    logger.error('Update "{}" caused error "{}"'.format(update, error))


def main():
    updater = Updater(BOT_TOKEN)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command_handler, pass_args=True))
    dispatcher.add_handler(CommandHandler('restart', restart_command_handler))
    dispatcher.add_handler(CommandHandler('logs', logs_command_handler))

    dispatcher.add_handler(InlineQueryHandler(inline_query_handler))

    dispatcher.add_error_handler(error_handler)

    if cli_args.debug:
        logger.info('Started polling')

        updater.start_polling(timeout=0.01)
    else:
        if cli_args.server and not cli_args.polling:
            logger.info('Started webhook')

            if config:
                webhook = config['Webhook']

                port = int(webhook['Port'])
                key = webhook['Key']
                cert = webhook['Cert']
                url = webhook['Url'] + BOT_TOKEN

                if cli_args.set_webhook:
                    logger.info('Updated webhook')
                else:
                    updater.bot.setWebhook = (lambda *args, **kwargs: None)

                updater.start_webhook(
                    listen='0.0.0.0',
                    port=port,
                    url_path=BOT_TOKEN,
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

    if ADMIN_USER_ID:
        updater.bot.sendMessage(ADMIN_USER_ID, 'Bot has been restarted')

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

    cli_args = parser.parse_args()

    if cli_args.debug:
        logger.info('Debug')

    config = None

    try:
        config = configparser.ConfigParser()

        config.read('config.cfg')

        BOT_TOKEN = config.get('Telegram', 'Key' if cli_args.server else 'TestKey')
    except configparser.Error as error:
        logger.error('Config error: {}'.format(error))

        exit(1)

    if not BOT_TOKEN:
        logger.error('Missing bot token')

        exit(2)

    analytics = Analytics()

    try:
        ADMIN_USER_ID = config.getint('Telegram', 'Admin')

        analytics.botanToken = config.get('Botan', 'Key')
        analytics.googleToken = config.get('Google', 'Key')
    except configparser.Error as error:
        logger.warning('Config error: {}'.format(error))

    requests_cache.install_cache(expire_after=timedelta(days=1))

    if cli_args.query or cli_args.fragment:
        class Dummy:
            def __init__(self):
                self.inline_query = None

        dummy_update = Dummy()

        dummy_update.inline_query = Dummy()

        dummy_update.inline_query.from_user = Dummy()
        dummy_update.inline_query.offset = None
        dummy_update.inline_query.answer = (lambda *args, **kwargs: None)

        dummy_update.inline_query.from_user.id = None
        dummy_update.inline_query.from_user.first_name = None
        dummy_update.inline_query.from_user.last_name = None
        dummy_update.inline_query.from_user.username = None

        inline_query_handler(None, dummy_update)
    else:
        main()
