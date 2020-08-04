# -*- coding: utf-8 -*-

import dataclasses


@dataclasses.dataclass
class ParsedDefinition:
    index: int
    title: str
    html: str
    url: str
