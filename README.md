# ArXiV Updates via LLM generated summaries

This script is meant to search for new papers, summarize them using an LLM and send out summaries via a telegram bot.

## LLM

In this version, we are using the free [Mistral](https://console.mistral.ai/) model.
If you want to change it, simply provide a different function to the `make_summaries` function.

## Requirements

```text
uv venv
uv pip install -r requirements.txt
```

## Setup

### Config

You can edit your configuration in `config.json`.

- `keywords`: Keywords to search on ArXiV. The lists represent a disjunktive normal form (DNF). That is, the lists are concatenated with OR, the entries of each list with AND.
- `preferences`: Your personal preferences for creating the summaries. This will be added to the LLM prompt.
- `last_date`: Start date for search (up to today, format YYYY-MM-DD)
- `download_dir`: Where papers are downloaded internally
- `max_results`: Maximum number of papers per category. Keep it mind that a standard telegram bot can only send 20 messages per minute.
- `max_pages`: Maximum number of pages for LLM to read

### Secrets

Put your API tokens and the telegram chat id into `.env`. A template for this can be found in `.env.template`.

## Scedule running once a day

On Windows, follow the instructions [here](https://mikenguyen.netlify.app/post/task-scheduler-with-python-and-anaconda-environment/) using the `run_updater.bat` file.
