#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from uuid import uuid4

import argparse
import base64
import configparser
import logging
import os
import sys
import time

from botanio import botan

from lxml import etree, html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, ParseMode
from telegram.ext import CommandHandler, InlineQueryHandler, Updater
from telegram.constants import MAX_MESSAGE_LENGTH

import requests

from constants import *

BOT_TOKEN = None

ADMIN_USER_ID = None

BOTAN_TOKEN = None
GOOGLE_TOKEN = None

logging.basicConfig(format=LOGS_FORMAT, level=logging.INFO)

logger = logging.getLogger(__name__)

errorHandler = logging.FileHandler('errors.log')
errorHandler.setFormatter(logging.Formatter(LOGS_FORMAT))
errorHandler.setLevel(logging.ERROR)

logger.addHandler(errorHandler)

def start_handler(bot, update):
    message = update.message
    command = message.text
    chat_id = message.chat_id

    query = COMMAND_QUERY_EXTRACT_REGEX.sub('', command)
    query = base64.urlsafe_b64decode(query)

    if not query:
        reply_button = InlineKeyboardButton('Încearcă', switch_inline_query='cuvânt')
        reply_markup = InlineKeyboardMarkup([[reply_button]])

        bot.sendMessage(
            chat_id,
            (
                'Salut, sunt un bot care caută definiții pentru cuvinte folosind '
                '[dexonline.ro](http://dexonline.ro). '
                'Încearcă să scrii @DexRoBot _cuvânt_ în orice chat.'
            ),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

        return

    url = DEX_SEARCH_URL_FORMAT.format(query)

    reply = 'Niciun rezultat găsit pentru "{}". Incearcă o căutare in tot textul definițiilor [aici]({}).'.format(query, url)

    bot.sendMessage(
        chat_id=chat_id,
        text=reply,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

def restart_handler(bot, update):
    chat_id = update.message.chat_id

    if not ADMIN_USER_ID or update.message.from_user.id != ADMIN_USER_ID:
        bot.sendMessage(chat_id, 'You are not allowed to restart the bot')

        return

    bot.sendMessage(chat_id, 'Restarting after 1 second...')

    time.sleep(1)

    os.execl(sys.executable, sys.executable, *sys.argv)

def inline_query_handler(bot, update):
    inline_query = update.inline_query

    if args.fragment:
        query = None
    else:
        if args.query:
            query = args.query
        else:
            query = inline_query.query

        if not query:
            logger.warning('Empty query')

            return

    user = inline_query.from_user

    if not args.server:
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

    if args.fragment:
        dex_url = 'debug'

        dex_raw_definitions = [{
            'id': 0,
            'htmlRep': args.fragment,
            'sourceName': None,
            'userNick': None
        }]
    else:
        dex_api_url = DEX_API_URL_FORMAT.format(query)

        dex_raw_response = requests.get(dex_api_url).json()

        dex_raw_definitions = dex_raw_response['definitions']

        dex_url = dex_api_url[:-5] # /json

    # set the index of the definitions
    for index in range(len(dex_raw_definitions)):
        dex_raw_definitions[index]['index'] = index

    if args.index is not None:
        if args.index >= len(dex_raw_definitions):
            logger.warning('Index out of bounds')

            return

        dex_raw_definitions = [dex_raw_definitions[args.index]]

    results = list()

    offset_string = update.inline_query.offset
    offset = 0

    if offset_string:
        offset = int(offset_string)

        if offset < len(dex_raw_definitions):
            dex_raw_definitions = dex_raw_definitions[offset + 1:]
    else:
        if BOTAN_TOKEN:
            botan_track = botan.track(BOTAN_TOKEN, user, {'query': query}, 'inline_query')

            logger.info('Botan track: {}'.format(botan_track))

        if GOOGLE_TOKEN:
            google_analytics_url = GOOGLE_ANALYTICS_BASE_URL.format(GOOGLE_TOKEN, user.id, 'inline_query', query)

            google_analytics_response = requests.get(google_analytics_url, headers=GOOGLE_HEADERS)

            if not str(google_analytics_response.status_code).startswith('2'):
                logger.error('Google analytics error: {}: {}').format(google_analytics_response.status_code, google_analytics_response.text)

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
                supNumber = int(sup.text_content())

                if 0 <= supNumber <= 9:
                    sup.text = UNICODE_SUPERSCRIPTS[supNumber]

            etree.strip_tags(child, '*')

            if not child.tag in ['b', 'i']:
                child.tag = 'i'

            child.attrib.clear() # etree.strip_attributes(child, '*') should work too

            child_string = html.tostring(child).decode()

            dex_definition_html = '{}{}'.format(dex_definition_html, child_string)

            dex_definition_title = '{}{}'.format(dex_definition_title, child.text_content())

            if child.tail:
                dex_definition_title = '{}{}'.format(dex_definition_title, child.tail)

        if args.debug:
            dex_definition_title = '{}: {}'.format(dex_definition_index, dex_definition_title)

        dex_definition_title = dex_definition_title[:MESSAGE_TITLE_LENGTH_LIMIT + 1]

        if len(dex_definition_title) >= MESSAGE_TITLE_LENGTH_LIMIT:
            dex_definition_title[:-3] # ellipsis
            dex_definition_title = '{}...'.format(dex_definition_title)

        dex_definition_url = '{}/{}'.format(dex_url.replace(' ', ''), dex_definition_id)
        dex_author_url = '{}/{}'.format(DEX_AUTHOR_URL, dex_definition_author)

        dex_definition_footer = '{}\nsursa: <a href="{}">{}</a> adăugată de: <a href="{}">{}</a>'.format(dex_definition_url, DEX_SOURCES_URL, dex_definition_source_name, dex_author_url, dex_definition_author)

        text_limit = MAX_MESSAGE_LENGTH

        text_limit -= 1 # newline between text and url
        text_limit -= len(dex_definition_footer) # definition footer
        text_limit -= 4 # possible end tag
        text_limit -= 3 # ellipsis

        dex_definition_html = dex_definition_html[:text_limit]

        dex_definition_html = UNFINISHED_TAG_REGEX.sub('', dex_definition_html)

        dangling_tags_groups = DANGLING_TAG_REGEX.search(dex_definition_html)

        if dangling_tags_groups is not None:
            start_tag_name = dangling_tags_groups.group(1)

            dex_definition_html = '{}...</{}>'.format(dex_definition_html, start_tag_name)

        dex_definition_html = '{}\n{}'.format(dex_definition_html, dex_definition_footer)

        if args.debug:
            logger.info('Result: {}: {}'.format(dex_definition_index, dex_definition_html))

        dex_definition_result = InlineQueryResultArticle(
            id=uuid4(),
            title=dex_definition_title,
            thumb_url=DEX_THUMBNAIL_URL,
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
        results = results[:MESSAGES_COUNT_LIMIT + 1]

    cache_time = 24 * 60 * 60

    if args.debug:
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

    dispatcher.add_handler(CommandHandler('start', start_handler))
    dispatcher.add_handler(CommandHandler('restart', restart_handler))

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
                url = webhook['Url'] + BOT_TOKEN

                if args.set_webhook:
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

    args = parser.parse_args()

    if args.debug:
        logger.info('Debug')

    try:
        config = configparser.ConfigParser()

        config.read('config.cfg')

        BOT_TOKEN = config.get('Telegram', 'Key' if args.server else 'TestKey')
    except configparser.Error as error:
        logger.error('Config error: {}'.format(error))

        exit(1)

    if not BOT_TOKEN:
        logger.error('Missing bot token')

        exit(2)

    try:
        ADMIN_USER_ID = config.getint('Telegram', 'Admin')

        BOTAN_TOKEN = config.get('Botan', 'Key')
        GOOGLE_TOKEN = config.get('Google', 'Key')
    except configparser.Error as error:
        logger.warning('Config error: {}'.format(error))

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
