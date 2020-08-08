# -*- coding: utf-8 -*-

import dataclasses
import typing

import telegram


@dataclasses.dataclass
class CompleteDefinition:
    title: str
    html: str
    url: str

    inline_keyboard_buttons: typing.List[typing.List[telegram.InlineKeyboardButton]]

    image_url: typing.Optional[str] = None
