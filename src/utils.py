# -*- coding: utf-8 -*-

import argparse
import base64
import collections
import html
import json
import logging
import time
import typing
import urllib.parse
import uuid

import lxml.etree
import lxml.html.builder
import regex
import requests
import requests_cache
import telegram
import telegram.ext

import analytics
import complete_definition
import constants
import database
import parsed_definition

logger = logging.getLogger(__name__)


def get_raw_response(api_url: str) -> typing.Dict[str, typing.Any]:
    api_request = requests.get(api_url)
    api_final_url = api_request.url

    if not api_final_url.endswith(constants.DEX_API_JSON_PATH):
        api_request = requests.get(f'{api_final_url}{constants.DEX_API_JSON_PATH}')

    return api_request.json()


def create_definition_url(raw_definition: typing.Dict[str, typing.Any], url: str) -> str:
    id = raw_definition['id']
    url_escaped = url.replace(' ', '')

    return f'{url_escaped}/{id}'


def create_footer(raw_definition: typing.Dict[str, typing.Any], definition_url: str) -> str:
    source_name = raw_definition['sourceName']
    author = raw_definition['userNick']

    author_url = f'{constants.DEX_AUTHOR_URL}/{urllib.parse.quote(author)}'

    return (
        f'{definition_url}\n'
        f'sursa: <a href="{constants.DEX_SOURCES_URL}">{source_name}</a> '
        f'adăugată de: <a href="{author_url}">{author}</a>'
    )


def get_message_limit(footer: str) -> int:
    message_limit = telegram.constants.MAX_MESSAGE_LENGTH

    message_limit -= len(constants.DEFINITION_AND_FOOTER_SEPARATOR)
    message_limit -= len(footer)
    message_limit -= len(constants.ELLIPSIS)

    return message_limit


def get_html(raw_definition: typing.Dict[str, typing.Any]) -> lxml.html.HtmlElement:
    html_rep = raw_definition['htmlRep']
    fragments = lxml.html.fragments_fromstring(html_rep)
    root = lxml.html.Element('root')

    for fragment in fragments:
        root.append(fragment)

    return root


def replace_superscripts(root: lxml.html.HtmlElement, definition_url: str) -> None:
    for sup in root.findall('sup'):
        sup_text = sup.text_content()
        superscript_text = get_superscript(sup_text)

        if superscript_text:
            sup.text = superscript_text
        else:
            logger.warning(f'Unsupported superscript "{sup_text}" in definition "{definition_url}"')


def get_word_link(word: str, bot_name: str) -> str:
    link = lxml.html.builder.A(word)
    link.set('href', constants.BOT_START_URL_FORMAT.format(bot_name, base64_encode(word)))

    return lxml.html.tostring(
        doc=link,
        encoding='unicode'
    )


def clean_html_element(element: lxml.html.HtmlElement) -> None:
    lxml.etree.strip_tags(element, '*')

    if element.tag not in ['b', 'i']:
        element.tag = 'i'

    # etree.strip_attributes(element, '*') should work too.
    # See https://bugs.launchpad.net/lxml/+bug/1846267.
    element.attrib.clear()


def get_parsed_definition(raw_definition: typing.Dict[str, typing.Any], url: str, links_toggle: bool, cli_args: argparse.Namespace, bot_name: str, prefix='', suffix='') -> parsed_definition.ParsedDefinition:
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
        lxml.etree.strip_tags(root, '*')

        text = root.text

        definition_title = text
        elements = constants.WORD_REGEX.finditer(text)
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
                text_content = html.escape(word)
                html_text = get_word_link(
                    word=text_content,
                    bot_name=bot_name
                )

            if other is not None:
                extra_text_content = html.escape(other)
        else:
            clean_html_element(element)

            text_content = element.text_content() + (element.tail or '')
            html_text = lxml.html.tostring(element).decode()

            definition_title += text_content

        if text_content:
            if len(definition_text_content) + len(text_content) + len(suffix) > message_limit:
                definition_html_text += constants.ELLIPSIS

                break
            else:
                definition_html_text += html_text
                definition_text_content += text_content

        if extra_text_content:
            definition_html_text += extra_text_content
            definition_text_content += extra_text_content

    if cli_args.debug:
        definition_title = f'{definition_index}: {definition_title}'

    definition_title = definition_title[:constants.MESSAGE_TITLE_LENGTH_LIMIT]

    if len(definition_title) >= constants.MESSAGE_TITLE_LENGTH_LIMIT:
        definition_title = definition_title[:- len(constants.ELLIPSIS)]
        definition_title += constants.ELLIPSIS

    definition_html_text += f'{constants.DEFINITION_AND_FOOTER_SEPARATOR}{footer}'
    definition_html_text += suffix

    if cli_args.debug:
        logger.info(f'Result: {definition_index}: {definition_html_text}')

    return parsed_definition.ParsedDefinition(
        index=definition_index,
        title=definition_title,
        html=definition_html_text,
        url=definition_url
    )


def get_complete_definition(definition: parsed_definition.ParsedDefinition, inline_keyboard_buttons: typing.List[typing.List[telegram.InlineKeyboardButton]]) -> complete_definition.CompleteDefinition:
    return complete_definition.CompleteDefinition(
        title=definition.title,
        html=definition.html,
        url=definition.url,

        inline_keyboard_buttons=inline_keyboard_buttons
    )


def get_inline_query_definition_result(definition: complete_definition.CompleteDefinition) -> telegram.InlineQueryResultArticle:
    reply_markup = telegram.InlineKeyboardMarkup(definition.inline_keyboard_buttons)

    return telegram.InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title=definition.title,
        thumb_url=constants.DEX_THUMBNAIL_URL,
        url=definition.url,
        hide_url=True,
        reply_markup=reply_markup,
        input_message_content=telegram.InputTextMessageContent(
            message_text=definition.html,
            parse_mode=telegram.ParseMode.HTML,
            disable_web_page_preview=True
        )
    )


def get_query_definitions(update: telegram.Update, context: telegram.ext.CallbackContext, query: typing.Optional[str], links_toggle: bool, analytics_handler: analytics.AnalyticsHandler, cli_args: argparse.Namespace, bot_name: str) -> typing.Tuple[typing.List[complete_definition.CompleteDefinition], int]:
    user = update.effective_user

    if cli_args.fragment:
        url = 'debug'

        raw_definitions = [{
            'id': 0,
            'htmlRep': cli_args.fragment,
            'sourceName': None,
            'userNick': None
        }]
    else:
        api_url = constants.DEX_DEFINITION_API_URL_FORMAT.format(query)
        raw_response = get_raw_response(api_url)

        raw_definitions = raw_response['definitions']

        url = api_url[:- len(constants.DEX_API_JSON_PATH)]

    definitions_count = len(raw_definitions)

    # Set the global index of the definitions.
    for index in range(definitions_count):
        raw_definitions[index]['index'] = index

    definitions: typing.List[complete_definition.CompleteDefinition] = []

    if cli_args.index is not None:
        if cli_args.index >= definitions_count:
            logger.warning('Index out of bounds')

            return definitions, 0

        raw_definitions = [raw_definitions[cli_args.index]]

    offset_string = None
    offset = 0

    inline_query = update.inline_query
    is_inline_query = False

    if inline_query is not None:
        offset_string = inline_query.offset
        is_inline_query = True

    if offset_string:
        offset = int(offset_string)

        if offset < definitions_count:
            raw_definitions = raw_definitions[offset + 1:]
    elif is_inline_query and user is not None:
        analytics_handler.track(context, analytics.AnalyticsType.INLINE_QUERY, user, query)

    for raw_definition in raw_definitions:
        parsed_definition_data = get_parsed_definition(
            raw_definition=raw_definition,
            url=url,
            links_toggle=links_toggle,
            cli_args=cli_args,
            bot_name=bot_name
        )
        inline_keyboard_buttons = get_definition_inline_keyboard_buttons(query, definitions_count, parsed_definition_data.index, links_toggle)
        complete_definition_data = get_complete_definition(
            definition=parsed_definition_data,
            inline_keyboard_buttons=inline_keyboard_buttons
        )

        definitions.append(complete_definition_data)

    return definitions, offset


def get_word_of_the_day_definition(links_toggle: bool, cli_args: argparse.Namespace, bot_name: str, with_stop=False) -> complete_definition.CompleteDefinition:
    timestamp = int(time.time())
    api_url = constants.DEX_WORD_OF_THE_DAY_URL.format(timestamp)
    raw_response = get_raw_response(api_url)

    day = raw_response['day']
    month = raw_response['month']

    raw_requested = raw_response['requested']
    raw_record = raw_requested['record']

    year = raw_record['year']
    reason = raw_record['reason']
    image_url = raw_record['image']
    image_author = raw_record['imageAuthor']

    raw_definition = raw_record['definition']

    url = regex.sub(
        pattern=constants.DEX_API_SUFFIX_REGEX,
        repl='',
        string=api_url
    )
    prefix = f'<b>Cuvântul zilei {day}.{month}.{year}:</b>\n\n'
    suffix = f'\n\n<b>Cheia alegerii:</b> {reason}'

    parsed_definition_data = get_parsed_definition(
        raw_definition=raw_definition,
        url=url,
        links_toggle=links_toggle,
        cli_args=cli_args,
        bot_name=bot_name,
        prefix=prefix,
        suffix=suffix
    )
    inline_keyboard_buttons = get_subscription_notification_inline_keyboard_buttons(
        links_toggle=links_toggle,
        with_stop=with_stop
    )
    completed_definition_data = get_complete_definition(
        definition=parsed_definition_data,
        inline_keyboard_buttons=inline_keyboard_buttons
    )
    completed_definition_data.image_url = image_url
    completed_definition_data.image_author = image_author

    return completed_definition_data


def clear_definitions_cache(query: str) -> str:
    api_url = constants.DEX_DEFINITION_API_URL_FORMAT.format(query)

    cache = requests_cache.core.get_cache()

    if cache.has_url(api_url):
        cache.delete_url(api_url)

        return f'Cache successfully deleted for "{query}"'
    else:
        return f'No cache for "{query}"'


def get_superscript(text: str) -> typing.Optional[str]:
    superscript = ''

    for letter in text:
        treated_letter = letter.lower().replace('[', '(').replace(']', ')')

        if treated_letter not in constants.UNICODE_SUPERSCRIPTS:
            return None

        superscript += constants.UNICODE_SUPERSCRIPTS[treated_letter]

    return superscript


def get_definition_inline_keyboard_buttons(query: typing.Optional[str], definitions_count: int, offset: int, links_toggle: bool) -> typing.List[typing.List[telegram.InlineKeyboardButton]]:
    buttons: typing.List[typing.List[telegram.InlineKeyboardButton]] = []

    paging_buttons: typing.List[telegram.InlineKeyboardButton] = []
    links_toggle_buttons: typing.List[telegram.InlineKeyboardButton] = []

    if definitions_count > 1:
        is_first_page = offset == 0
        is_last_page = offset == definitions_count - 1

        previous_offset = offset - 1
        next_offset = offset + 1

        previous_text = constants.PREVIOUS_OVERLAP_PAGE_ICON if is_first_page else constants.PREVIOUS_PAGE_ICON
        current_text = f'{offset + 1} / {definitions_count}'
        next_text = constants.NEXT_OVERLAP_PAGE_ICON if is_last_page else constants.NEXT_PAGE_ICON

        if is_first_page:
            previous_offset = definitions_count - 1

        previous_data = {
            constants.BUTTON_DATA_QUERY_KEY: query,
            constants.BUTTON_DATA_OFFSET_KEY: previous_offset,
            constants.BUTTON_DATA_LINKS_TOGGLE_KEY: links_toggle
        }

        if offset == 0:
            first_data = None
        else:
            first_data = {
                constants.BUTTON_DATA_QUERY_KEY: query,
                constants.BUTTON_DATA_OFFSET_KEY: 0,
                constants.BUTTON_DATA_LINKS_TOGGLE_KEY: links_toggle
            }

        if is_last_page:
            next_offset = 0

        next_data = {
            constants.BUTTON_DATA_QUERY_KEY: query,
            constants.BUTTON_DATA_OFFSET_KEY: next_offset,
            constants.BUTTON_DATA_LINKS_TOGGLE_KEY: links_toggle
        }

        previous_button = telegram.InlineKeyboardButton(previous_text, callback_data=json.dumps(previous_data))
        current_button = telegram.InlineKeyboardButton(current_text, callback_data=json.dumps(first_data))
        next_button = telegram.InlineKeyboardButton(next_text, callback_data=json.dumps(next_data))

        paging_buttons.append(previous_button)
        paging_buttons.append(current_button)
        paging_buttons.append(next_button)

    links_toggle_data = {
        constants.BUTTON_DATA_QUERY_KEY: query,
        constants.BUTTON_DATA_OFFSET_KEY: offset,
        constants.BUTTON_DATA_LINKS_TOGGLE_KEY: not links_toggle
    }

    links_toggle_text = constants.LINKS_TOGGLE_ON_TEXT if links_toggle else constants.LINKS_TOGGLE_OFF_TEXT

    links_toggle_button = telegram.InlineKeyboardButton(links_toggle_text, callback_data=json.dumps(links_toggle_data))

    links_toggle_buttons.append(links_toggle_button)

    if len(paging_buttons) > 0:
        buttons.append(paging_buttons)

    buttons.append(links_toggle_buttons)

    return buttons


def send_subscription_onboarding_message_if_needed(bot: telegram.Bot, user: telegram.User, chat_id: int) -> None:
    db_user = database.User.get_or_none(database.User.telegram_id == user.id)

    if db_user is None:
        return

    if db_user.subscription != database.User.Subscription.undetermined.value:
        return

    reply_markup = telegram.InlineKeyboardMarkup(get_subscription_onboarding_inline_keyboard_buttons())

    bot.send_message(
        chat_id=chat_id,
        text='Vrei să primești cuvântul zilei?',
        reply_markup=reply_markup
    )


def get_subscription_onboarding_inline_keyboard_buttons() -> typing.List[typing.List[telegram.InlineKeyboardButton]]:
    no_data = {
        constants.BUTTON_DATA_IS_SUBSCRIPTION_ONBOARDING_KEY: True,
        constants.BUTTON_DATA_SUBSCRIPTION_STATE_KEY: database.User.Subscription.denied.value
    }

    no_button = telegram.InlineKeyboardButton(
        text='Nu',
        callback_data=json.dumps(no_data)
    )

    yes_data = {
        constants.BUTTON_DATA_IS_SUBSCRIPTION_ONBOARDING_KEY: True,
        constants.BUTTON_DATA_SUBSCRIPTION_STATE_KEY: database.User.Subscription.accepted.value
    }

    yes_button = telegram.InlineKeyboardButton(
        text='Da',
        callback_data=json.dumps(yes_data)
    )

    return [[no_button, yes_button]]


def get_subscription_notification_inline_keyboard_buttons(links_toggle=False, with_stop=True) -> typing.List[typing.List[telegram.InlineKeyboardButton]]:
    links_toggle_data = {
        constants.BUTTON_DATA_LINKS_TOGGLE_KEY: not links_toggle,
        constants.BUTTON_DATA_SUBSCRIPTION_STATE_KEY: None
    }

    links_toggle_text = constants.LINKS_TOGGLE_ON_TEXT if links_toggle else constants.LINKS_TOGGLE_OFF_TEXT

    links_toggle_button = telegram.InlineKeyboardButton(
        text=links_toggle_text,
        callback_data=json.dumps(links_toggle_data)
    )

    subscription_data: typing.Dict[str, typing.Any]
    subscription_text: str

    if with_stop:
        subscription_data = {
            constants.BUTTON_DATA_LINKS_TOGGLE_KEY: links_toggle,
            constants.BUTTON_DATA_SUBSCRIPTION_STATE_KEY: database.User.Subscription.revoked.value
        }

        subscription_text = 'Oprește'
    else:
        subscription_data = {
            constants.BUTTON_DATA_LINKS_TOGGLE_KEY: links_toggle,
            constants.BUTTON_DATA_SUBSCRIPTION_STATE_KEY: database.User.Subscription.accepted.value
        }

        subscription_text = 'Repornește'

    subscription_button = telegram.InlineKeyboardButton(
        text=subscription_text,
        callback_data=json.dumps(subscription_data)
    )

    return [[links_toggle_button, subscription_button]]


def base64_encode(string: str) -> str:
    """
    Removes any `=` used as padding from the encoded string.
    Copied from https://gist.github.com/cameronmaske/f520903ade824e4c30ab.
    """

    encoded = base64.urlsafe_b64encode(string.encode())

    return encoded.decode().rstrip('=')


def base64_decode(string: str) -> str:
    """
    Adds back in the required padding before decoding.
    Copied from https://gist.github.com/cameronmaske/f520903ade824e4c30ab.
    """

    padding = 4 - (len(string) % 4)
    string += '=' * padding

    return base64.urlsafe_b64decode(string).decode('utf-8')
