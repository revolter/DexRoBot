# -*- coding: utf-8 -*-

from html import escape
from urllib.parse import quote
from uuid import uuid4

import base64
import collections
import json
import logging
import time

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
    DEX_API_JSON_PATH, DEX_DEFINITION_API_URL_FORMAT, DEX_WORD_OF_THE_DAY_URL, DEX_SEARCH_URL_FORMAT,
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
ParsedDefinition = collections.namedtuple(
    typename='ParsedDefinition',
    field_names='index title html url'
)


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


def replace_superscripts(root, definition_url):
    for sup in root.findall('sup'):
        sup_text = sup.text_content()
        superscript_text = get_superscript(sup_text)

        if superscript_text:
            sup.text = superscript_text
        else:
            logger.warning('Unsupported superscript "{}" in definition "{}"'.format(sup_text, definition_url))


def get_word_link(word, bot_name):
    link = A(word)
    link.set('href', BOT_START_URL_FORMAT.format(bot_name, base64_encode(word)))

    return html.tostring(link).decode()


def clean_html_element(element):
    etree.strip_tags(element, '*')

    if element.tag not in ['b', 'i']:
        element.tag = 'i'

    # etree.strip_attributes(element, '*') should work too.
    # See https://bugs.launchpad.net/lxml/+bug/1846267.
    element.attrib.clear()


def get_parsed_definition(raw_definition, url, links_toggle, cli_args, bot_name, prefix='', suffix=''):
    definition_index = raw_definition.get('index', 'N/A')

    definition_url = create_definition_url(
        raw_definition=raw_definition,
        url=url
    )
    footer = create_footer(
        raw_definition=raw_definition,
        definition_url=definition_url
    )

    message_limit = get_message_limit(footer)
    root = get_html(raw_definition)

    definition_title: str
    definition_html_text = prefix
    elements: collections.Iterator

    replace_superscripts(
        root=root,
        definition_url=definition_url
    )

    if links_toggle:
        etree.strip_tags(root, '*')

        text = root.text

        definition_title = text
        elements = WORD_REGEX.finditer(text)
    else:
        definition_title = ''
        elements = root.iterchildren()

    definition_text_content = ''

    for element in elements:
        text_content = None
        extra_text_content = None
        html_text = None

        if links_toggle:
            word = element.group('word')
            other = element.group('other')

            if word is not None:
                text_content = escape(word)
                html_text = get_word_link(
                    word=text_content,
                    bot_name=bot_name
                )

            if other is not None:
                extra_text_content = escape(other)
        else:
            clean_html_element(element)

            text_content = element.text_content() + (element.tail or '')
            html_text = html.tostring(element).decode()

            definition_title += text_content

        if text_content:
            if len(definition_text_content) + len(text_content) + len(suffix) > message_limit:
                definition_html_text += ELLIPSIS

                break
            else:
                definition_html_text += html_text
                definition_text_content += text_content

        if extra_text_content:
            definition_html_text += extra_text_content
            definition_text_content += extra_text_content

    if cli_args.debug:
        definition_title = '{}: {}'.format(definition_index, definition_title)

    definition_title = definition_title[:MESSAGE_TITLE_LENGTH_LIMIT]

    if len(definition_title) >= MESSAGE_TITLE_LENGTH_LIMIT:
        definition_title = definition_title[:- len(ELLIPSIS)]
        definition_title += ELLIPSIS

    definition_html_text += '{}{}'.format(DEFINITION_AND_FOOTER_SEPARATOR, footer)
    definition_html_text += suffix

    if cli_args.debug:
        logger.info('Result: {}: {}'.format(definition_index, definition_html_text))

    return ParsedDefinition(
        index=definition_index,
        title=definition_title,
        html=definition_html_text,
        url=definition_url
    )


def get_inline_query_definition_result(parsed_definition, inline_keyboard_buttons):
    reply_markup = InlineKeyboardMarkup(inline_keyboard_buttons)

    return InlineQueryResultArticle(
        id=uuid4(),
        title=parsed_definition.title,
        thumb_url=DEX_THUMBNAIL_URL,
        url=parsed_definition.url,
        hide_url=True,
        reply_markup=reply_markup,
        input_message_content=InputTextMessageContent(
            message_text=parsed_definition.html,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    )


def get_query_definitions(update, query, links_toggle, analytics, cli_args, bot_name):
    user = get_user(update)

    if cli_args.fragment:
        url = 'debug'

        raw_definitions = [{
            'id': 0,
            'htmlRep': cli_args.fragment,
            'sourceName': None,
            'userNick': None
        }]
    else:
        api_url = DEX_DEFINITION_API_URL_FORMAT.format(query)
        raw_response = get_raw_response(api_url)

        raw_definitions = raw_response['definitions']

        url = api_url[:- len(DEX_API_JSON_PATH)]

    definitions_count = len(raw_definitions)

    # Set the global index of the definitions.
    for index in range(definitions_count):
        raw_definitions[index]['index'] = index

    if cli_args.index is not None:
        if cli_args.index >= definitions_count:
            logger.warning('Index out of bounds')

            return

        raw_definitions = [raw_definitions[cli_args.index]]

    definitions = []

    offset_string = None
    offset = 0

    is_inline_query = update.inline_query is not None

    if is_inline_query:
        offset_string = update.inline_query.offset

    if offset_string:
        offset = int(offset_string)

        if offset < definitions_count:
            raw_definitions = raw_definitions[offset + 1:]
    elif is_inline_query:
        analytics.track(AnalyticsType.INLINE_QUERY, user, query)

    for raw_definition in raw_definitions:
        parsed_definition = get_parsed_definition(
            raw_definition=raw_definition,
            url=url,
            links_toggle=links_toggle,
            cli_args=cli_args,
            bot_name=bot_name
        )
        inline_keyboard_buttons = get_definition_inline_keyboard_buttons(query, definitions_count, parsed_definition.index, links_toggle)
        definition_result = get_inline_query_definition_result(
            parsed_definition=parsed_definition,
            inline_keyboard_buttons=inline_keyboard_buttons
        )

        definitions.append(definition_result)

    return definitions, offset


def get_word_of_the_day_definition(links_toggle, cli_args, bot_name):
    timestamp = int(time.time())
    api_url = DEX_WORD_OF_THE_DAY_URL.format(timestamp)
    raw_response = get_raw_response(api_url)

    day = raw_response['day']
    month = raw_response['month']

    raw_requested = raw_response['requested']
    raw_record = raw_requested['record']

    year = raw_record['year']
    reason = raw_record['reason']
    image_url = raw_record['image']

    raw_definition = raw_record['definition']

    url = api_url[:- len(DEX_API_JSON_PATH)]
    prefix = '<b>Cuvântul zilei {}.{}.{}:</b>\n\n'.format(day, month, year)
    suffix = '\n\n<b>Cheia alegerii:</b> {}'.format(reason)

    parsed_definition = get_parsed_definition(
        raw_definition=raw_definition,
        url=url,
        links_toggle=links_toggle,
        cli_args=cli_args,
        bot_name=bot_name,
        prefix=prefix,
        suffix=suffix
    )
    inline_keyboard_buttons = get_subscription_cancel_inline_keyboard_button()
    definition_result = get_inline_query_definition_result(
        parsed_definition=parsed_definition,
        inline_keyboard_buttons=inline_keyboard_buttons
    )

    definition_result.url = image_url

    return definition_result


def clear_definitions_cache(query):
    api_url = DEX_DEFINITION_API_URL_FORMAT.format(query)

    cache = requests_cache.core.get_cache()

    if cache.has_url(api_url):
        cache.delete_url(api_url)

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
