# project-schedule-cost-tracker

I built a project delivery tracker to learn how the underlying idea works. This is a learning project.

## Try it

Install Python 3.9 or newer, then run:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m tracker examples/capital_project.csv --start 2026-11-09
```

Open `output/gantt.svg` in a browser and `output/variance.xlsx` in Excel or LibreOffice. In ProjectLibre, choose File > Open and select `output/schedule.xml` (Microsoft Project XML format). The sample represents a small capital project; replace it with your own CSV using the same columns. Separate predecessor IDs with semicolons, use whole working days for duration, and enter progress as a fraction from 0 to 1. Dates use Monday to Friday, eight hours per day, without holidays. A weekend start moves to Monday.

## Share tasks and decisions

For Atlassian Cloud, create an API token and set `ATLASSIAN_URL` to your site URL, `ATLASSIAN_EMAIL` to your account email and `ATLASSIAN_TOKEN` to the token in your shell. Use a Jira project key and a Confluence space key where your account can create content:

```sh
python -m tracker.atlassian examples/capital_project.csv examples/decisions.txt --project DEMO --space DOC --title 'Project delivery decisions'
```

This creates one Jira Task per CSV row and a Confluence page containing the decision log and issue keys. Each run creates new records; it does not update existing ones or create Jira dependency links. A failure partway through may leave some issues created. Keep tokens out of files and version control. The tests use a local HTTP server, so no Atlassian account is needed to run them.

## How the numbers work

A forward pass finds each task's earliest start after its predecessors finish. A backward pass finds its latest start without delaying the whole project. The difference is float, or spare working days. The tool rejects missing dependencies, duplicate IDs and cycles.

Earned value is budget multiplied by progress. Cost variance is earned value minus actual cost, so a negative number signals spending above the value of completed work. The forecast at completion is total budget divided by the current cost efficiency (earned value divided by actual cost). It is blank when no value has been earned; it is an estimate, not a guarantee. The workbook contains formulas, which recalculate when opened in spreadsheet software. The ProjectLibre XML carries task durations, dates, predecessor links, progress and costs; the CSV remains the source for this tracker.

## Tests and limits

There are 3 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `project-schedule-cost-tracker-tests.yml`.
