# -*- coding: utf-8 -*-

import typing
import urllib.parse

import telegram.utils.helpers

import analytics
import constants


def check_admin(bot: telegram.Bot, message: telegram.Message, analytics_handler: analytics.AnalyticsHandler, admin_user_id: int) -> bool:
    analytics_handler.track(analytics.AnalyticsType.COMMAND, message.from_user, message.text)

    if message.from_user.id != admin_user_id:
        bot.send_message(message.chat_id, 'You are not allowed to use this command')

        return False

    return True


def get_no_results_message(query: str) -> str:
    url = constants.DEX_SEARCH_URL_FORMAT.format(urllib.parse.quote(query))
    url_text = escape_v2_markdown_text_link(
        text='aici',
        url=url
    )

    first_phrase = f'Niciun rezultat găsit pentru "{query}".'
    second_phrase = 'Incearcă o căutare in tot textul definițiilor'

    return (
        f'{escape_v2_markdown_text(first_phrase)} '
        f'{escape_v2_markdown_text(second_phrase)} '
        f'{url_text}{ESCAPED_FULL_STOP}'
    )


def send_no_results_message(bot: telegram.Bot, chat_id: int, message_id: int, query: str) -> None:
    bot.send_message(
        chat_id=chat_id,
        text=get_no_results_message(query),
        parse_mode=telegram.ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
        reply_to_message_id=message_id
    )


def escape_v2_markdown_text(text: str, entity_type: typing.Optional[str] = None) -> str:
    return telegram.utils.helpers.escape_markdown(
        text=text,
        version=2,
        entity_type=entity_type
    )


def escape_v2_markdown_text_link(text: str, url: str) -> str:
    escaped_text = escape_v2_markdown_text(text)
    escaped_url = escape_v2_markdown_text(
        text=url,
        entity_type=telegram.MessageEntity.TEXT_LINK
    )

    return f'[{escaped_text}]({escaped_url})'


ESCAPED_FULL_STOP = escape_v2_markdown_text('.')
ESCAPED_VERTICAL_LINE = escape_v2_markdown_text('|')
