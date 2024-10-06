import asyncio
import logging
import re
from re import fullmatch
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
import aiohttp

from urllib.parse import urljoin, quote_plus

logger = logging.getLogger('raffle_bot.db')

LB_BASE_URL = 'https://letterboxd.com'
LB_SEARCH_ENDPOINT = 'https://letterboxd.com/s/search/films/'

def prettyprint_movie(movie_title):
    """
    Converts movie title year to movie title (year)
    """
    split = movie_title.rsplit(' ', 1)
    if len(split) < 2:
        return movie_title
    year = split[1]
    if re.fullmatch(r'\d{4}', year):
        return f'{split[0]} ({year})'
    return movie_title


async def get_movie_title(query):
    year = __check_year(query)
    if year:
        # XXX: if year is in brackets, the LB search returns wrong results
        # so if anyone uses brackets, we just simply append the year onto the original
        # query without any brackets
        split_q = query.split()[:-1]
        split_q.append(year)
        query = ' '.join(split_q)
    # XXX: lb bot doesn't handle this case either, but once it does, we'll need to do it as well
    # query = query.replace('/', ' ')
    query = query.replace('.', ' ')
    async with aiohttp.ClientSession(loop=asyncio.get_event_loop()) as session:
        async with session.get(urljoin(LB_SEARCH_ENDPOINT, quote_plus(query))) as resp:
            if resp.status >= 400:
                return '', ''
            soup = BeautifulSoup(await resp.text(), features="html.parser")
            anchor = soup.select_one('ul.results > li')
            if anchor == None:
                return '', ''
            film = anchor.select_one('span.film-title-wrapper > a')
            title = film.text
            url = film.attrs.get('href', '')
            logger.info(f"got title '{title}' and '{url}' for query '{query}'")
            return prettyprint_movie(title), url
    return '', ''


@dataclass
class FilmReview:
    user: str
    url: str
    rating: int


async def get_user_review(session, user, film_id):
    user = user.strip()
    url = f'{LB_BASE_URL}/{user}{film_id}'
    logger.info(f'fetching url {url}')
    async with session.get(url) as resp:
        logger.info(f'got status {resp.status}')
        if resp.status >= 400:
            return None
        return FilmReview(user, url, None)
    return None

async def try_get_user_review(session, user, film_name):
    print(f'getting {film_name}')
    title, url = await get_movie_title(film_name)
    if url:
        return await get_user_review(session, user, url)


def __check_year(keywords):
    """
    Taken from https://github.com/velzerat/lb-bot

    MIT License

    Copyright (c) 2018 Thomas Philippe

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
    """
    last_word = keywords.split()[-1]
    if fullmatch(r'\(\d{4}\)', last_word):
        return last_word.replace('(', '').replace(')', '')
    return ''


if __name__ == '__main__':
    # t = get_movie_title('little forest summer/autumn')
    t = get_movie_title('young mr. Lincoln')
    #t = get_user_review('vnki', '/film/my-own-private-idaho')
    loop = asyncio.get_event_loop()
    r = loop.run_until_complete(t)
    print(r)
