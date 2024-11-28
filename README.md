# ArXiV Updates via LLM generated summaries
This script is meant to search for new papers, summarize them using an LLM and send out a pdf file via email.
We further provide functionality to let it run once a day on windows.

## LLM
In this version, we are using the free [Mistral](https://console.mistral.ai/) model.
If you want to change it, simply provide a different function to the `make_summaries` function.

## Requirements
```
conda create --name arxiv_update
conda activate arxiv_update
pip install -r requirements.txt
```


## Configuration



You can set everything you need in the `config.json` file:
- `keywords`: Keywords to search on ArXiV.
- `preferences`: Your personal preferences for creating the summaries. This will be added to the LLM prompt.
- `emails`: To whom the emails will be sent.
- `last_date`: Start date for search (up to today, format YYYY-MM-DD)
- `smtp_*`: SMTP stuff for sending the mail (see [here](https://realpython.com/python-send-email/) for an example) 
- `download_dir`: Where papers are downloaded internally
- `summary_dir`: Where summaries are saved
- `max_results`: Maximum number of papers per category
- `max_pages`: Maximum number of pages for LLM to read

## Scedule running once a day
On Windows, follow the instructions [here](https://mikenguyen.netlify.app/post/task-scheduler-with-python-and-anaconda-environment/) using the `run_updater.bat` file.


