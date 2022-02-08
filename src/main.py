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

import pytz
import requests_cache
import telegram.ext
import telegram.utils.request

import analytics
import constants
import custom_logger
import database
import queue_bot
import queue_updater
import telegram_utils
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


def create_or_update_user(bot: telegram.Bot, user: telegram.User) -> None:
    db_user = database.User.create_or_update_user(
        id=user.id,
        username=user.username,
        bot=bot,
        admin_id=ADMIN_USER_ID
    )

    if db_user is not None:
        prefix = 'New user:'

        bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=(
                f'{telegram_utils.escape_v2_markdown_text(prefix)} '
                f'{db_user.get_markdown_description()}'
            ),
            parse_mode=telegram.ParseMode.MARKDOWN_V2
        )


def start_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    message_id = message.message_id
    chat_id = message.chat_id
    user = message.from_user

    args = context.args or []
    query = ' '.join(args)

    try:
        query = utils.base64_decode(query)
    except UnicodeDecodeError:
        pass

    if user is not None:
        create_or_update_user(bot, user)

        analytics_handler.track(context, analytics.AnalyticsType.COMMAND, user, f'/start {query}')

    if query:
        bot.send_chat_action(chat_id, telegram.ChatAction.TYPING)

        if user is not None:
            analytics_handler.track(context, analytics.AnalyticsType.MESSAGE, user, query)

        links_toggle = False

        (definitions, offset) = utils.get_query_definitions(update, context, query, links_toggle, analytics_handler, cli_args, BOT_NAME)

        if len(definitions) == 0:
            telegram_utils.send_no_results_message(bot, chat_id, message_id, query)
        else:
            definition = definitions[offset]
            reply_markup = telegram.InlineKeyboardMarkup(definition.inline_keyboard_buttons)

            bot.send_message(
                chat_id=chat_id,
                text=definition.html,
                reply_markup=reply_markup,
                parse_mode=telegram.ParseMode.HTML,
                disable_web_page_preview=True,
                reply_to_message_id=message_id
            )

            if user is not None:
                utils.send_subscription_onboarding_message_if_needed(
                    bot=bot,
                    user=user,
                    chat_id=chat_id
                )
    else:
        reply_button = telegram.InlineKeyboardButton('Încearcă', switch_inline_query='cuvânt')
        reply_markup = telegram.InlineKeyboardMarkup([[reply_button]])

        first_phrase = 'Salut, sunt un bot care caută definiții pentru cuvinte folosind'
        link = telegram_utils.escape_v2_markdown_text_link(
            text='dexonline.ro',
            url='http://dexonline.ro'
        )

        second_phrase_1 = 'Poți scrie direct cuvântul căutat aici în chat sau poți să scrii "@'
        second_phrase_2 = '_cuvânt_"'
        second_phrase_3 = 'în orice alt chat.'

        bot.send_message(
            chat_id=chat_id,
            text=(
                f'{telegram_utils.escape_v2_markdown_text(first_phrase)} {link}{telegram_utils.ESCAPED_FULL_STOP}\n'

                f'{telegram_utils.escape_v2_markdown_text(second_phrase_1)}{BOT_NAME} '
                f'{second_phrase_2} {telegram_utils.escape_v2_markdown_text(second_phrase_3)}'
            ),
            reply_markup=reply_markup,
            parse_mode=telegram.ParseMode.MARKDOWN_V2
        )


def subscribe_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    chat_id = message.chat_id
    user = message.from_user

    if user is None:
        return

    create_or_update_user(bot, user)

    analytics_handler.track(context, analytics.AnalyticsType.COMMAND, user, '/subscribe')

    db_user: database.User = database.User.get_or_none(database.User.telegram_id == user.id)

    if db_user is None:
        return

    if db_user.subscription != database.User.Subscription.accepted.value:
        db_user.subscription = database.User.Subscription.accepted.value
        db_user.save()

        subscription_update_message = db_user.get_subscription_update_message()

        telegram_utils.send_subscription_update_message(
            bot=telegram_queue_bot,
            chat_id=ADMIN_USER_ID,
            text=subscription_update_message
        )

    utils.send_subscription_accepted_message_if_needed(
        bot=bot,
        user=user,
        chat_id=chat_id
    )


def restart_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    if not telegram_utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    bot.send_message(message.chat_id, 'Restarting...')

    threading.Thread(target=stop_and_restart).start()


def logs_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    chat_id = message.chat_id

    if not telegram_utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    try:
        bot.send_document(chat_id, open('errors.log', 'rb'))
    except telegram.TelegramError:
        bot.send_message(chat_id, 'Log is empty')


def users_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    chat_id = message.chat_id

    if not telegram_utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    args = context.args or []

    bot.send_message(
        chat_id=chat_id,
        text=database.User.get_users_table(
            sorted_by_updated_at='updated' in args,
            include_only_subscribed='subscribed' in args
        ),
        parse_mode=telegram.ParseMode.MARKDOWN_V2
    )


def clear_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    chat_id = message.chat_id

    if not telegram_utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    args = context.args or []

    for query in args:
        bot.send_message(chat_id, utils.clear_definitions_cache(query))


def inline_query_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    inline_query = update.inline_query

    if inline_query is None:
        return

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
            analytics_handler.track(context, analytics.AnalyticsType.EMPTY_QUERY, user)

            return

    if not cli_args.server:
        user_identification = f'#{user.id}'
        user_name = None

        if user.first_name and user.last_name:
            user_name = f'{user.first_name} {user.last_name}'
        elif user.first_name:
            user_name = user.first_name
        elif user.last_name:
            user_name = user.last_name

        if user_name:
            user_identification += f': {user_name}'

        if user.username:
            user_identification += f' (@{user.username})'

        user_identification += ':'

        logger.info(f'{user_identification} {query}')

    links_toggle = False

    (definitions, offset) = utils.get_query_definitions(update, context, query, links_toggle, analytics_handler, cli_args, BOT_NAME)

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
        next_offset = str(offset + telegram.constants.MAX_INLINE_QUERY_RESULTS)

    definitions_results = list(map(utils.get_inline_query_definition_result, definitions))

    inline_query.answer(
        results=definitions_results,
        cache_time=cache_time,
        next_offset=next_offset,
        switch_pm_text=no_results_text,
        switch_pm_parameter=no_results_parameter
    )


def message_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.effective_message

    if message is None:
        return

    bot = context.bot

    message_id = message.message_id
    query = message.text
    chat_id = message.chat.id
    user = message.from_user

    if user is not None:
        create_or_update_user(bot, user)

    # Most probably the message was sent via a bot.
    if len(message.entities) > 0:
        return

    bot.send_chat_action(chat_id, telegram.ChatAction.TYPING)

    if user is not None:
        analytics_handler.track(context, analytics.AnalyticsType.MESSAGE, user, query)

    links_toggle = False

    (definitions, offset) = utils.get_query_definitions(update, context, query, links_toggle, analytics_handler, cli_args, BOT_NAME)

    if len(definitions) == 0:
        telegram_utils.send_no_results_message(bot, chat_id, message_id, query or '')
    else:
        definition = definitions[offset]
        reply_markup = telegram.InlineKeyboardMarkup(definition.inline_keyboard_buttons)

        bot.send_message(
            chat_id=chat_id,
            text=definition.html,
            reply_markup=reply_markup,
            parse_mode=telegram.ParseMode.HTML,
            disable_web_page_preview=True,
            reply_to_message_id=message_id
        )

    if user is not None:
        utils.send_subscription_onboarding_message_if_needed(
            bot=bot,
            user=user,
            chat_id=chat_id
        )


def message_answer_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    callback_query = update.callback_query

    if callback_query is None:
        return

    bot = context.bot

    raw_callback_data = callback_query.data

    if not raw_callback_data:
        callback_query.answer()

        return

    callback_data = json.loads(raw_callback_data)

    if not callback_data:
        callback_query.answer()

        return

    is_inline = callback_query.inline_message_id is not None
    chat_id = 0

    message_id: typing.Union[str, int]

    wotd_date: typing.Optional[str] = None

    if constants.BUTTON_DATA_DATE_KEY in callback_data:
        wotd_date = callback_data[constants.BUTTON_DATA_DATE_KEY]

    if is_inline:
        inline_message_id = callback_query.inline_message_id

        if inline_message_id is None:
            callback_query.answer()

            return

        message_id = inline_message_id
    else:
        callback_message = callback_query.message

        if callback_message is None:
            callback_query.answer()

            return

        chat_id = callback_message.chat_id
        message_id = callback_message.message_id

        if wotd_date is None:
            text = callback_message.text
            match = constants.WORD_OF_THE_DAY_DATE_REGEX.search(text)

            if match is not None:
                raw_day = match.group('day')
                month = match.group('month')
                year = match.group('year')

                day = f'{raw_day:0>2}'

                wotd_date = f'{year}/{month}/{day}'

    links_toggle = False

    if constants.BUTTON_DATA_LINKS_TOGGLE_KEY in callback_data:
        links_toggle = callback_data[constants.BUTTON_DATA_LINKS_TOGGLE_KEY]

    if constants.BUTTON_DATA_SUBSCRIPTION_STATE_KEY in callback_data:
        state: int = callback_data[constants.BUTTON_DATA_SUBSCRIPTION_STATE_KEY]
        user = update.effective_user

        if user is None:
            callback_query.answer()

            return

        user_id = user.id

        db_user: database.User = database.User.get_or_none(database.User.telegram_id == user_id)

        if db_user is not None:
            is_toggling_links = state is None

            if is_toggling_links:
                is_active = db_user.subscription != database.User.Subscription.revoked.value
                definition = utils.get_word_of_the_day_definition(
                    date=wotd_date,
                    links_toggle=links_toggle,
                    cli_args=cli_args,
                    bot_name=BOT_NAME,
                    with_stop=is_active
                )
                reply_markup = telegram.InlineKeyboardMarkup(definition.inline_keyboard_buttons)

                bot.edit_message_text(
                    text=definition.html,
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=reply_markup,
                    parse_mode=telegram.ParseMode.HTML,
                    disable_web_page_preview=True
                )
            else:
                subscription = database.User.Subscription(state)

                db_user.subscription = subscription.value
                db_user.save()

                if constants.BUTTON_DATA_IS_SUBSCRIPTION_ONBOARDING_KEY in callback_data:
                    try:
                        bot.delete_message(
                            chat_id=chat_id,
                            message_id=message_id
                        )
                    except telegram.TelegramError:
                        pass
                else:
                    is_active = db_user.subscription != database.User.Subscription.revoked.value
                    reply_markup = telegram.InlineKeyboardMarkup(utils.get_subscription_notification_inline_keyboard_buttons(
                        date=wotd_date,
                        links_toggle=links_toggle,
                        with_stop=is_active
                    ))

                    callback_query.edit_message_reply_markup(reply_markup)

                subscription_update_message = db_user.get_subscription_update_message()

                telegram_utils.send_subscription_update_message(
                    bot=bot,
                    chat_id=ADMIN_USER_ID,
                    text=subscription_update_message
                )

                utils.send_subscription_accepted_message_if_needed(
                    bot=bot,
                    user=user,
                    chat_id=chat_id
                )
    else:
        query: typing.Optional[str] = callback_data[constants.BUTTON_DATA_QUERY_KEY]
        offset = callback_data[constants.BUTTON_DATA_OFFSET_KEY]

        (definitions, _offset) = utils.get_query_definitions(update, context, query, links_toggle, analytics_handler, cli_args, BOT_NAME)
        definition = definitions[offset]
        reply_markup = telegram.InlineKeyboardMarkup(definition.inline_keyboard_buttons)

        if is_inline:
            bot.edit_message_text(
                text=definition.html,
                inline_message_id=message_id,
                reply_markup=reply_markup,
                parse_mode=telegram.ParseMode.HTML,
                disable_web_page_preview=True
            )
        else:
            bot.edit_message_text(
                text=definition.html,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
                parse_mode=telegram.ParseMode.HTML,
                disable_web_page_preview=True
            )


def word_of_the_day_job_handler(context: telegram.ext.CallbackContext) -> None:
    definition = utils.get_word_of_the_day_definition(
        date=None,
        links_toggle=False,
        cli_args=cli_args,
        bot_name=BOT_NAME,
        with_stop=True
    )
    reply_markup = telegram.InlineKeyboardMarkup(definition.inline_keyboard_buttons)
    users = database.User.select().where(database.User.subscription == database.User.Subscription.accepted.value)

    for user in users:
        id = user.telegram_id

        telegram_queue_bot.queue_message(
            chat_id=id,
            text=definition.html,
            reply_markup=reply_markup,
            parse_mode=telegram.ParseMode.HTML,
            disable_web_page_preview=True,
            disable_notification=True
        )

        url = definition.image_url

        if url is not None:
            caption = f'© imagine {definition.image_author}'

            if url.endswith('gif'):
                telegram_queue_bot.queue_animation(
                    chat_id=id,
                    animation=url,
                    caption=caption,
                    disable_notification=True
                )
            else:
                telegram_queue_bot.queue_photo(
                    chat_id=id,
                    photo=url,
                    caption=caption,
                    disable_notification=True
                )

    sent_messages = len(users)

    telegram_queue_bot.queue_message(
        chat_id=ADMIN_USER_ID,
        text=f'''Sent {sent_messages} word of the day message{'s' if sent_messages > 1 else ''}'''
    )


def error_handler(update: object, context: telegram.ext.CallbackContext) -> None:
    update_str = update.to_dict() if isinstance(update, telegram.Update) else str(update)

    logger.error(f'Update "{json.dumps(update_str, indent=4, ensure_ascii=False)}" caused error "{context.error}"')


def queued_message_error_handler(chat_id: int, exception: Exception) -> None:
    try:
        raise exception
    except telegram.error.Unauthorized:
        db_user: database.User = database.User.get_or_none(database.User.telegram_id == chat_id)
        blocked_status = database.User.Subscription.blocked.value

        if db_user is not None and db_user.subscription != blocked_status:
            db_user.subscription = blocked_status
            db_user.save()

            subscription_update_message = db_user.get_subscription_update_message()

            telegram_utils.send_subscription_update_message(
                bot=telegram_queue_bot,
                chat_id=ADMIN_USER_ID,
                text=subscription_update_message
            )


def main() -> None:
    dispatcher = updater.dispatcher

    dispatcher.add_handler(telegram.ext.CommandHandler('start', start_command_handler, pass_args=True))
    dispatcher.add_handler(telegram.ext.CommandHandler('subscribe', subscribe_command_handler))

    dispatcher.add_handler(telegram.ext.CommandHandler('restart', restart_command_handler))
    dispatcher.add_handler(telegram.ext.CommandHandler('logs', logs_command_handler))
    dispatcher.add_handler(telegram.ext.CommandHandler('users', users_command_handler, pass_args=True))
    dispatcher.add_handler(telegram.ext.CommandHandler('clear', clear_command_handler, pass_args=True))

    dispatcher.add_handler(telegram.ext.InlineQueryHandler(inline_query_handler, run_async=True))

    dispatcher.add_handler(telegram.ext.MessageHandler(telegram.ext.Filters.text, message_handler, run_async=True))
    dispatcher.add_handler(telegram.ext.CallbackQueryHandler(message_answer_handler, run_async=True))

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
                    setattr(updater.bot, 'set_webhook', (lambda *args, **kwargs: False))

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
        logger.error(f'Config error: {error}')

        sys.exit(1)

    if not BOT_TOKEN:
        logger.error('Missing bot token')

        sys.exit(2)

    request = telegram.utils.request.Request(con_pool_size=8)
    telegram_queue_bot = queue_bot.QueueBot(
        token=BOT_TOKEN,
        request=request,
        exception_handler=queued_message_error_handler
    )
    updater = queue_updater.QueueUpdater(
        bot=telegram_queue_bot,
        use_context=True
    )
    job_queue = updater.job_queue
    analytics_handler = analytics.AnalyticsHandler()

    try:
        analytics_handler.googleToken = config.get('Google', 'Key')
    except configparser.Error as error:
        logger.warning(f'Config error: {error}')

    analytics_handler.userAgent = BOT_NAME

    requests_cache.install_cache(expire_after=constants.RESULTS_CACHE_TIME)

    if cli_args.query or cli_args.fragment:
        dummy_inline_query = telegram.InlineQuery(
            id='0',
            from_user=telegram.User(
                id=0,
                first_name='Dummy',
                is_bot=False
            ),
            query='',
            offset=''
        )

        setattr(dummy_inline_query, 'answer', (lambda *args, **kwargs: True))

        dummy_update = telegram.Update(0)
        dummy_update.inline_query = dummy_inline_query

        dummy_context = telegram.ext.CallbackContext(updater.dispatcher)

        inline_query_handler(dummy_update, dummy_context)
    else:
        timezone = pytz.timezone('Europe/Bucharest')
        time = datetime.time(
            hour=12,
            minute=0,
            second=0
        )
        date = datetime.datetime.combine(datetime.datetime.today(), time)
        local_time = timezone.localize(date).timetz()

        job_queue.run_daily(
            callback=word_of_the_day_job_handler,
            time=local_time
        )

        main()
