#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import timedelta

import argparse
import base64
import configparser
import json
import logging
import os
import sys
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatAction, ParseMode
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, InlineQueryHandler, MessageHandler,
    Filters, Updater
)

import requests_cache

from analytics import Analytics, AnalyticsType
from constants import LOGS_FORMAT, MESSAGES_COUNT_LIMIT
from database import User
from utils import check_admin, send_no_results_message, get_definitions, get_inline_keyboard_buttons

BOT_TOKEN = None

ADMIN_USER_ID = None

logging.basicConfig(format=LOGS_FORMAT, level=logging.INFO)

error_logging_handler = logging.FileHandler('errors.log')
error_logging_handler.setFormatter(logging.Formatter(LOGS_FORMAT))
error_logging_handler.setLevel(logging.ERROR)

logging.getLogger().addHandler(error_logging_handler)

logger = logging.getLogger(__name__)

analytics = None


def start_command_handler(bot, update, args):
    message = update.message
    chat_id = message.chat_id
    user = message.from_user

    query = ' '.join(args)

    try:
        query = base64.urlsafe_b64decode(query).decode('utf-8')
    except:
        pass

    analytics.track(AnalyticsType.COMMAND, user, '/start {}'.format(query))

    User.create_user(user.id, user.username)

    if not query:
        reply_button = InlineKeyboardButton('Încearcă', switch_inline_query='cuvânt')
        reply_markup = InlineKeyboardMarkup([[reply_button]])

        bot.sendMessage(
            chat_id, (
                'Salut, sunt un bot care caută definiții pentru cuvinte folosind '
                '[dexonline.ro](http://dexonline.ro).\n'
                'Poți scrie direct cuvântul căutat aici în chat '
                'sau poți să scrii @DexRoBot _cuvânt_ în orice alt chat.'
            ),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

        return

    send_no_results_message(bot, chat_id, query)


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
        bot.sendDocument(chat_id, open('errors.log', 'rb'))
    except:
        bot.sendMessage(chat_id, 'Log is empty')


def users_command_handler(bot, update):
    message = update.message
    chat_id = message.chat_id

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    bot.sendMessage(chat_id, User.get_users_table())


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

    (definitions, offset) = get_definitions(update, query, analytics, cli_args)

    definitions_count = len(definitions)

    no_results_text = None
    no_results_parameter = None

    if definitions_count == 0:
        no_results_text = 'Niciun rezultat'
        no_results_parameter = base64.urlsafe_b64encode(query.encode()).decode()
    else:
        definitions = definitions[:MESSAGES_COUNT_LIMIT]

    cache_time = int(timedelta(hours=1).total_seconds())

    if cli_args.debug:
        cache_time = 0

    next_offset = None

    if definitions_count > len(definitions):
        next_offset = offset + MESSAGES_COUNT_LIMIT

    inline_query.answer(
        definitions,
        cache_time=cache_time,
        next_offset=next_offset,
        switch_pm_text=no_results_text,
        switch_pm_parameter=no_results_parameter
    )


def message_handler(bot, update):
    message = update.message
    query = message.text
    chat_id = message.chat.id
    user = message.from_user

    if len(message.entities) > 0:  # most probably the message was sent via a bot
        return

    bot.sendChatAction(chat_id, ChatAction.TYPING)

    analytics.track(AnalyticsType.MESSAGE, user, query)

    (definitions, offset) = get_definitions(update, query, analytics, cli_args)

    if len(definitions) == 0:
        send_no_results_message(bot, chat_id, query)
    else:
        buttons = get_inline_keyboard_buttons(query, len(definitions), offset)

        reply_markup = InlineKeyboardMarkup(buttons)

        definition = definitions[offset]
        definition_content = definition.input_message_content
        definition_text = definition_content.message_text

        bot.sendMessage(
            chat_id, definition_text,
            reply_markup=reply_markup,
            parse_mode=definition_content.parse_mode,
            disable_web_page_preview=True
        )


def message_answer_handler(bot, update):
    callback_query = update.callback_query
    callback_message = callback_query.message
    callback_data = json.loads(callback_query.data)

    chat_id = callback_message.chat_id
    message_id = callback_message.message_id

    query = callback_data['query']
    offset = callback_data['offset']

    (definitions, _) = get_definitions(update, query, analytics, cli_args)

    buttons = get_inline_keyboard_buttons(query, len(definitions), offset)

    reply_markup = InlineKeyboardMarkup(buttons)

    definition = definitions[offset]
    definition_content = definition.input_message_content
    definition_text = definition_content.message_text

    bot.editMessageText(
        definition_text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=reply_markup,
        parse_mode=definition_content.parse_mode,
        disable_web_page_preview=True
    )


def error_handler(bot, update, error):
    logger.error('Update "{}" caused error "{}"'.format(update, error))


def main():
    updater = Updater(BOT_TOKEN)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command_handler, pass_args=True))

    dispatcher.add_handler(CommandHandler('restart', restart_command_handler))
    dispatcher.add_handler(CommandHandler('logs', logs_command_handler))
    dispatcher.add_handler(CommandHandler('users', users_command_handler))

    dispatcher.add_handler(InlineQueryHandler(inline_query_handler))

    dispatcher.add_handler(MessageHandler(Filters.text, message_handler))
    dispatcher.add_handler(CallbackQueryHandler(message_answer_handler))

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
