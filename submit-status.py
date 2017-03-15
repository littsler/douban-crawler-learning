#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import json
from requests.sessions import Session
from music_collect_crawl import login, FORMAT

douban_url = "https://www.douban.com"
get_url_info_url = "https://www.douban.com/j/misc/get_url_info"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)
log = logging.getLogger()


def get_url_info(url, session):
    """
    Douban extracts informations of a given URL. This function sends a POST with the URL to douban and extracts the information
    :param url: the given URL
    :param session: a pre-logged in HTTP session
    :return: structured data returned by Douban
    """
    log.debug("get info of url...")
    if not isinstance(session, Session):
        raise Exception("Session invalid!")
    ck = session.cookies.get('ck')
    r = session.post(get_url_info_url, data={'url': url, 'ck': ck, 'need_images': '1'})
    if r.status_code != 200:
        r.raise_for_status()
    return json.loads(r.text)


def submit_status(session, url=None, comment=None):
    """
    Submit a status to douban.
    :param session: a pre-logged in HTTP session
    :param url: a URL to be recommended
    :param comment: text to be posted
    :return: None
    """
    log.debug("submit a status...")
    if not isinstance(session, Session):
        raise Exception("Session invalid!")
    if url is None and comment is None:
        raise Exception("Nothing to post!")
    data = {'ck': session.cookies['ck']}
    if url is not None:
        info = get_url_info(url, session)
        data['title'] = info['title']
        data['url'] = url
        data['image'] = info['images'][0]
        data['image_num'] = len(info['images'])
        data['abstract'] = info['abstract']
        data['t'] = 'I'
    if comment is not None:
        data['comment'] = comment
    r = session.post(douban_url, data=data)
    if r.status_code != 200:
        r.raise_for_status()


if __name__ == '__main__':
    log.debug("start...")
    s = Session()
    login(session=s)
    submit_status(s, url="some_url_to_be_recommended", comment='Some comment to be posted')
    log.debug("finished.")
