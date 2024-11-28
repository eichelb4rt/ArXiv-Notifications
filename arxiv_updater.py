# general
from datetime import date, datetime
import time
import os
import json

# Arxiv API
import requests
import urllib.request
import feedparser

# scrape pdf and feed to LLM
from mistralai import Mistral
import pymupdf4llm
import pymupdf

# create summary pdf
from pylatex import Command, Document, Section, Subsection, Description, Hyperref, Package,  NewLine
from pylatex.utils import NoEscape, escape_latex
from pylatexenc import latexencode
import urllib.parse

# sending mail
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


CS_CLASSES = [
    'cs.' + cat for cat in [
        'AI', 'AR', 'CC', 'CE', 'CG', 'CL', 'CR', 'CV', 'CY', 'DB',
        'DC', 'DL', 'DM', 'DS', 'ET', 'FL', 'GL', 'GR', 'GT', 'HC',
        'IR', 'IT', 'LG', 'LO', 'MA', 'MM', 'MS', 'NA', 'NE', 'NI',
        'OH', 'OS', 'PF', 'PL', 'RO', 'SC', 'SD', 'SE', 'SI', 'SY',
    ]
]

def query_mistral(query):
    model = "mistral-large-latest"
    api_key = os.environ["MISTRAL_API_KEY"]
    client = Mistral(api_key=api_key)

    
    chat_response = client.chat.complete(
        model = model,
        messages = [
            {
                "role": "user",
                "content": query
            },
        ]
    )
    outp = chat_response.choices[0].message.content
    return outp

def query_arxiv(keywords, last_date, max_results):
    start_date = date.fromisoformat(last_date)
    kw_query = '%28'
    for kws in keywords:
        tmp = 'ti:%22'
        for kw in kws.split(' '):
            tmp += kw.lower() + '+'
        tmp = tmp[:-1]
        tmp += '%22'
        kw_query += f'{tmp}+OR+'
    kw_query = kw_query[:-4]
    kw_query += '%29'

    articles = {}
    counter = 0
    for cat in CS_CLASSES:
        query = f'http://export.arxiv.org/api/query?search_query={kw_query}+AND+cat:{cat}&start=0&max_results={max_results}&sortBy=lastUpdatedDate&sortOrder=descending'
        response = urllib.request.urlopen(query).read()
        feed = feedparser.parse(response)
        if len(feed.entries) > 0:
            for i, article in enumerate(feed.entries):
                if(article['updated_parsed'] >= start_date.timetuple()):
                    article_info = {
                        'title' : article['title'].replace('\n', ''),
                        'date' : article['updated_parsed'],
                        'authors' : [author['name'] for author in article['authors']],
                        'link' : article['link'],
                        'abstract' : article['summary'].replace('\n', '')
                    }
                    id = article_info['title'].replace(' ', '_').replace(':', '_').replace('-', '_').replace('__', '_').replace('___', '_').lower()
                    if id not in articles:
                        counter += 1
                    articles[id] = article_info
    return articles

def download_articles(articles, download_dir):
    for filename in articles:
        filepath = os.path.join(download_dir, f'{filename}.pdf')
        if not os.path.exists(filepath):
            urllib.request.urlretrieve(articles[filename]['link'].replace('abs', 'pdf'), filepath)

def make_summaries(download_dir, preferences, query_llm = query_mistral):
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
    
    
    outps = {}
    for filename in os.listdir(download_dir):
        filepath = os.path.join(download_dir, f'{filename}')
        doc = pymupdf.open(filepath)
        md_text = pymupdf4llm.to_markdown(filepath, pages = range(min(max_pages, len(doc))), show_progress= False)
        outps[filename] = query_llm(query + md_text)
    return outps


def create_summary_pdf(articles, summaries, keywords, summary_dir, timestamp):
    replace_dict = {
        '𝜖' : 'epsilon'
    }
    datestr = "{:%B %d, %Y}".format(datetime.now())
    
    doc = Document()
    doc.packages.append(Package('hyperref'))
    
    title = 'New Papers for'
    for kw in keywords:
        title += f' {kw},'
    title = title[:-1]
    
    doc.preamble.append(Command("title", title))
    doc.preamble.append(Command("date", NoEscape(r"\today")))
    doc.append(NoEscape(r"\maketitle"))
    
    for filename in summaries:
        paper_title = latexencode.unicode_to_latex(articles[filename[:-4]]['title'])
        splits = paper_title.split('\\$')
        
        for i in range(len(splits)):
            if i%2 == 1:
                splits[i] = f'\\texorpdfstring{{${splits[i]}$}}{{{splits[i]}}}'
        paper_title = '\\boldmath '
        for s in splits:
            paper_title += s
        with doc.create(Section(NoEscape(paper_title))):
            
            text = summaries[filename]
            for c in replace_dict:
                text = text.replace(c, replace_dict[c])
        
            doc.append(latexencode.unicode_to_latex(text))
            #doc.append(NoEscape(outps[filename]))
            doc.append(NewLine())
    
            link = escape_latex(articles[filename[:-4]]['link'])
            link_str = f"Link: \\url{{{link}}}"
            doc.append(NoEscape(link_str))
    
    summary_name = f'summary_{timestamp:%Y_%m_%d}'
    doc.generate_pdf(os.path.join(summary_dir, summary_name), clean_tex=False, compiler='pdfLaTeX')
    
    for fileend in ['.aux', '.log', '.tex']:
        p = os.path.join(summary_dir, f'{summary_name}{fileend}')
        if os.path.exists(p):
            os.remove(p)
    path_to_file = os.path.join(summary_dir, f'{summary_name}.pdf')
    return path_to_file


def send_emails(emails, smtp_server, smtp_port, smtp_login, smtp_pw, path_to_file, keywords, last_date, timestamp, n_papers):
    subject = "ArXiV update"
    body = f"We found {n_papers} new papers regarding the following topics:\n"
    for kw in keywords:
        body += f'- {kw}\n'
    body += f'Time period: {last_date} until {timestamp:%Y-%m-%d}\n'
    body += f"See the summary in the attachment."
    
    for recipient_email in emails:
        message = MIMEMultipart()
        message['Subject'] = subject
        message['From'] = smtp_login
        message['To'] = recipient_email
        body_part = MIMEText(body)
        message.attach(body_part)
    
        with open(path_to_file,'rb') as file:
            message.attach(MIMEApplication(file.read(), Name=f'summary_{timestamp:%Y_%m_%d}.pdf'))
    
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port, timeout=5) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(smtp_login, smtp_pw)
            server.sendmail(smtp_login, recipient_email, message.as_string())
    

if __name__ == '__main__':


    # read from config file
    with open('config.json') as f:
        config = json.load(f)
    keywords = config['keywords']
    preferences = config['preferences']
    last_date = config['last_date']
    emails = config['emails']
    smtp_server = config['smtp_server']
    smtp_port = config['smtp_port']
    smtp_login = config['smtp_login']
    smtp_pw = config['smtp_pw']
    download_dir = config['download_dir']
    summary_dir = config['summary_dir']
    max_results = config['max_results']
    max_pages = config['max_pages']
    ###################################


    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    if not os.path.exists(summary_dir):
        os.makedirs(summary_dir)

    print('Scraping ArXiV...', end='')
    articles = query_arxiv(keywords, last_date, max_results)
    print('done.')
    timestamp = datetime.now()

    if len(articles) > 0:
        print(f'Found {len(articles)} new articles.')
        
        print('Downloading PDFs...', end='')
        download_articles(articles, download_dir)
        print('done.')

        print('Using LLM to make summaries...', end='')
        summaries = make_summaries(download_dir, preferences)
        print('done.')

        print('Creating PDF...', end='')
        path_to_file = create_summary_pdf(articles, summaries, keywords, summary_dir, timestamp)
        print(f'done.\nPDF located at {path_to_file}')

        print('Sending emails...', end='')
        send_emails(emails, smtp_server, smtp_port, smtp_login, smtp_pw, path_to_file, keywords, last_date, timestamp, len(articles))
        print('done.')

        print('Deleting articles...', end='')
        for file in os.listdir(download_dir):
            os.remove(os.path.join(download_dir, file))
        print('done.')
            

    else:
        print('No new articles found.')

    print('Updating config...', end='')
    config['last_date'] = f'{timestamp:%Y-%m-%d}'
    with open('config.json','w') as outfile:
        json.dump(config, outfile, indent = '\t')
    print('done.')
