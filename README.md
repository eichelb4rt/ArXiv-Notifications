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

You can set everything you need in the `config.json` and `last_request.json` files:

#### config.json

- `keywords`: Keywords to search on ArXiV. The lists represent a disjunktive normal form (DNF). That is, the lists are concatenated with OR, the entries of each list with AND.
- `preferences`: Your personal preferences for creating the summaries. This will be added to the LLM prompt.
- `emails`: To whom the emails will be sent.
- `buffer_days` : number of last days for which we store scraped results (to avoid uncovered time periods)
- `smtp_*`: SMTP stuff for sending the mail (see [here](https://realpython.com/python-send-email/) for an example) 
- `download_dir`: Where papers are downloaded internally
- `summary_dir`: Where summaries are saved
- `max_results`: Maximum number of papers per category
- `max_pages`: Maximum number of pages for LLM to read

#### last_request.json

- `last_date` : here you can set the earliest date that needs to be considered by the search
- `request_buffer` : only used internally to avoid uncovered time periods

## Scedule running once a day
On Windows, follow the instructions [here](https://mikenguyen.netlify.app/post/task-scheduler-with-python-and-anaconda-environment/) using the `run_updater.bat` file.


