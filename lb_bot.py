import asyncio
import logging
from re import fullmatch

import requests
from bs4 import BeautifulSoup
import aiohttp

from urllib.parse import urljoin, quote_plus


LB_SEARCH_ENDPOINT = 'https://letterboxd.com/search/films/'


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
    async with aiohttp.ClientSession(loop=asyncio.get_event_loop()) as session:
        async with session.get(urljoin(LB_SEARCH_ENDPOINT, quote_plus(query))) as resp:
            if resp.status >= 400:
                raise RuntimeError()
            soup = BeautifulSoup(await resp.text(), features="html.parser")
            title = soup.select_one('ul.results > li').select_one(
                'span.film-title-wrapper > a').text
            logging.debug(title)
            logging.info(f"got title '{title}' for query '{query}'")
            return title
    return ''


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
    loop = asyncio.get_event_loop()
    r = loop.run_until_complete(t)
