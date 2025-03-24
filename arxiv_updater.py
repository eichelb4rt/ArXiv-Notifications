import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any, Callable

import feedparser
import pymupdf
import pymupdf4llm
import requests
from dotenv import dotenv_values
from mistralai import Mistral
from tqdm import tqdm

SECRETS = dotenv_values(".env")


CS_CLASSES = [
    'cs.' + cat for cat in [
        'AI', 'AR', 'CC', 'CE', 'CG', 'CL', 'CR', 'CV', 'CY', 'DB',
        'DC', 'DL', 'DM', 'DS', 'ET', 'FL', 'GL', 'GR', 'GT', 'HC',
        'IR', 'IT', 'LG', 'LO', 'MA', 'MM', 'MS', 'NA', 'NE', 'NI',
        'OH', 'OS', 'PF', 'PL', 'RO', 'SC', 'SD', 'SE', 'SI', 'SY',
    ]
]


ArticleInfo = dict[str, Any]


def query_mistral(query: str) -> str:
    '''
    Queries Mistral model.

    @Params:
        query... string representing the query

    @Returns:
        answer string
    '''

    model = "mistral-large-latest"
    client = Mistral(api_key=SECRETS["MISTRAL_API_TOKEN"])

    chat_response = client.chat.complete(
        model=model,
        messages=[
            {
                "role": "user",
                "content": query
            },
        ]
    )
    outp = chat_response.choices[0].message.content
    return outp


def query_arxiv(keywords: list[str], last_date: str, max_results: int) -> dict[str, ArticleInfo]:
    '''
    First step of pipeline: Search for new papers on ArXiV.

    @Params:
        keywords... List of strings representing keywords of interest
        last_date... start date for search
        max_results... maximum results for each class (will keep only the newest ones)

    @Returns:
        dictionary with key = paper name, value = details to paper
    '''
    start_date = date.fromisoformat(last_date)
    kw_query = '%28'
    for kws in keywords:
        kw_str = '%28'
        for part_kws in kws:
            tmp = 'abs:%22'
            for kw in part_kws.split(' '):
                tmp += kw.lower() + '+'
            tmp = tmp[:-1]
            tmp += '%22'
            kw_str += f'{tmp}+AND+'
        kw_str = kw_str[:-5]

        kw_query += f'{kw_str}%29+OR+'
    kw_query = kw_query[:-4]
    kw_query += '%29'

    articles = {}
    for cat in CS_CLASSES:
        query = f'http://export.arxiv.org/api/query?search_query={kw_query}+AND+cat:{cat}&start=0&max_results={max_results}&sortBy=lastUpdatedDate&sortOrder=descending'
        response = urllib.request.urlopen(query).read()
        feed = feedparser.parse(response)
        if len(feed.entries) > 0:
            for i, article in enumerate(feed.entries):
                if (article['updated_parsed'] >= start_date.timetuple()):
                    article_info = {
                        'title': article['title'].replace('\n', ''),
                        'date': article['updated_parsed'],
                        'authors': [author['name'] for author in article['authors']],
                        'link': article['link'],
                        'abstract': article['summary'].replace('\n', '')
                    }
                    article_id = article_info['title'].replace(' ', '_').replace(':', '_').replace('-', '_').replace('__', '_').replace('___', '_').replace('?', '').replace('!', '').lower()
                    articles[article_id] = article_info
    return articles


def download_articles(articles: dict[str, ArticleInfo], download_dir: str) -> None:
    '''
    Second step of pipeline: download the papers.

    @Params:
        articles... result dictionary from query_arxiv function
        download_dir... path where to download to
    '''

    del_list = []
    for filename in articles:
        filepath = os.path.join(download_dir, f'{filename}.pdf')
        if not os.path.exists(filepath):
            try:
                urllib.request.urlretrieve(articles[filename]['link'].replace('abs', 'pdf'), filepath)
            except OSError:
                del_list.append(filename)
    for filename in del_list:
        del articles[filename]


def make_summaries(download_dir: str, preferences: list[str], max_pages: int, query_llm: Callable[[str], str] = query_mistral) -> dict[str, str]:
    '''
    Third step of pipeline: scrape text from pdf and use LLM to summarize.

    @Params:
        download_dir...  path where papers have been downloaded
        preferences... list of strings specifying users preferences
        query_llm... function, that takes a query string and provides an answer string

    @Returns:
        dictionary with key = paper name, value = summary
    '''

    if len(preferences) > 0:
        query = "You are talking to a researcher with the following preferences:\n"
        for pref in preferences:
            query += f'- {pref}\n'
    else:
        query = ''
    query += "What is the main idea and novelty of the following paper?\n"
    query += "Please resume in a brief and concise manner in one paragraph.\n"
    query += "Do not repeat the title and the authors of the paper.\n"
    if len(preferences) > 0:
        query += "Keep in mind what might be interesting for the researcher regarding his preferences.\n"

    summaries = {}
    for filename in tqdm(os.listdir(download_dir)):
        filepath = os.path.join(download_dir, f'{filename}')
        doc = pymupdf.open(filepath)
        md_text = pymupdf4llm.to_markdown(filepath, pages=range(min(max_pages, len(doc))), show_progress=False).encode("utf-8", "replace").decode("utf8")
        print(query + md_text)
        summaries[filename] = query_llm(query + md_text)
    return summaries


def create_overviews(articles: dict[str, ArticleInfo], summaries: dict[str, str], keywords: list[list[str]]) -> list[str]:
    '''
    Fourth step of pipeline:Creates a single pdf as summary.

    @Params:
        articles... result from query_arxiv function with details about papers
        summaries... result from make_summaries function with summaries for each paper
        keywords... list of keywords that we were interested in
        summary_dir... directory where to save summary file
        timestamp... for naming the file

    @Returns:
        path to file
    '''

    # sort by date
    filenames = list(summaries.keys())
    dates = [f"{datetime(*articles[filename[:-4]]['date'][:6]):%Y-%m-%d}" for filename in filenames]
    filenames = [x for _, x in sorted(zip(dates, filenames))]

    replace_dict = {
        '𝜖': 'epsilon'
    }

    overviews = []
    for filename in filenames:
        overview = f"<b>Title:</b> {articles[filename[:-4]]["title"]}\n\n"
        summary = summaries[filename]
        for c in replace_dict:
            summary = summary.replace(c, replace_dict[c])
        overview += f"<b>Summary:</b>\n{summary}\n\n"
        overview += f"<b>Authors:</b> {", ".join(articles[filename[:-4]]["authors"])}\n"
        overview += f"<b>Date:</b> {datetime(*articles[filename[:-4]]['date'][:6]):%Y-%m-%d}\n"
        overview += f"<b>Link:</b> {articles[filename[:-4]]["link"]}"
        overviews.append(overview)
    return overviews


def send_message(message: str, chat_id: int) -> None:
    args = {
        "parse_mode": "HTML",
        "chat_id": chat_id,
        "text": message,
        "link_preview_options": json.dumps({"is_disabled": True}),
    }
    response = requests.post(f"https://api.telegram.org/bot{SECRETS["TELEGRAM_API_TOKEN"]}/sendMessage?{urllib.parse.urlencode(args)}")
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)


def main():
    # read from config file
    cwd = os.path.dirname(__file__)
    with open(os.path.join(cwd, 'config.json')) as f:
        config = json.load(f)
    keywords = config['keywords']
    preferences = config['preferences']
    last_date = config['last_date']
    download_dir = os.path.join(cwd, config['download_dir'])
    max_results = config['max_results']
    max_pages = config['max_pages']
    chat_id = SECRETS["TELEGRAM_CHAT_ID"]
    ###################################

    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    print('Scraping ArXiV...')
    articles = query_arxiv(keywords, last_date, max_results)
    print('done.')
    timestamp = datetime.now()
    
    if len(articles) == 0:
        print('No new articles found.')
        return

    
    print(f'Found {len(articles)} new articles.')

    print('Downloading PDFs...')
    download_articles(articles, download_dir)
    print('done.')

    print('Using LLM to make summaries...')
    summaries = make_summaries(download_dir, preferences, max_pages)
    print('done.')

    print('Creating PDF...')
    overviews = create_overviews(articles, summaries, keywords)

    print('Sending message...')
    initial_message = f"Found {len(overviews)} new Papers for {", ".join(
        [f"({" & ".join(kw_list)})" for kw_list in keywords]
    )}"
    send_message(initial_message, chat_id)
    for overview in overviews:
        send_message(overview, chat_id)
    print('done.')

    print('Deleting articles...')
    for file in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, file))
    print('done.')

    print('Updating config...')
    config['last_date'] = f'{timestamp:%Y-%m-%d}'
    with open(os.path.join(cwd, 'config.json'), 'w') as outfile:
        json.dump(config, outfile, indent='\t')
    print('done.')


if __name__ == "__main__":
    main()
