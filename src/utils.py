# -*- coding: utf-8 -*-

from urllib.parse import quote
from uuid import uuid4

import json
import logging

from lxml import etree, html

from telegram import (
    InlineKeyboardButton, InlineQueryResultArticle,
    InputTextMessageContent, ParseMode
)
from telegram.constants import MAX_MESSAGE_LENGTH

import requests

from analytics import AnalyticsType
from constants import (
    DEX_API_URL_FORMAT, DEX_SEARCH_URL_FORMAT,
    DEX_THUMBNAIL_URL, DEX_SOURCES_URL, DEX_AUTHOR_URL,
    DANGLING_TAG_REGEX, UNFINISHED_TAG_REGEX,
    UNICODE_SUPERSCRIPTS, MESSAGE_TITLE_LENGTH_LIMIT,
    PREVIOUS_PAGE_ICON, NEXT_PAGE_ICON, NO_PAGE_ICON
)

logger = logging.getLogger(__name__)


def check_admin(bot, message, analytics, admin_user_id):
    analytics.track(AnalyticsType.COMMAND, message.from_user, message.text)

    if not admin_user_id or message.from_user.id != admin_user_id:
        bot.sendMessage(message.chat_id, 'You are not allowed to use this command')

        return False

    return True


def get_user(update):
    try:
        user = update.message.from_user
    except (NameError, AttributeError):
        try:
            user = update.inline_query.from_user
        except (NameError, AttributeError):
            try:
                user = update.chosen_inline_result.from_user
            except (NameError, AttributeError):
                try:
                    user = update.callback_query.from_user
                except (NameError, AttributeError):
                    return None

    return user


def get_no_results_message(query):
    url = DEX_SEARCH_URL_FORMAT.format(quote(query))

    message = (
        'Niciun rezultat găsit pentru "{}". '
        'Incearcă o căutare in tot textul definițiilor [aici]({}).'
    ).format(query, url)

    return message


def send_no_results_message(bot, chat_id, query):
    bot.sendMessage(
        chat_id, get_no_results_message(query),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )


def get_definitions(update, query, analytics, cli_args):
    user = get_user(update)

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

    definitions = []

    offset_string = None
    offset = 0

    is_inline_query = update.inline_query is not None

    if is_inline_query:
        offset_string = update.inline_query.offset

    if offset_string:
        offset = int(offset_string)

        if offset < len(dex_raw_definitions):
            dex_raw_definitions = dex_raw_definitions[offset + 1:]
    elif is_inline_query:
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

        definitions.append(dex_definition_result)

    return definitions, offset


def get_inline_keyboard_buttons(query, definitions_count, offset):
    paging_buttons = []

    is_first_page = offset == 0
    is_last_page = offset == definitions_count - 1

    if is_first_page:
        previous_data = None
    else:
        previous_data = {
            'query': query,
            'offset': offset - 1
        }

    if is_last_page:
        next_data = None
    else:
        next_data = {
            'query': query,
            'offset': offset + 1
        }

    previous_button = InlineKeyboardButton(NO_PAGE_ICON if is_first_page else PREVIOUS_PAGE_ICON, callback_data=json.dumps(previous_data))
    next_button = InlineKeyboardButton(NO_PAGE_ICON if is_last_page else NEXT_PAGE_ICON, callback_data=json.dumps(next_data))

    paging_buttons.append(previous_button)
    paging_buttons.append(next_button)

    return [paging_buttons]
