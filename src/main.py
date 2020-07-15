#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from threading import Thread

import argparse
import configparser
import datetime
import json
import logging
import os
import sys

from constants import LOGS_FORMAT, LoggerFilter

logging.basicConfig(format=LOGS_FORMAT, level=logging.INFO)

error_logging_handler = logging.FileHandler('errors.log')
error_logging_handler.setFormatter(logging.Formatter(LOGS_FORMAT))
error_logging_handler.setLevel(logging.ERROR)
error_logging_handler.addFilter(LoggerFilter(logging.ERROR))

logging.getLogger().addHandler(error_logging_handler)

warning_logging_handler = logging.FileHandler('warnings.log')
warning_logging_handler.setFormatter(logging.Formatter(LOGS_FORMAT))
warning_logging_handler.setLevel(logging.WARNING)
warning_logging_handler.addFilter(LoggerFilter(logging.WARNING))

logging.getLogger().addHandler(warning_logging_handler)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatAction, ParseMode, Update
from telegram.constants import MAX_INLINE_QUERY_RESULTS
from telegram.ext import (
    CallbackContext, CallbackQueryHandler,
    CommandHandler, InlineQueryHandler, MessageHandler,
    Filters
)
from telegram.utils.request import Request

import requests_cache

from analytics import Analytics, AnalyticsType
from constants import (
    RESULTS_CACHE_TIME,
    BUTTON_DATA_QUERY_KEY, BUTTON_DATA_OFFSET_KEY, BUTTON_DATA_LINKS_TOGGLE_KEY,
    BUTTON_DATA_IS_SUBSCRIPTION_ONBOARDING_KEY, BUTTON_DATA_SUBSCRIPTION_STATE_KEY
)
from database import User
from queue_bot import QueueBot
from queue_updater import QueueUpdater
from utils import (
    check_admin, send_no_results_message,
    get_query_definitions, get_word_of_the_day_definition, clear_definitions_cache,
    get_definition_inline_keyboard_buttons,
    send_subscription_onboarding_message_if_needed, get_subscription_notification_inline_keyboard_buttons,
    base64_encode, base64_decode
)

BOT_NAME = None
BOT_TOKEN = None

ADMIN_USER_ID = None

logger = logging.getLogger(__name__)

updater: QueueUpdater = None
analytics = None


def stop_and_restart():
    updater.stop()
    os.execl(sys.executable, sys.executable, *sys.argv)


def create_or_update_user(bot, user):
    db_user = User.create_or_update_user(user.id, user.username)

    if db_user is not None and ADMIN_USER_ID is not None:
        bot.send_message(ADMIN_USER_ID, 'New user: {}'.format(db_user.get_markdown_description()), parse_mode=ParseMode.MARKDOWN)


def start_command_handler(update: Update, context: CallbackContext):
    message = update.message
    bot = context.bot

    message_id = message.message_id
    chat_id = message.chat_id
    user = message.from_user

    query = ' '.join(context.args)

    try:
        query = base64_decode(query)
    except:
        pass

    create_or_update_user(bot, user)

    analytics.track(AnalyticsType.COMMAND, user, '/start {}'.format(query))

    if query:
        bot.send_chat_action(chat_id, ChatAction.TYPING)

        analytics.track(AnalyticsType.MESSAGE, user, query)

        links_toggle = False

        (definitions, offset) = get_query_definitions(update, query, links_toggle, analytics, cli_args, BOT_NAME)

        if len(definitions) == 0:
            send_no_results_message(bot, chat_id, message_id, query)
        else:
            inline_keyboard_buttons = get_definition_inline_keyboard_buttons(query, len(definitions), offset, links_toggle)

            reply_markup = InlineKeyboardMarkup(inline_keyboard_buttons)

            definition = definitions[offset]
            definition_content = definition.input_message_content
            definition_text = definition_content.message_text

            bot.send_message(
                chat_id, definition_text,
                reply_markup=reply_markup,
                parse_mode=definition_content.parse_mode,
                disable_web_page_preview=True,
                reply_to_message_id=message_id
            )

            send_subscription_onboarding_message_if_needed(
                bot=bot,
                user=user,
                chat_id=chat_id
            )
    else:
        reply_button = InlineKeyboardButton('Încearcă', switch_inline_query='cuvânt')
        reply_markup = InlineKeyboardMarkup([[reply_button]])

        bot.send_message(
            chat_id, (
                'Salut, sunt un bot care caută definiții pentru cuvinte folosind '
                '[dexonline.ro](http://dexonline.ro).\n'
                'Poți scrie direct cuvântul căutat aici în chat '
                'sau poți să scrii @{} _cuvânt_ în orice alt chat.'
            ).format(BOT_NAME),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

        return


def restart_command_handler(update: Update, context: CallbackContext):
    message = update.message
    bot = context.bot

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    bot.send_message(message.chat_id, 'Restarting...')

    Thread(target=stop_and_restart).start()


def logs_command_handler(update: Update, context: CallbackContext):
    message = update.message
    bot = context.bot

    chat_id = message.chat_id

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    try:
        bot.send_document(chat_id, open('errors.log', 'rb'))
    except:
        bot.send_message(chat_id, 'Log is empty')


def users_command_handler(update: Update, context: CallbackContext):
    message = update.message
    bot = context.bot

    chat_id = message.chat_id

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    bot.send_message(chat_id, User.get_users_table('updated' in context.args), parse_mode=ParseMode.MARKDOWN)


def clear_command_handler(update: Update, context: CallbackContext):
    message = update.message
    bot = context.bot

    chat_id = message.chat_id

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    for query in context.args:
        bot.send_message(chat_id, clear_definitions_cache(query))


def inline_query_handler(update: Update, context: CallbackContext):
    inline_query = update.inline_query
    bot = context.bot

    user = inline_query.from_user

    create_or_update_user(bot, user)

    query = None

    if not cli_args.fragment:
        if cli_args.query:
            query = cli_args.query
        else:
            query = inline_query.query

        if not query:
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
            user_identification += ': {}'.format(user_name)

        if user.username:
            user_identification += ' (@{})'.format(user.username)

        user_identification += ':'

        logger.info('{} {}'.format(user_identification, query))

    links_toggle = False

    (definitions, offset) = get_query_definitions(update, query, links_toggle, analytics, cli_args, BOT_NAME)

    definitions_count = len(definitions)

    no_results_text = None
    no_results_parameter = None

    if definitions_count == 0:
        no_results_text = 'Niciun rezultat'
        no_results_parameter = base64_encode(query)
    else:
        definitions = definitions[:MAX_INLINE_QUERY_RESULTS]

    cache_time = int(RESULTS_CACHE_TIME.total_seconds())

    if cli_args.debug:
        cache_time = 0

    next_offset = None

    if definitions_count > len(definitions):
        next_offset = offset + MAX_INLINE_QUERY_RESULTS

    inline_query.answer(
        definitions,
        cache_time=cache_time,
        next_offset=next_offset,
        switch_pm_text=no_results_text,
        switch_pm_parameter=no_results_parameter
    )


def message_handler(update: Update, context: CallbackContext):
    message = update.effective_message
    bot = context.bot

    message_id = message.message_id
    query = message.text
    chat_id = message.chat.id
    user = message.from_user

    create_or_update_user(bot, user)

    # Most probably the message was sent via a bot.
    if len(message.entities) > 0:
        return

    bot.send_chat_action(chat_id, ChatAction.TYPING)

    analytics.track(AnalyticsType.MESSAGE, user, query)

    links_toggle = False

    (definitions, offset) = get_query_definitions(update, query, links_toggle, analytics, cli_args, BOT_NAME)

    if len(definitions) == 0:
        send_no_results_message(bot, chat_id, message_id, query)
    else:
        inline_keyboard_buttons = get_definition_inline_keyboard_buttons(query, len(definitions), offset, links_toggle)

        reply_markup = InlineKeyboardMarkup(inline_keyboard_buttons)

        definition = definitions[offset]
        definition_content = definition.input_message_content
        definition_text = definition_content.message_text

        bot.send_message(
            chat_id, definition_text,
            reply_markup=reply_markup,
            parse_mode=definition_content.parse_mode,
            disable_web_page_preview=True,
            reply_to_message_id=message_id
        )

    send_subscription_onboarding_message_if_needed(
        bot=bot,
        user=user,
        chat_id=chat_id
    )


def message_answer_handler(update: Update, context: CallbackContext):
    callback_query = update.callback_query
    bot = context.bot

    callback_data = json.loads(callback_query.data)

    if not callback_data:
        callback_query.answer()

        return

    is_inline = callback_query.inline_message_id is not None
    chat_id = 0

    if is_inline:
        message_id = callback_query.inline_message_id
    else:
        callback_message = callback_query.message

        chat_id = callback_message.chat_id
        message_id = callback_message.message_id

    links_toggle = False

    if BUTTON_DATA_LINKS_TOGGLE_KEY in callback_data:
        links_toggle = callback_data[BUTTON_DATA_LINKS_TOGGLE_KEY]

    if BUTTON_DATA_SUBSCRIPTION_STATE_KEY in callback_data:
        state: int = callback_data[BUTTON_DATA_SUBSCRIPTION_STATE_KEY]
        user_id = update.effective_user.id

        db_user: User = User.get_or_none(User.telegram_id == user_id)

        if db_user is not None:
            is_toggling_links = state is None

            if is_toggling_links:
                is_active = db_user.subscription != User.Subscription.revoked.value
                definition = get_word_of_the_day_definition(
                    links_toggle=links_toggle,
                    cli_args=cli_args,
                    bot_name=BOT_NAME,
                    with_stop=is_active
                )

                reply_markup = definition.reply_markup

                definition_content = definition.input_message_content
                definition_text = definition_content.message_text
                parse_mode = definition_content.parse_mode

                bot.edit_message_text(
                    text=definition_text,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True
                )
            else:
                subscription = User.Subscription(state)

                db_user.subscription = subscription.value
                db_user.save()

                if BUTTON_DATA_IS_SUBSCRIPTION_ONBOARDING_KEY in callback_data:
                    bot.delete_message(
                        chat_id=chat_id,
                        message_id=message_id
                    )
                else:
                    is_active = db_user.subscription != User.Subscription.revoked.value
                    reply_markup = InlineKeyboardMarkup(get_subscription_notification_inline_keyboard_buttons(
                        links_toggle=links_toggle,
                        with_stop=is_active
                    ))

                    callback_query.edit_message_reply_markup(reply_markup)

    else:
        query = callback_data[BUTTON_DATA_QUERY_KEY]
        offset = callback_data[BUTTON_DATA_OFFSET_KEY]

        (definitions, _) = get_query_definitions(update, query, links_toggle, analytics, cli_args, BOT_NAME)

        inline_keyboard_buttons = get_definition_inline_keyboard_buttons(query, len(definitions), offset, links_toggle)

        reply_markup = InlineKeyboardMarkup(inline_keyboard_buttons)

        definition = definitions[offset]
        definition_content = definition.input_message_content
        definition_text = definition_content.message_text

        if is_inline:
            bot.edit_message_text(
                definition_text,
                inline_message_id=message_id,
                reply_markup=reply_markup,
                parse_mode=definition_content.parse_mode,
                disable_web_page_preview=True
            )
        else:
            bot.edit_message_text(
                definition_text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
                parse_mode=definition_content.parse_mode,
                disable_web_page_preview=True
            )


def word_of_the_day_job_handler(context: CallbackContext):
    bot: QueueBot = context.bot

    definition = get_word_of_the_day_definition(
        links_toggle=False,
        cli_args=cli_args,
        bot_name=BOT_NAME,
        with_stop=True
    )

    reply_markup = definition.reply_markup
    image_url = definition.url

    definition_content = definition.input_message_content
    definition_text = definition_content.message_text
    parse_mode = definition_content.parse_mode

    for user in User.select().where(User.subscription == User.Subscription.accepted.value):
        id = user.telegram_id

        bot.queue_message(
            chat_id=id,
            text=definition_text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
            disable_notification=True
        )

        bot.queue_photo(
            chat_id=id,
            photo=image_url,
            disable_notification=True
        )


def error_handler(update: Update, context: CallbackContext):
    logger.error('Update "{}" caused error "{}"'.format(json.dumps(update.to_dict(), indent=4), context.error))


def main():
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command_handler, pass_args=True))

    dispatcher.add_handler(CommandHandler('restart', restart_command_handler))
    dispatcher.add_handler(CommandHandler('logs', logs_command_handler))
    dispatcher.add_handler(CommandHandler('users', users_command_handler, pass_args=True))
    dispatcher.add_handler(CommandHandler('clear', clear_command_handler, pass_args=True))

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
                    updater.bot.set_webhook = (lambda *args, **kwargs: None)

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

            updater.start_polling(timeout=0.01)

    logger.info('Bot started. Press Ctrl-C to stop.')

    if ADMIN_USER_ID is not None:
        updater.bot.send_message(ADMIN_USER_ID, 'Bot has been restarted')

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

        BOT_NAME = config.get('Telegram', 'Name' if cli_args.server else 'TestName')
        BOT_TOKEN = config.get('Telegram', 'Key' if cli_args.server else 'TestKey')

        ADMIN_USER_ID = config.getint('Telegram', 'Admin')
    except configparser.Error as error:
        logger.error('Config error: {}'.format(error))

        sys.exit(1)

    if not BOT_TOKEN:
        logger.error('Missing bot token')

        sys.exit(2)

    request = Request(con_pool_size=8)
    queue_bot = QueueBot(
        token=BOT_TOKEN,
        request=request
    )
    updater = QueueUpdater(
        bot=queue_bot,
        use_context=True
    )
    job_queue = updater.job_queue
    analytics = Analytics()

    try:
        analytics.googleToken = config.get('Google', 'Key')
    except configparser.Error as error:
        logger.warning('Config error: {}'.format(error))

    analytics.userAgent = BOT_NAME

    requests_cache.install_cache(expire_after=RESULTS_CACHE_TIME)

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

        inline_query_handler(dummy_update, None)
    else:
        offset = datetime.timedelta(hours=2)
        timezone = datetime.timezone(offset)
        time = datetime.time(
            hour=12,
            minute=0,
            second=0,
            tzinfo=timezone
        )

        job_queue.run_daily(
            callback=word_of_the_day_job_handler,
            time=time
        )

        main()
