#!/usr/bin/env python
# -*- coding: utf-8 -*-

import telegram
from telegram.ext import Updater, CommandHandler
import requests
from bs4 import BeautifulSoup
import random
import logging
import os
import time
import sys
import re

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ['TG_BOT_TOKEN']

MY_GARAGE = 'my_garage'
DZEN_LINK_PATTERN = 'https://zen.yandex.ru/%s'
DZEN_LINK = DZEN_LINK_PATTERN % MY_GARAGE

ITEM_CLASS = 'card-image-view__clickable'

LINKS = {}
DEFAULT_LINKS = []
LINKS_UPDATE_TS = None
LINKS_UPDATE_INTERVAL = 60 * 30

MORE_LINK_REGEXP = r'\"more\"\:\"http.*?\"'
PAGES_TO_FETCH = 3

CHANNEL_OVERRIDES = {}


def error(update, context):
    '''Log Errors caused by Updates.'''
    logging.warning('Update %s caused error %s', update, context.error)


def get_channel(update, context):
    chat_id = update.message.chat_id
    channel = CHANNEL_OVERRIDES.get(chat_id, DZEN_LINK)
    update.message.reply_text(channel)


def random_link(update, context):
    global DEFAULT_LINKS, LINKS, LINKS_UPDATE_TS
    current_ts = int(time.time())

    chat_id = update.message.chat_id
    channel_overridden = chat_id in CHANNEL_OVERRIDES

    if current_ts - LINKS_UPDATE_TS > LINKS_UPDATE_INTERVAL:
        logging.info('Updating links')
        if channel_overridden:
            chat_channel_link = CHANNEL_OVERRIDES['chat_id']
        else:
            chat_channel_link = DZEN_LINK

        new_links = fetch_links_with_pagination(chat_channel_link)
        if channel_overridden:
            LINKS[chat_id] = new_links
        else:
            DEFAULT_LINKS = new_links

        LINKS_UPDATE_TS = current_ts

    if channel_overridden:
        chat_articles = LINKS[chat_id]
    else:
        chat_articles = DEFAULT_LINKS

    if len(chat_articles) > 0:
        text = random.choice(tuple(chat_articles))
    else:
        text = 'No articles'
    update.message.reply_text(text)


def set_channel(update, context):
    chat_id = update.message.chat_id
    try:
        new_channel_name = context.args[0]
        new_channel_link = DZEN_LINK_PATTERN % new_channel_name
        test_r = requests.get(new_channel_link)
        if test_r.status_code != 200:
            update.message.reply_text('No channel %s' % new_channel_name)
        else:
            CHANNEL_OVERRIDES[chat_id] = new_channel_link
            LINKS[chat_id] = fetch_links_with_pagination(new_channel_link)
            update.message.reply_text('New channel is %s' % new_channel_name)
    except Exception:
        logging.error('Error', exc_info=True)
        update.message.reply_text('Usage: /set_channel <channel name>')


def fetch_links_with_pagination(channel_link):
    """
    The article itself returns HTML doc, but pagination is implemented by js,
     which calls rest api, the link is passed as "more"
    :return:
    """
    r = requests.get(channel_link)
    html_doc = r.text
    soup = BeautifulSoup(html_doc, 'html.parser')
    article_link_objects = soup.findAll('a', {'class': ITEM_CLASS}, href=True)
    article_links = map(lambda a: a['href'], article_link_objects)

    # pretty ugly but works
    more_link_substring = re.search(MORE_LINK_REGEXP, html_doc).group()
    more_link = more_link_substring[8:-1]

    links = fetch_more_links(more_link, PAGES_TO_FETCH, article_links)
    unique_links = set(links)

    logging.info('Loaded %s links from %s' % (len(unique_links), DZEN_LINK))

    return unique_links


def fetch_more_links(more_link, steps_left, links):
    if steps_left == 0:
        return links
    else:
        more_response = requests.get(more_link)
        more_json = more_response.json()
        items = more_json.get('items', [])
        more_links = map(lambda i: i['link'], items)

        if 'more' in more_json and 'link' in more_json['more']:
            next_more_link = more_json['more']['link']
            return fetch_more_links(next_more_link, steps_left - 1, links + more_links)
        else:
            # no more links
            return links + more_links


def main():
    logging.info('Starting dzen bot for %s' % DZEN_LINK)
    global DEFAULT_LINKS, LINKS_UPDATE_TS
    DEFAULT_LINKS = fetch_links_with_pagination(DZEN_LINK)
    LINKS_UPDATE_TS = int(time.time())

    updater = Updater(TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('link', random_link))
    dp.add_handler(CommandHandler('get_channel', get_channel))
    dp.add_handler(CommandHandler("set_channel", set_channel,
                                  pass_args=True,
                                  pass_chat_data=True))
    dp.add_error_handler(error)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
