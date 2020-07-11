# -*- coding: utf-8 -*-

from html import escape
from urllib.parse import quote
from uuid import uuid4

import base64
import json
import logging

from lxml import etree, html
from lxml.html.builder import A

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle,
    InputTextMessageContent, ParseMode
)
from telegram.constants import MAX_MESSAGE_LENGTH

import requests
import requests_cache

from analytics import AnalyticsType
from constants import (
    DEX_API_JSON_PATH, DEX_DEFINITION_API_URL_FORMAT, DEX_SEARCH_URL_FORMAT,
    DEX_THUMBNAIL_URL, DEX_SOURCES_URL, DEX_AUTHOR_URL,
    BOT_START_URL_FORMAT,
    WORD_REGEX,
    UNICODE_SUPERSCRIPTS, ELLIPSIS, DEFINITION_AND_FOOTER_SEPARATOR, MESSAGE_TITLE_LENGTH_LIMIT,
    PREVIOUS_PAGE_ICON, PREVIOUS_OVERLAP_PAGE_ICON, NEXT_PAGE_ICON, NEXT_OVERLAP_PAGE_ICON,
    LINKS_TOGGLE_ON_TEXT, LINKS_TOGGLE_OFF_TEXT,
    BUTTON_DATA_QUERY_KEY, BUTTON_DATA_OFFSET_KEY, BUTTON_DATA_LINKS_TOGGLE_KEY,
    BUTTON_DATA_SUBSCRIPTION_STATE_KEY
)
from database import User

logger = logging.getLogger(__name__)


def check_admin(bot, message, analytics, admin_user_id):
    analytics.track(AnalyticsType.COMMAND, message.from_user, message.text)

    if admin_user_id is None or message.from_user.id != admin_user_id:
        bot.send_message(message.chat_id, 'You are not allowed to use this command')

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


def send_no_results_message(bot, chat_id, message_id, query):
    bot.send_message(
        chat_id, get_no_results_message(query),
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_to_message_id=message_id
    )


def get_raw_response(api_url):
    api_request = requests.get(api_url)
    api_final_url = api_request.url

    if not api_final_url.endswith(DEX_API_JSON_PATH):
        api_request = requests.get('{}{}'.format(api_final_url, DEX_API_JSON_PATH))

    return api_request.json()


def create_definition_url(raw_definition, url):
    id = raw_definition['id']
    url_escaped = url.replace(' ', '')

    return '{}/{}'.format(url_escaped, id)


def create_footer(raw_definition, definition_url):
    source_name = raw_definition['sourceName']
    author = raw_definition['userNick']

    author_url = '{}/{}'.format(DEX_AUTHOR_URL, quote(author))

    return (
        '{}\n'
        'sursa: <a href="{}">{}</a> '
        'adăugată de: <a href="{}">{}</a>'
    ).format(
        definition_url, DEX_SOURCES_URL, source_name,
        author_url, author
    )


def get_message_limit(footer):
    message_limit = MAX_MESSAGE_LENGTH

    message_limit -= len(DEFINITION_AND_FOOTER_SEPARATOR)
    message_limit -= len(footer)
    message_limit -= len(ELLIPSIS)

    return message_limit


def get_html(raw_definition):
    html_rep = raw_definition['htmlRep']
    fragments = html.fragments_fromstring(html_rep)
    root = html.Element('root')

    for fragment in fragments:
        root.append(fragment)

    return root


def get_definitions(update, query, links_toggle, analytics, cli_args, bot_name):
    user = get_user(update)

    if cli_args.fragment:
        url = 'debug'

        dex_raw_definitions = [{
            'id': 0,
            'htmlRep': cli_args.fragment,
            'sourceName': None,
            'userNick': None
        }]
    else:
        api_url = DEX_DEFINITION_API_URL_FORMAT.format(query)
        raw_response = get_raw_response(api_url)

        dex_raw_definitions = raw_response['definitions']

        url = api_url[:- len(DEX_API_JSON_PATH)]

    definitions_count = len(dex_raw_definitions)

    # Set the global index of the definitions.
    for index in range(definitions_count):
        dex_raw_definitions[index]['index'] = index

    if cli_args.index is not None:
        if cli_args.index >= definitions_count:
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

        if offset < definitions_count:
            dex_raw_definitions = dex_raw_definitions[offset + 1:]
    elif is_inline_query:
        analytics.track(AnalyticsType.INLINE_QUERY, user, query)

    for dex_raw_definition in dex_raw_definitions:
        dex_definition_index = dex_raw_definition['index']

        definition_url = create_definition_url(
            raw_definition=dex_raw_definition,
            url=url
        )

        footer = create_footer(
            raw_definition=dex_raw_definition,
            definition_url=definition_url
        )

        # Definition

        message_limit = get_message_limit(footer)

        root = get_html(dex_raw_definition)

        dex_definition_html = ''
        dex_definition_title = ''

        for sup in root.findall('sup'):
            sup_text = sup.text_content()
            superscript_text = get_superscript(sup_text)

            if superscript_text:
                sup.text = superscript_text
            else:
                logger.warning('Unsupported superscript "{}" in definition "{}"'.format(sup_text, definition_url))

        if links_toggle:
            etree.strip_tags(root, '*')

            text = root.text

            dex_definition_string = ''

            for match in WORD_REGEX.finditer(text):
                word = match.group('word')
                other = match.group('other')

                if word is not None:
                    word = escape(word)

                    link = A(word)

                    link.set('href', BOT_START_URL_FORMAT.format(bot_name, base64_encode(word)))

                    link_text = html.tostring(link).decode()

                    if len(dex_definition_string) + len(word) > message_limit:
                        dex_definition_html += ELLIPSIS

                        break
                    else:
                        dex_definition_html += link_text

                        dex_definition_string += word

                if other is not None:
                    other = escape(other)

                    dex_definition_html += other

                    dex_definition_string += other

            dex_definition_title = text
        else:
            dex_definition_string = ''

            for element in root.iterchildren():
                etree.strip_tags(element, '*')

                if element.tag not in ['b', 'i']:
                    element.tag = 'i'

                # etree.strip_attributes(element, '*') should work too.
                element.attrib.clear()

                text = element.text_content() + (element.tail or '')

                string = html.tostring(element).decode()

                dex_definition_title += text

                if len(dex_definition_string) + len(text) > message_limit:
                    dex_definition_html += ELLIPSIS

                    break
                else:
                    dex_definition_html += string

                    dex_definition_string += text

        if cli_args.debug:
            dex_definition_title = '{}: {}'.format(dex_definition_index, dex_definition_title)

        dex_definition_title = dex_definition_title[:MESSAGE_TITLE_LENGTH_LIMIT]

        if len(dex_definition_title) >= MESSAGE_TITLE_LENGTH_LIMIT:
            dex_definition_title = dex_definition_title[:- len(ELLIPSIS)]
            dex_definition_title += ELLIPSIS

        dex_definition_html += '{}{}'.format(DEFINITION_AND_FOOTER_SEPARATOR, footer)

        if cli_args.debug:
            logger.info('Result: {}: {}'.format(dex_definition_index, dex_definition_html))

        inline_keyboard_buttons = get_definition_inline_keyboard_buttons(query, definitions_count, dex_definition_index, links_toggle)

        reply_markup = InlineKeyboardMarkup(inline_keyboard_buttons)

        dex_definition_result = InlineQueryResultArticle(
            id=uuid4(),
            title=dex_definition_title,
            thumb_url=DEX_THUMBNAIL_URL,
            url=definition_url,
            hide_url=True,
            reply_markup=reply_markup,
            input_message_content=InputTextMessageContent(
                message_text=dex_definition_html,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        )

        definitions.append(dex_definition_result)

    return definitions, offset


def clear_definitions_cache(query):
    dex_api_url = DEX_DEFINITION_API_URL_FORMAT.format(query)

    cache = requests_cache.core.get_cache()

    if cache.has_url(dex_api_url):
        cache.delete_url(dex_api_url)

        return 'Cache successfully deleted for "{}"'.format(query)
    else:
        return 'No cache for "{}"'.format(query)


def get_superscript(text):
    superscript = ''

    for letter in text:
        treated_letter = letter.lower().replace('[', '(').replace(']', ')')

        if treated_letter not in UNICODE_SUPERSCRIPTS:
            return None

        superscript += UNICODE_SUPERSCRIPTS[treated_letter]

    return superscript


def get_definition_inline_keyboard_buttons(query, definitions_count, offset, links_toggle):
    buttons = []

    paging_buttons = []
    links_toggle_buttons = []

    if definitions_count > 1:
        is_first_page = offset == 0
        is_last_page = offset == definitions_count - 1

        previous_offset = offset - 1
        next_offset = offset + 1

        previous_text = PREVIOUS_OVERLAP_PAGE_ICON if is_first_page else PREVIOUS_PAGE_ICON
        current_text = '{} / {}'.format(offset + 1, definitions_count)
        next_text = NEXT_OVERLAP_PAGE_ICON if is_last_page else NEXT_PAGE_ICON

        if is_first_page:
            previous_offset = definitions_count - 1

        previous_data = {
            BUTTON_DATA_QUERY_KEY: query,
            BUTTON_DATA_OFFSET_KEY: previous_offset,
            BUTTON_DATA_LINKS_TOGGLE_KEY: links_toggle
        }

        if offset == 0:
            first_data = None
        else:
            first_data = {
                BUTTON_DATA_QUERY_KEY: query,
                BUTTON_DATA_OFFSET_KEY: 0,
                BUTTON_DATA_LINKS_TOGGLE_KEY: links_toggle
            }

        if is_last_page:
            next_offset = 0

        next_data = {
            BUTTON_DATA_QUERY_KEY: query,
            BUTTON_DATA_OFFSET_KEY: next_offset,
            BUTTON_DATA_LINKS_TOGGLE_KEY: links_toggle
        }

        previous_button = InlineKeyboardButton(previous_text, callback_data=json.dumps(previous_data))
        current_button = InlineKeyboardButton(current_text, callback_data=json.dumps(first_data))
        next_button = InlineKeyboardButton(next_text, callback_data=json.dumps(next_data))

        paging_buttons.append(previous_button)
        paging_buttons.append(current_button)
        paging_buttons.append(next_button)

    links_toggle_data = {
        BUTTON_DATA_QUERY_KEY: query,
        BUTTON_DATA_OFFSET_KEY: offset,
        BUTTON_DATA_LINKS_TOGGLE_KEY: not links_toggle
    }

    links_toggle_text = LINKS_TOGGLE_ON_TEXT if links_toggle else LINKS_TOGGLE_OFF_TEXT

    links_toggle_button = InlineKeyboardButton(links_toggle_text, callback_data=json.dumps(links_toggle_data))

    links_toggle_buttons.append(links_toggle_button)

    if len(paging_buttons) > 0:
        buttons.append(paging_buttons)

    buttons.append(links_toggle_buttons)

    return buttons


def get_subscription_onboarding_inline_keyboard_buttons():
    no_data = {
        BUTTON_DATA_SUBSCRIPTION_STATE_KEY: User.Subscription.denied.value
    }

    no_button = InlineKeyboardButton(
        text='Nu',
        callback_data=json.dumps(no_data)
    )

    yes_data = {
        BUTTON_DATA_SUBSCRIPTION_STATE_KEY: User.Subscription.accepted.value
    }

    yes_button = InlineKeyboardButton(
        text='Da',
        callback_data=json.dumps(yes_data)
    )

    return [[no_button, yes_button]]


def get_subscription_cancel_inline_keyboard_button():
    data = {
        BUTTON_DATA_SUBSCRIPTION_STATE_KEY: User.Subscription.revoked.value
    }

    button = InlineKeyboardButton(
        text='Oprește',
        callback_data=json.dumps(data)
    )

    return [[button]]


def base64_encode(string):
    """
    Removes any `=` used as padding from the encoded string.
    Copied from https://gist.github.com/cameronmaske/f520903ade824e4c30ab.
    """

    encoded = base64.urlsafe_b64encode(string.encode())

    return encoded.decode().rstrip('=')


def base64_decode(string):
    """
    Adds back in the required padding before decoding.
    Copied from https://gist.github.com/cameronmaske/f520903ade824e4c30ab.
    """

    padding = 4 - (len(string) % 4)
    string = string + ('=' * padding)

    return base64.urlsafe_b64decode(string).decode('utf-8')
