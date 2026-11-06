import argparse
from datetime import date
from pathlib import Path
from .core import load_tasks, schedule
from .export import gantt, workbook, project_xml

def main():
    p = argparse.ArgumentParser(description='Create a schedule and cost report from a CSV task list.')
    p.add_argument('csv'); p.add_argument('--start', required=True, type=date.fromisoformat, help='Project start date (YYYY-MM-DD)')
    p.add_argument('--output', default='output')
    args = p.parse_args(); tasks = load_tasks(args.csv); timings = schedule(tasks)
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    gantt(tasks,timings,out/'gantt.svg'); workbook(tasks,timings,out/'variance.xlsx'); project_xml(tasks,timings,args.start,out/'schedule.xml')
    print(f'Wrote reports to {out}. Duration: {max(r["finish"] for r in timings.values())} working days.')
if __name__ == '__main__': main()
