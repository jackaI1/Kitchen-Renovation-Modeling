"""Publish task issues and a decision log using Atlassian Cloud REST APIs."""
import argparse
import base64
import html
import json
import os
from urllib.request import Request, urlopen
from .core import load_tasks, schedule


def post(base, path, payload, email, token):
    credentials = base64.b64encode(f'{email}:{token}'.encode()).decode()
    request = Request(base.rstrip('/') + path, data=json.dumps(payload).encode(), headers={'Authorization':'Basic '+credentials, 'Content-Type':'application/json', 'Accept':'application/json'}, method='POST')
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def publish(tasks, decisions, base, email, token, project, space, title):
    timings = schedule(tasks); issues = []
    for task in tasks:
        description = f'CSV task {task.id}; duration {task.duration} working days; dependencies: {", ".join(task.dependencies) or "none"}; float: {timings[task.id]["float"]} days; budget: {task.budget}; actual: {task.actual}.'
        payload = {'fields': {'project': {'key': project}, 'summary': task.name, 'issuetype': {'name':'Task'}, 'description': {'type':'doc','version':1,'content':[{'type':'paragraph','content':[{'type':'text','text':description}]}]}}}
        issues.append(post(base, '/rest/api/3/issue', payload, email, token)['key'])
    content = '<p>Project decisions:</p><pre>' + html.escape(decisions) + '</pre><p>Created Jira issues: ' + html.escape(', '.join(issues)) + '</p>'
    page = post(base, '/wiki/rest/api/content', {'type':'page','title':title,'space':{'key':space},'body':{'storage':{'value':content,'representation':'storage'}}}, email, token)
    return issues, page['id']


def main():
    p = argparse.ArgumentParser(description='Create Jira tasks and a Confluence decision-log page.')
    p.add_argument('csv'); p.add_argument('decisions'); p.add_argument('--project',required=True); p.add_argument('--space',required=True); p.add_argument('--title',default='Project delivery decision log')
    a = p.parse_args()
    base, email, token = (os.environ[k] for k in ('ATLASSIAN_URL','ATLASSIAN_EMAIL','ATLASSIAN_TOKEN'))
    with open(a.decisions, encoding='utf-8') as f: decisions = f.read()
    issues, page = publish(load_tasks(a.csv), decisions, base, email, token, a.project, a.space, a.title)
    print(f'Created {len(issues)} Jira issues and Confluence page {page}.')
if __name__ == '__main__': main()
