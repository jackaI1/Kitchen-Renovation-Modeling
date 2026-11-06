"""Small critical-path engine and loss-preserving XER reader/writer."""
import argparse
import csv
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from pathlib import Path


def dt(value):
    return datetime.fromisoformat(value) if value else None


def block(text, start):
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '(': depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0: return text[start:i+1]
    raise ValueError('Unbalanced calendar data')


def entries(text):
    # Direct child records, each begins with (0||identifier(...
    result = []
    i = 0
    while i < len(text):
        m = re.search(r'\(0\|\|([^()]+)\(', text[i:])
        if not m: break
        pos = i + m.start()
        item = block(text, pos)
        result.append((m.group(1), item))
        i = pos + len(item)
    return result


def shifts(text):
    result = []
    for m in re.finditer(r'\((?:s\|([^|()]+)\|f\|([^|()]+)|f\|([^|()]+)\|s\|([^|()]+))\)', text):
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        start, end = time.fromisoformat(a), time.fromisoformat(b)
        if start >= end: raise ValueError('Overnight or empty calendar shift is unsupported')
        result.append((start, end))
    result.sort()
    if any(result[i][1] > result[i+1][0] for i in range(len(result)-1)): raise ValueError('Overlapping shifts')
    return result


class Calendar:
    def __init__(self, week, exceptions=None):
        self.week, self.exceptions = week, exceptions or {}
        if not any(week.values()): raise ValueError('Calendar has no working time')

    @classmethod
    def standard(cls):
        return cls({i: [(time(8), time(16))] for i in range(5)})

    @classmethod
    def parse(cls, data):
        if not data: return cls.standard()
        root = entries(data)
        if not root or root[0][0] != 'CalendarData': raise ValueError('Unsupported calendar format')
        sections = dict(entries(root[0][1][len('(0||CalendarData'): -1]))
        if 'DaysOfWeek' not in sections: raise ValueError('Calendar missing DaysOfWeek')
        days = entries(sections['DaysOfWeek'][len('(0||DaysOfWeek'):-1])
        if {name for name, _ in days} != set('1234567'): raise ValueError('Calendar must define all seven weekdays')
        week = {(int(name)+5)%7: shifts(item) for name, item in days}
        exceptions = {}
        if 'Exceptions' in sections:
            for _, item in entries(sections['Exceptions'][len('(0||Exceptions'):-1]):
                m = re.search(r'\(d\|(\d+)\)', item)
                if not m: raise ValueError('Unsupported calendar exception')
                day = (datetime(1899, 12, 30) + timedelta(days=int(m.group(1)))).date()
                exceptions[day] = shifts(item)
        return cls(week, exceptions)

    def intervals(self, date):
        return [(datetime.combine(date, a), datetime.combine(date, b)) for a,b in self.exceptions.get(date, self.week.get(date.weekday(), []))]

    def move(self, when, hours):
        if hours == 0: return when
        forward = hours > 0
        remaining = abs(hours) * 3600
        cursor = when
        for _ in range(36600):
            intervals = self.intervals(cursor.date())
            for start, end in (intervals if forward else reversed(intervals)):
                if forward:
                    point = max(cursor, start)
                    available = max(0, (end-point).total_seconds())
                    if available and remaining <= available: return point + timedelta(seconds=remaining)
                    remaining -= available
                else:
                    point = min(cursor, end)
                    available = max(0, (point-start).total_seconds())
                    if available and remaining <= available: return point - timedelta(seconds=remaining)
                    remaining -= available
            cursor = datetime.combine(cursor.date() + timedelta(days=1 if forward else -1), time.min if forward else time.max)
        raise ValueError('Calendar search exceeded 100 years')

    def snap(self, when):
        for n in range(36600):
            day = when.date() + timedelta(days=n)
            for a,b in self.intervals(day):
                if when < b: return max(when, a)
        raise ValueError('Calendar search exceeded 100 years')

    def hours_between(self, start, end):
        if end < start: return -self.hours_between(end, start)
        total = 0
        day = start.date()
        while day <= end.date():
            for a,b in self.intervals(day): total += max(0, (min(end,b)-max(start,a)).total_seconds())
            day += timedelta(days=1)
        return total / 3600


@dataclass
class Task:
    id: str
    name: str
    duration: float
    calendar: Calendar
    actual_start: datetime = None
    actual_finish: datetime = None
    percent: float = 0
    early_start: datetime = None
    early_finish: datetime = None
    late_start: datetime = None
    late_finish: datetime = None
    float_hours: float = 0

@dataclass
class Link:
    pred: str
    succ: str
    kind: str
    lag: float

class Schedule:
    def __init__(self, tasks, links, data_date):
        self.tasks, self.links, self.data_date = tasks, links, data_date
        self.deadline = None

    def calculate(self):
        by = {t.id:t for t in self.tasks}
        if len(by) != len(self.tasks): raise ValueError('Duplicate task ID')
        incoming = {k:[] for k in by}; outgoing = {k:[] for k in by}
        for l in self.links:
            if l.pred not in by or l.succ not in by: raise ValueError('External or missing relationship endpoint')
            if l.kind not in ('FS','SS','FF'): raise ValueError('Unsupported relationship: '+l.kind)
            incoming[l.succ].append(l); outgoing[l.pred].append(l)
        order, ready = [], [k for k in by if not incoming[k]]
        counts = {k:len(v) for k,v in incoming.items()}
        while ready:
            k = ready.pop(0); order.append(k)
            for l in outgoing[k]:
                counts[l.succ] -= 1
                if counts[l.succ] == 0: ready.append(l.succ)
        if len(order) != len(by): raise ValueError('Relationship cycle')
        for k in order:
            t = by[k]; c = t.calendar
            if t.duration < 0: raise ValueError('Negative duration')
            if t.actual_finish:
                t.early_start, t.early_finish = t.actual_start, t.actual_finish
                continue
            start = c.snap(self.data_date)
            for l in incoming[k]:
                p = by[l.pred]
                anchor = (p.actual_start or p.early_start) if l.kind == 'SS' else p.early_finish
                bound = c.move(anchor, l.lag)
                if l.kind == 'FF': bound = c.move(bound, -t.duration)
                start = max(start, c.snap(bound))
            t.early_start = start
            t.early_finish = c.move(start, t.duration)
        finish = self.deadline or max(t.early_finish for t in self.tasks)
        for k in reversed(order):
            t = by[k]; c = t.calendar
            if t.actual_finish:
                t.late_start, t.late_finish, t.float_hours = t.early_start, t.early_finish, 0
                continue
            latest = c.move(finish, -t.duration)
            for l in outgoing[k]:
                s = by[l.succ]; sc = s.calendar
                target = s.late_finish if l.kind == 'FF' else s.late_start
                bound = sc.move(target, -l.lag)
                if l.kind in ('FS','FF'): bound = c.move(bound, -t.duration)
                latest = min(latest, bound)
            t.late_start = latest; t.late_finish = c.move(latest, t.duration)
            t.float_hours = round(c.hours_between(t.early_start, latest), 6)
        return self

class Xer:
    def __init__(self, path):
        raw = Path(path).read_bytes().decode('cp1252')
        lines = raw.splitlines()
        if not lines or not lines[0].startswith('ERMHDR'): raise ValueError('Missing XER header')
        self.header = lines[0]; self.tables = []; table = None; fields = None; ended = False
        for line in lines[1:]:
            parts = line.split('\t'); tag = parts[0]
            if tag == '%T': table = [parts[1], [], []]; self.tables.append(table); fields = None
            elif tag == '%F':
                if table is None: raise ValueError('Fields without table')
                fields = parts[1:]; table[1] = fields
            elif tag == '%R':
                if fields is None or len(parts)-1 != len(fields): raise ValueError('Invalid XER row')
                table[2].append(dict(zip(fields, parts[1:])))
            elif tag == '%E': ended = True; break
            elif line: raise ValueError('Unknown XER record: '+tag)
        if not ended: raise ValueError('Missing XER end marker')

    def rows(self, name):
        return next((t[2] for t in self.tables if t[0] == name), [])

    def model(self):
        projects = self.rows('PROJECT')
        if len(projects) != 1: raise ValueError('Exactly one project is required')
        project = projects[0]
        date = dt(project.get('last_recalc_date') or project.get('plan_start_date'))
        if not date: raise ValueError('Project requires a data date')
        calendars = {r['clndr_id']: Calendar.parse(r.get('clndr_data','')) for r in self.rows('CALENDAR')}
        tasks = []
        for r in self.rows('TASK'):
            if r.get('task_type') in ('TT_LOE','TT_WBS'): raise ValueError('Level-of-effort and WBS summary tasks are unsupported')
            cid = r.get('clndr_id') or project.get('clndr_id')
            if cid not in calendars: raise ValueError('Missing activity calendar: '+str(cid))
            duration = float(r.get('remain_drtn_hr_cnt') or r.get('target_drtn_hr_cnt') or 0)
            tasks.append(Task(r['task_id'], r.get('task_name',''), duration, calendars[cid], dt(r.get('act_start_date')), dt(r.get('act_end_date')), float(r.get('phys_complete_pct') or 0)))
        if not tasks: raise ValueError('No activities')
        links = [Link(r['pred_task_id'], r['task_id'], r['pred_type'].removeprefix('PR_'), float(r.get('lag_hr_cnt') or 0)) for r in self.rows('TASKPRED')]
        return Schedule(tasks, links, date)

    def apply(self, schedule):
        self.rows('PROJECT')[0]['last_recalc_date'] = fmt(schedule.data_date)
        by = {t.id:t for t in schedule.tasks}
        for r in self.rows('TASK'):
            t = by[r['task_id']]
            r.update({'remain_drtn_hr_cnt':str(t.duration), 'phys_complete_pct':str(t.percent), 'act_start_date':fmt(t.actual_start), 'act_end_date':fmt(t.actual_finish), 'status_code':'TK_Complete' if t.actual_finish else 'TK_Active' if t.actual_start else 'TK_NotStart', 'early_start_date':fmt(t.early_start), 'early_end_date':fmt(t.early_finish), 'late_start_date':fmt(t.late_start), 'late_end_date':fmt(t.late_finish), 'total_float_hr_cnt':str(t.float_hours)})
        for name, fields, rows in self.tables:
            if name in ('TASK','PROJECT'):
                for row in rows:
                    for key in row:
                        if key not in fields: fields.append(key)

    def write(self, path):
        lines = [self.header]
        for name, fields, rows in self.tables:
            lines += ['%T\t'+name, '%F\t'+'\t'.join(fields)]
            lines += ['%R\t'+'\t'.join(r.get(f,'') for f in fields) for r in rows]
        lines.append('%E')
        Path(path).write_bytes(('\r\n'.join(lines)+'\r\n').encode('cp1252'))

def fmt(value): return value.strftime('%Y-%m-%d %H:%M') if value else ''

def gantt(schedule, path):
    start = min(t.early_start for t in schedule.tasks); end = max(t.early_finish for t in schedule.tasks)
    span = max((end-start).total_seconds(), 1)
    rows = []
    for t in schedule.tasks:
        left = (t.early_start-start).total_seconds()/span*100
        width = max((t.early_finish-t.early_start).total_seconds()/span*100, .3)
        rows.append(f'<div class="row"><span>{html.escape(t.name)} ({html.escape(t.id)})</span><div class="track"><div class="bar {"critical" if t.float_hours <= 0 else ""}" style="left:{left:.3f}%;width:{width:.3f}%" title="{fmt(t.early_start)} to {fmt(t.early_finish)}; float {t.float_hours:g} h"></div></div></div>')
    Path(path).write_text('<!doctype html><meta charset="utf-8"><title>Schedule Gantt</title><style>body{font:15px system-ui;margin:2rem}.row{display:flex;align-items:center;margin:.5rem 0}.row span{width:220px}.track{position:relative;background:#eee;height:24px;flex:1}.bar{position:absolute;background:#377bb5;height:24px}.critical{background:#b33}</style><h1>Schedule Gantt</h1><p>'+fmt(start)+' to '+fmt(end)+'; red = critical</p>'+''.join(rows), encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description='Calculate a P6 XER schedule')
    parser.add_argument('xer'); parser.add_argument('--data-date'); parser.add_argument('--deadline', help='Required finish date, for negative float'); parser.add_argument('--progress', help='JSON object keyed by task ID'); parser.add_argument('--output'); parser.add_argument('--gantt')
    args = parser.parse_args()
    try:
        xer = Xer(args.xer); schedule = xer.model()
        if args.data_date: schedule.data_date = dt(args.data_date)
        if args.deadline: schedule.deadline = dt(args.deadline)
        if args.progress:
            updates = json.loads(Path(args.progress).read_text())
            by = {t.id:t for t in schedule.tasks}
            for key, u in updates.items():
                t = by[key]; t.actual_start = dt(u.get('actual_start')) if 'actual_start' in u else t.actual_start
                t.actual_finish = dt(u.get('actual_finish')) if 'actual_finish' in u else t.actual_finish
                t.percent = float(u.get('percent_complete', t.percent)); t.duration = float(u.get('remaining_hours', t.duration))
                if not 0 <= t.percent <= 100 or t.duration < 0 or (t.actual_finish and not t.actual_start): raise ValueError('Invalid progress for '+key)
        schedule.calculate()
        print('ID\tActivity\tEarly finish\tFloat (hours)\tStatus')
        for t in schedule.tasks: print(f'{t.id}\t{t.name}\t{fmt(t.early_finish)}\t{t.float_hours:g}\t'+('LATE' if t.float_hours < 0 else 'CRITICAL' if t.float_hours == 0 else ''))
        if args.output: xer.apply(schedule); xer.write(args.output)
        if args.gantt: gantt(schedule, args.gantt)
    except (ValueError, KeyError, OSError) as e: parser.exit(2, f'Error: {e}\n')

if __name__ == '__main__': main()
