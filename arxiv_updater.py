# general
from datetime import date, datetime
import os
import json
from tqdm import tqdm

# Arxiv API
import urllib.request
import urllib.parse
import feedparser

# scrape pdf and feed to LLM
from mistralai import Mistral
import pymupdf4llm
import pymupdf

# create summary pdf
from pylatex import Command, Document, Section, Package,  NewLine
from pylatex.utils import NoEscape, escape_latex
from pylatexenc import latexencode

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

def query_mistral(query:str) -> str:
    '''
    Queries Mistral model.

    @Params:
        query... string representing the query

    @Returns:
        answer string
    '''

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

def query_arxiv(keywords : list, last_date : str, max_results : int) -> dict:
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
                    id = article_info['title'].replace(' ', '_').replace(':', '_').replace('-', '_').replace('__', '_').replace('___', '_').replace('?', '').replace('!', '').lower()
                    if id not in articles:
                        counter += 1
                    articles[id] = article_info
    return articles

def download_articles(articles: dict, download_dir:str):
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

def make_summaries(download_dir:str, preferences:list, query_llm:callable = query_mistral) -> dict:
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
    
    
    outps = {}
    for filename in tqdm(os.listdir(download_dir)):
        filepath = os.path.join(download_dir, f'{filename}')
        doc = pymupdf.open(filepath)
        md_text = pymupdf4llm.to_markdown(filepath, pages = range(min(max_pages, len(doc))), show_progress= False)
        outps[filename] = query_llm(query + md_text)
    return outps

def create_summary_pdf(articles:dict, summaries:dict, keywords:list, summary_dir:str, timestamp:datetime.date) -> str:
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
        '𝜖' : 'epsilon'
    }
    datestr = "{:%B %d, %Y}".format(datetime.now())
    
    doc = Document()
    doc.packages.append(Package('hyperref'))
    
    title = 'New Papers for'
    for kw in keywords:
        line_str = '('
        for tmp in kw:
            line_str += f' {tmp} AND'
        line_str = line_str[:-4] + ' )'
        title += f' {line_str},'
    title = title[:-1]
    
    doc.preamble.append(Command("title", title))
    doc.preamble.append(Command("date", NoEscape(r"\today")))
    doc.append(NoEscape(r"\maketitle"))
    
    for filename in filenames:
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
            tmp = f"{datetime(*articles[filename[:-4]]['date'][:6]):%Y-%m-%d}"
            date_str = f"Date: {tmp}, "
            doc.append(date_str)
            link = escape_latex(articles[filename[:-4]]['link'])
            link_str = f"Link: \\url{{{link}}}"
            doc.append(NoEscape(link_str))


    
    summary_name = f'summary_{timestamp:%Y_%m_%d}'
    doc.generate_pdf(os.path.join(summary_dir, summary_name), clean_tex=False, compiler='pdfLaTeX')
    
    
    path_to_file = os.path.join(summary_dir, f'{summary_name}.pdf')
    return path_to_file

def send_emails(emails:list, smtp_server:str, smtp_port:str, smtp_login:str, smtp_pw:str, path_to_file:str, keywords:list, last_date:str, timestamp:datetime.date, n_papers:int):
    '''
    Last step of pipeline: sends email with summary results.

    @Params:
        emails... list of emails to send to
        smtp_server... provider of smtp
        smtp_port... port of smtp
        smtp_login... account from where to send
        smtp_pw... password for account
        path_to_file... path to file for attachment
        keywords... list of keywords that were used for search
        last_date... start date for search
        timestamp... end date for search
        n_papers... how many papers were found
    '''
    
    subject = "ArXiV update"
    body = f"We found {n_papers} new papers regarding the following topics:\n"
    for kw in keywords:
        line_str = '- '
        for tmp in kw:
            line_str += f'{tmp}, '
        line_str = line_str[:-2]
        body += f'{line_str}\n'
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
    cwd = os.path.dirname(__file__)
    with open(os.path.join(cwd, 'config.json')) as f:
        config = json.load(f)
    keywords = config['keywords']
    preferences = config['preferences']
    last_date = config['last_date']
    emails = config['emails']
    smtp_server = config['smtp_server']
    smtp_port = config['smtp_port']
    smtp_login = config['smtp_login']
    smtp_pw = config['smtp_pw']
    download_dir = os.path.join(cwd, config['download_dir'])
    summary_dir = os.path.join(cwd, config['summary_dir'])
    max_results = config['max_results']
    max_pages = config['max_pages']
    ###################################


    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    if not os.path.exists(summary_dir):
        os.makedirs(summary_dir)

    print('Scraping ArXiV...')
    articles = query_arxiv(keywords, last_date, max_results)
    print('done.')
    timestamp = datetime.now()

    if len(articles) > 0:
        print(f'Found {len(articles)} new articles.')
        
        print('Downloading PDFs...')
        download_articles(articles, download_dir)
        print('done.')

        print('Using LLM to make summaries...')
        summaries = make_summaries(download_dir, preferences)
        print('done.')

        print('Creating PDF...')
        try:
            path_to_file = create_summary_pdf(articles, summaries, keywords, summary_dir, timestamp)
        except:
            print('Error occured, but PDF was generated nonetheless')
            summary_name = f'summary_{timestamp:%Y_%m_%d}'
            for file in os.listdir(summary_dir):
                if not file.endswith('pdf'):
                    p = os.path.join(summary_dir, file)
                    os.remove(p)
            path_to_file = os.path.join(summary_dir, f'{summary_name}.pdf')
            assert os.path.exists(path_to_file)
        print(f'done.\nPDF located at {path_to_file}')

        print('Sending emails...')
        send_emails(emails, smtp_server, smtp_port, smtp_login, smtp_pw, path_to_file, keywords, last_date, timestamp, len(articles))
        print('done.')

        print('Deleting articles...')
        for file in os.listdir(download_dir):
            os.remove(os.path.join(download_dir, file))
        print('done.')
            

    else:
        print('No new articles found.')

    print('Updating config...')
    config['last_date'] = f'{timestamp:%Y-%m-%d}'
    with open(os.path.join(cwd, 'config.json'),'w') as outfile:
        json.dump(config, outfile, indent = '\t')
    print('done.')
