#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from analytics import AnalyticsType


def check_admin(bot, message, analytics, admin_user_id):
    analytics.track(AnalyticsType.COMMAND, message.from_user, message.text)

    if not admin_user_id or message.from_user.id != admin_user_id:
        bot.sendMessage(message.chat_id, 'You are not allowed to restart the bot')

        return False

    return True
