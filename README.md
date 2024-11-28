# ArXiV Updates via LLM generated summaries

This script is meant to search for new papers, summarize them using an LLM and send out a pdf file via email.

You can set everything you need in the `config.json` file:
- `keywords`: Keywords to search on ArXiV.
- `preferences`: Your personal preferences for creating the summaries. This will be added to the LLM prompt.
- `emails`: To whom the emails will be sent.
- `last_date`: Start date for search (up to today)
- `smtp_*`: SMTP stuff for sending the mail (see [here](https://realpython.com/python-send-email/) for an example) 
- `download_dir`: Where papers are downloaded internally
- `summary_dir`: Where summaries are saved
- `max_results`: Maximum number of papers per category
- `max_pages`: Maximum number of pages for LLM to read


