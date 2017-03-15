#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import random
import re
import time
from multiprocessing import Pool, Queue, Manager
from queue import Empty

from requests import Session

ua_list = [r'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0']
referer = "https://www.douban.com/accounts/login"
contact_url_template = "https://www.douban.com/people/{}/contacts"
music_url_template = "https://music.douban.com/people/{}/collect?start={" \
                     "}&sort=time&filter=all&mode=list&tags_sort=count"
pattern_contact = r'<dd><a href="https://www.douban.com/people/(?P<id>[^/>]*?)/">(?P<username>[^<]*?)</a></dd>'
pattern_cd = r'<a href="https://music.douban.com/subject/(?P<item>[^/]*?)/">(?P<title>[^<]*?)</a>'
pattern_intro = r'<span class="intro">(?P<intro>[^<]*?)</span>'
pattern_captcha_url = r'<img id="captcha_image" src="(?P<captcha_url>[^"]*?)" alt="captcha" class="captcha_image"/>'
pattern_captcha_id = r'<input type="hidden" name="captcha-id" value="(?P<captcha_id>[^"]*?)"/>'
pattern_redir = r'<input name="redir" type="hidden" value="(?P<redir>[^"]*?)"/>'
pattern_source = r'<input name="source" type="hidden" value="(?P<source>[^"]*?)"/>'
MAX_WORKERS = 1
MAX_DEPTH = 1
COUNT_PER_PAGE = 30
session_queue = Queue()
id_queue = Queue()
login_url = "https://www.douban.com/accounts/login"
form_email = 'some_email@address'
form_password = 'some_password'
users = Manager().list()
result_file_path = 'music-collection.json'
FORMAT = '%(asctime)-15s %(threadName)s %(levelname)s %(message)s'
logging.basicConfig(format=FORMAT, level=logging.DEBUG)
log = logging.getLogger()
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True


def random_sleep(min_val=0.5, max_val=1.5):
    """
    Randomly sleep for a period between min_val and max_val
    :param min_val: minimal value of the sleep period. Default as 0.5s
    :param max_val: maximal value of the sleep period. Default as 1.5s
    :return: None
    """
    time.sleep(random.uniform(min_val, max_val))


def _customized_header():
    """
    Shape a customized request header.
    :return: a dict as a customized request header
    """
    return {'User-Agent': random.choice(ua_list),
            'Referer': referer, 'Host': 'www.douban.com', 'Upgrade-Insecure-Requests': '1'}


def new_session():
    """
    New an HTTP seesion with customized headers.
    :return: an HTTP session
    """
    log.debug("get a new session...")
    session = Session()
    session.headers.update(_customized_header())
    return session


def init_session_queue(size):
    """
    Initialize a queue with established HTTP sessions.
    :param size: initial size of the queue
    :return: a queue with established HTTP sessions.
    """
    for i in range(size):
        session_queue.put(new_session())


def handle_captcha(page):
    """
    Handle captcha manually. A URL link to the captcha image will be given and an input of solution will be waited for.
    :param page: a plain text of the HTTP page with captcha
    :return: a tuple of (captcha-id, captcha-solution)
    """
    log.debug('captcha found. handle captcha...')
    captcha_url = re.findall(pattern_captcha_url, page)[0]
    captcha_id = re.findall(pattern_captcha_id, page)[0]
    if captcha_url is None:
        raise Exception("No captcha found")
    log.info("captcha link is {}. solution:".format(captcha_url))
    solution = input("solution:")
    return captcha_id, solution


def login(email=form_email, password=form_password, url=None, res=None, session=None):
    """
    Log in to Douban.
    :param email: E-mail for login. Default as form_email
    :param password: password for login. Default as form_password
    :param url: the URL of login page. Default as the default URL for login
    :param res: a previous response. If not given, a GET of the url will be performed
    :param session: an HTTP session. if not given, one HTTP session will be retrieved from the session_queue,
                and returned before the function exits
    :return: the response from the login
    """
    log.debug('login...')
    if session is None:
        _session = session_queue.get()
    else:
        _session = session
    if url is None:
        url = login_url
    try:
        if res is None:
            res = _session.get(url)
        data = {}
        if re.search(r"captcha-id", res.text) is not None:
            captcha_id, captcha_solution = handle_captcha(res.text)
            data['captcha-id'] = captcha_id
            data['captcha-solution'] = captcha_solution
        data['form_email'] = email
        data['form_password'] = password
        data['remember'] = 'on'
        data['source'] = re.findall(pattern_source, res.text)[0]
        data['redir'] = re.findall(pattern_redir, res.text)[0]
        res_login = _session.post(url, data=data)
        if res_login.status_code != 200:
            res_login.raise_for_status()
        _session.headers['Referer'] = res_login.url
        return res_login
    finally:
        if session is None:
            session_queue.put(_session)


def fetch_followings(user_id, depth, session=None):
    """
    Fetch the followings of a given user ID and a depth. The followings will be put into the id_queue with a depth equals current depth + 1
    :param user_id: the user ID to be scanned
    :param depth: the current depth
    :param session: an HTTP session. If not given, an HTTP session will be retrieved from session_queue and returned before the function exits
    :return: None
    """
    log.debug('fetch followings of user {}, depth {}'.format(user_id, depth))
    if session is None:
        _session = session_queue.get()
    else:
        _session = session
    try:
        _session.headers['Host'] = 'www.douban.com'
        r = _session.get(contact_url_template.format(user_id))
        if r.status_code != 200:
            r.raise_for_status()
        if r.url.startswith(login_url):
            log.debug("must login")
            r = login(url=r.url, res=r, session=_session)
        contacts = re.findall(pattern_contact, r.text)
        log.debug("{} followings of user {} found.".format(len(contacts), user_id))
        for uid, uname in contacts:
            users.append({'id': uid, 'name': uname})
            id_queue.put({'id': uid, 'depth': depth + 1})
        _session.headers['Referer'] = r.url
    finally:
        if session is None:
            session_queue.put(_session)
    random_sleep()


def proceed_user(user_id, depth, session=None):
    """
    Retrieve the CD collection of the given user ID and depth. If the current depth < MAX_DEPTH, fetch_followings will be called.
    :param user_id: the user ID to be scanned
    :param depth: the current depth
    :param session: an HTTP session. If not given, an HTTP session will be retrieved from the session_queue and returned before the function exits
    :return: None
    """
    log.debug("proceed user {} with depth {}...".format(user_id, depth))
    for i, user in enumerate(users):
        if user['id'] == user_id:
            if 'cds' in user.keys():
                log.debug("user {} is already handled. do nothing.")
                return
            else:
                log.debug("fetch cd collections of user {}...".format(user_id))
                if session is None:
                    _session = session_queue.get()
                else:
                    _session = session
                start = 0
                cd_collection = []
                _session.headers['Host'] = 'music.douban.com'
                try:
                    while True:
                        r = _session.get(music_url_template.format(user_id, start))
                        if r.status_code != 200:
                            r.raise_for_status()
                        if r.url.startswith(login_url):
                            log.debug("must login")
                            r = login(url=r.url, res=r, session=_session)
                        cds = re.findall(pattern_cd, r.text)
                        intros = re.findall(pattern_intro, r.text)
                        cds_of_page = list(
                            map(lambda x, y: {'item-id': x[0], 'item-name': x[1].strip(), 'intro': y}, cds,
                                intros))
                        cd_collection.extend(cds_of_page)
                        if len(cds_of_page) < COUNT_PER_PAGE:
                            break
                        else:
                            start += COUNT_PER_PAGE
                        _session.headers['Referer'] = r.url
                        random_sleep()
                    user['cds'] = cd_collection
                    users[i] = user
                    if depth < MAX_DEPTH:
                        fetch_followings(user_id, depth, session=_session)
                finally:
                    if session is None:
                        session_queue.put(_session)
                return
    log.error("no entry of user {} found!".format(user_id))
    raise Exception("no entry of user {} found!".format(user_id))


def main():
    """
    The main process.
    :return: None
    """
    jobs = []
    with Pool(processes=MAX_WORKERS) as pool:
        log.debug("start...")
        init_session_queue(MAX_WORKERS)
        s = session_queue.get()
        try:
            login(session=s)
            fetch_followings('some_id', 0, session=s)
        finally:
            session_queue.put(s)
        while True:
            try:
                task = id_queue.get(timeout=1)
            except Empty:
                if all(job.ready() for job in jobs):
                    log.debug("all jobs done.")
                    break
            else:
                log.debug("task {} gotten".format(task))
                job = pool.apply_async(proceed_user, args=[task['id'], task['depth']])
                jobs.append(job)
    try:
        with open(result_file_path, mode='w', encoding='utf-8') as file:
            log.debug("write to json file. path: {}".format(result_file_path))
            log.debug("length of users: {}".format(len(users)))
            file.write(json.dumps({'users': list(users)}, indent=4))
    except Exception as e:
        log.exception(e)


if __name__ == '__main__':
    main()
