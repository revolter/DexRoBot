#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import configparser
import datetime
import json
import logging
import os
import sys
import threading
import typing

import requests_cache
import telegram
import telegram.ext
import telegram.utils.request

import analytics
import constants
import custom_logger
import database
import queue_bot
import queue_updater
import utils

custom_logger.configure_root_logger()

logger = logging.getLogger(__name__)

BOT_NAME: str
BOT_TOKEN: str

ADMIN_USER_ID: int

updater: queue_updater.QueueUpdater
analytics_handler: analytics.AnalyticsHandler


def stop_and_restart() -> None:
    updater.stop()
    os.execl(sys.executable, sys.executable, *sys.argv)


def create_or_update_user(bot: queue_bot.QueueBot, user: database.User) -> None:
    db_user = database.User.create_or_update_user(user.id, user.username)

    if db_user is not None:
        bot.send_message(ADMIN_USER_ID, 'New user: {}'.format(db_user.get_markdown_description()), parse_mode=telegram.ParseMode.MARKDOWN)


def start_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext):
    message = update.message
    bot = context.bot

    message_id = message.message_id
    chat_id = message.chat_id
    user = message.from_user

    query = ' '.join(context.args)

    try:
        query = utils.base64_decode(query)
    except UnicodeDecodeError:
        pass

    create_or_update_user(bot, user)

    analytics_handler.track(analytics.AnalyticsType.COMMAND, user, '/start {}'.format(query))

    if query:
        bot.send_chat_action(chat_id, telegram.ChatAction.TYPING)

        analytics_handler.track(analytics.AnalyticsType.MESSAGE, user, query)

        links_toggle = False

        (definitions, offset) = utils.get_query_definitions(update, query, links_toggle, analytics_handler, cli_args, BOT_NAME)

        if len(definitions) == 0:
            utils.send_no_results_message(bot, chat_id, message_id, query)
        else:
            inline_keyboard_buttons = utils.get_definition_inline_keyboard_buttons(query, len(definitions), offset, links_toggle)

            reply_markup = telegram.InlineKeyboardMarkup(inline_keyboard_buttons)

            definition = definitions[offset]
            definition_content = typing.cast(telegram.InputTextMessageContent, definition.input_message_content)
            definition_text = definition_content.message_text

            bot.send_message(
                chat_id, definition_text,
                reply_markup=reply_markup,
                parse_mode=definition_content.parse_mode,
                disable_web_page_preview=True,
                reply_to_message_id=message_id
            )

            utils.send_subscription_onboarding_message_if_needed(
                bot=bot,
                user=user,
                chat_id=chat_id
            )
    else:
        reply_button = telegram.InlineKeyboardButton('Încearcă', switch_inline_query='cuvânt')
        reply_markup = telegram.InlineKeyboardMarkup([[reply_button]])

        bot.send_message(
            chat_id, (
                'Salut, sunt un bot care caută definiții pentru cuvinte folosind '
                '[dexonline.ro](http://dexonline.ro).\n'
                'Poți scrie direct cuvântul căutat aici în chat '
                'sau poți să scrii @{} _cuvânt_ în orice alt chat.'
            ).format(BOT_NAME),
            reply_markup=reply_markup,
            parse_mode=telegram.ParseMode.MARKDOWN
        )

        return


def restart_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext):
    message = update.message
    bot = context.bot

    if not utils.check_admin(bot, message, analytics_handler, ADMIN_USER_ID):
        return

    bot.send_message(message.chat_id, 'Restarting...')

    threading.Thread(target=stop_and_restart).start()


def logs_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext):
    message = update.message
    bot = context.bot

    chat_id = message.chat_id

    if not utils.check_admin(bot, message, analytics_handler, ADMIN_USER_ID):
        return

    try:
        bot.send_document(chat_id, open('errors.log', 'rb'))
    except telegram.TelegramError:
        bot.send_message(chat_id, 'Log is empty')


def users_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext):
    message = update.message
    bot = context.bot

    chat_id = message.chat_id

    if not utils.check_admin(bot, message, analytics_handler, ADMIN_USER_ID):
        return

    args = context.args

    bot.send_message(chat_id, database.User.get_users_table(
        sorted_by_updated_at='updated' in args,
        include_only_subscribed='subscribed' in args
    ), parse_mode=telegram.ParseMode.MARKDOWN)


def clear_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext):
    message = update.message
    bot = context.bot

    chat_id = message.chat_id

    if not utils.check_admin(bot, message, analytics_handler, ADMIN_USER_ID):
        return

    for query in context.args:
        bot.send_message(chat_id, utils.clear_definitions_cache(query))


def inline_query_handler(update: telegram.Update, context: telegram.ext.CallbackContext):
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
            analytics_handler.track(analytics.AnalyticsType.EMPTY_QUERY, user, None)

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

    (definitions, offset) = utils.get_query_definitions(update, query, links_toggle, analytics_handler, cli_args, BOT_NAME)

    definitions_count = len(definitions)

    no_results_text = None
    no_results_parameter = None

    if definitions_count == 0:
        no_results_text = 'Niciun rezultat'
        no_results_parameter = utils.base64_encode(query) if query is not None else ''
    else:
        definitions = definitions[:telegram.constants.MAX_INLINE_QUERY_RESULTS]

    cache_time = int(constants.RESULTS_CACHE_TIME.total_seconds())

    if cli_args.debug:
        cache_time = 0

    next_offset = None

    if definitions_count > len(definitions):
        next_offset = offset + telegram.constants.MAX_INLINE_QUERY_RESULTS

    inline_query.answer(
        definitions,
        cache_time=cache_time,
        next_offset=next_offset,
        switch_pm_text=no_results_text,
        switch_pm_parameter=no_results_parameter
    )


def message_handler(update: telegram.Update, context: telegram.ext.CallbackContext):
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

    bot.send_chat_action(chat_id, telegram.ChatAction.TYPING)

    analytics_handler.track(analytics.AnalyticsType.MESSAGE, user, query)

    links_toggle = False

    (definitions, offset) = utils.get_query_definitions(update, query, links_toggle, analytics_handler, cli_args, BOT_NAME)

    if len(definitions) == 0:
        utils.send_no_results_message(bot, chat_id, message_id, query)
    else:
        inline_keyboard_buttons = utils.get_definition_inline_keyboard_buttons(query, len(definitions), offset, links_toggle)

        reply_markup = telegram.InlineKeyboardMarkup(inline_keyboard_buttons)

        definition = definitions[offset]
        definition_content = typing.cast(telegram.InputTextMessageContent, definition.input_message_content)
        definition_text = definition_content.message_text

        bot.send_message(
            chat_id, definition_text,
            reply_markup=reply_markup,
            parse_mode=definition_content.parse_mode,
            disable_web_page_preview=True,
            reply_to_message_id=message_id
        )

    utils.send_subscription_onboarding_message_if_needed(
        bot=bot,
        user=user,
        chat_id=chat_id
    )


def message_answer_handler(update: telegram.Update, context: telegram.ext.CallbackContext):
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

    if constants.BUTTON_DATA_LINKS_TOGGLE_KEY in callback_data:
        links_toggle = callback_data[constants.BUTTON_DATA_LINKS_TOGGLE_KEY]

    if constants.BUTTON_DATA_SUBSCRIPTION_STATE_KEY in callback_data:
        state: int = callback_data[constants.BUTTON_DATA_SUBSCRIPTION_STATE_KEY]
        user_id = update.effective_user.id

        db_user: database.User = database.User.get_or_none(database.User.telegram_id == user_id)

        if db_user is not None:
            is_toggling_links = state is None

            if is_toggling_links:
                is_active = db_user.subscription != database.User.Subscription.revoked.value
                definition = utils.get_word_of_the_day_definition(
                    links_toggle=links_toggle,
                    cli_args=cli_args,
                    bot_name=BOT_NAME,
                    with_stop=is_active
                )

                reply_markup = definition.reply_markup

                definition_content = typing.cast(telegram.InputTextMessageContent, definition.input_message_content)
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
                subscription = database.User.Subscription(state)

                db_user.subscription = subscription.value
                db_user.save()

                if constants.BUTTON_DATA_IS_SUBSCRIPTION_ONBOARDING_KEY in callback_data:
                    bot.delete_message(
                        chat_id=chat_id,
                        message_id=message_id
                    )
                else:
                    is_active = db_user.subscription != database.User.Subscription.revoked.value
                    reply_markup = telegram.InlineKeyboardMarkup(utils.get_subscription_notification_inline_keyboard_buttons(
                        links_toggle=links_toggle,
                        with_stop=is_active
                    ))

                    callback_query.edit_message_reply_markup(reply_markup)

    else:
        query: typing.Optional[str] = callback_data[constants.BUTTON_DATA_QUERY_KEY]
        offset = callback_data[constants.BUTTON_DATA_OFFSET_KEY]

        (definitions, _offset) = utils.get_query_definitions(update, query, links_toggle, analytics_handler, cli_args, BOT_NAME)

        inline_keyboard_buttons = utils.get_definition_inline_keyboard_buttons(query, len(definitions), offset, links_toggle)

        reply_markup = telegram.InlineKeyboardMarkup(inline_keyboard_buttons)

        definition = definitions[offset]
        definition_content = typing.cast(telegram.InputTextMessageContent, definition.input_message_content)
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


def word_of_the_day_job_handler(context: telegram.ext.CallbackContext):
    bot: queue_bot.QueueBot = context.bot

    definition = utils.get_word_of_the_day_definition(
        links_toggle=False,
        cli_args=cli_args,
        bot_name=BOT_NAME,
        with_stop=True
    )

    reply_markup = definition.reply_markup
    image_url = definition.url

    definition_content = typing.cast(telegram.InputTextMessageContent, definition.input_message_content)
    definition_text = definition_content.message_text
    parse_mode = definition_content.parse_mode

    users = database.User.select().where(database.User.subscription == database.User.Subscription.accepted.value)

    for user in users:
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

    sent_messages = len(users)

    bot.queue_message(ADMIN_USER_ID, 'Sent {} word of the day message{}'.format(sent_messages, 's' if sent_messages > 1 else ''))


def error_handler(update: telegram.Update, context: telegram.ext.CallbackContext):
    logger.error('Update "{}" caused error "{}"'.format(json.dumps(update.to_dict(), indent=4), context.error))


def main() -> None:
    dispatcher = updater.dispatcher

    dispatcher.add_handler(telegram.ext.CommandHandler('start', start_command_handler, pass_args=True))

    dispatcher.add_handler(telegram.ext.CommandHandler('restart', restart_command_handler))
    dispatcher.add_handler(telegram.ext.CommandHandler('logs', logs_command_handler))
    dispatcher.add_handler(telegram.ext.CommandHandler('users', users_command_handler, pass_args=True))
    dispatcher.add_handler(telegram.ext.CommandHandler('clear', clear_command_handler, pass_args=True))

    dispatcher.add_handler(telegram.ext.InlineQueryHandler(inline_query_handler))

    dispatcher.add_handler(telegram.ext.MessageHandler(telegram.ext.Filters.text, message_handler))
    dispatcher.add_handler(telegram.ext.CallbackQueryHandler(message_answer_handler))

    if cli_args.debug:
        logger.info('Started polling')

        updater.start_polling(timeout=0.01)
    else:
        dispatcher.add_error_handler(error_handler)

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

    request = telegram.utils.request.Request(con_pool_size=8)
    queue_bot = queue_bot.QueueBot(
        token=BOT_TOKEN,
        request=request
    )
    updater = queue_updater.QueueUpdater(
        bot=queue_bot,
        use_context=True
    )
    job_queue = updater.job_queue
    analytics_handler = analytics.AnalyticsHandler()

    try:
        analytics_handler.googleToken = config.get('Google', 'Key')
    except configparser.Error as error:
        logger.warning('Config error: {}'.format(error))

    analytics_handler.userAgent = BOT_NAME

    requests_cache.install_cache(expire_after=constants.RESULTS_CACHE_TIME)

    if cli_args.query or cli_args.fragment:
        dummy_inline_query = telegram.InlineQuery(
            id=0,
            from_user=telegram.User(
                id=0,
                first_name='Dummy',
                is_bot=False
            ),
            query=None,
            offset=None
        )
        dummy_inline_query.answer = (lambda *args, **kwargs: None)

        dummy_update = telegram.Update(0)
        dummy_update.inline_query = dummy_inline_query

        dummy_context = telegram.ext.CallbackContext(updater.dispatcher)

        inline_query_handler(dummy_update, dummy_context)
    else:
        timezone_offset = datetime.timedelta(hours=2)
        timezone = datetime.timezone(timezone_offset)
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
