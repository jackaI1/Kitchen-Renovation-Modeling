from datetime import datetime, timedelta, time
from html import escape
from xml.etree import ElementTree as ET
from openpyxl import Workbook
from openpyxl.styles import Font


def workday(start, offset):
    day = start
    while day.weekday() >= 5:
        day += timedelta(days=1)
    while offset:
        day += timedelta(days=1)
        if day.weekday() < 5:
            offset -= 1
    return day


def gantt(tasks, timings, path):
    width = max(r['finish'] for r in timings.values()) * 40 + 250
    height = 55 + len(tasks) * 32
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', '<rect width="100%" height="100%" fill="white"/>', '<text x="10" y="22" font-family="sans-serif" font-size="15">Task (red = critical)</text>']
    for i, task in enumerate(tasks):
        r = timings[task.id]; y = 40 + i * 32
        color = '#c33' if r['float'] == 0 else '#2876a8'
        parts += [f'<text x="10" y="{y+14}" font-family="sans-serif" font-size="12">{escape(task.id)}: {escape(task.name)}</text>', f'<rect x="{220+r["start"]*40}" y="{y}" width="{task.duration*40}" height="20" fill="{color}"/>', f'<text x="{225+r["start"]*40}" y="{y+14}" fill="white" font-family="sans-serif" font-size="11">{task.duration}d</text>']
    parts.append('</svg>')
    path.write_text('\n'.join(parts), encoding='utf-8')


def workbook(tasks, timings, path):
    wb = Workbook(); ws = wb.active; ws.title = 'Variance'
    ws.append(['ID', 'Task', 'Budget', 'Actual', 'Progress', 'Earned value', 'Cost variance', 'Forecast at completion', 'Float (days)'])
    for i, task in enumerate(tasks, 2):
        ws.append([task.id, task.name, task.budget, task.actual, task.progress, f'=C{i}*E{i}', f'=F{i}-D{i}', f'=IF(F{i}=0,"",C{i}*D{i}/F{i})', timings[task.id]['float']])
        ws[f'E{i}'].number_format = '0%'
        for col in ('C','D','F','G','H'): ws[f'{col}{i}'].number_format = '#,##0.00'
    end = len(tasks) + 2
    ws.append(['Total', '', f'=SUM(C2:C{end-1})', f'=SUM(D2:D{end-1})', '', f'=SUM(F2:F{end-1})', f'=SUM(G2:G{end-1})', f'=IF(F{end}=0,"",C{end}*D{end}/F{end})'])
    for cell in ws[1]: cell.font = Font(bold=True)
    ws.freeze_panes = 'C2'; ws.auto_filter.ref = f'A1:I{end-1}'
    for col, size in {'A':15,'B':30,'C':15,'D':15,'E':12,'F':18,'G':18,'H':25,'I':15}.items(): ws.column_dimensions[col].width = size
    wb.save(path)


def project_xml(tasks, timings, start, path):
    ns = 'http://schemas.microsoft.com/project'; ET.register_namespace('', ns)
    root = ET.Element(f'{{{ns}}}Project')
    def add(parent, name, value): ET.SubElement(parent, f'{{{ns}}}{name}').text = str(value)
    add(root, 'Name', 'Project delivery tracker'); add(root, 'ScheduleFromStart', 1)
    start = workday(start, 0)
    add(root, 'StartDate', datetime.combine(start, time(8)).isoformat()); add(root, 'MinutesPerDay', 480); add(root, 'MinutesPerWeek', 2400); add(root, 'DaysPerMonth', 20)
    calendars = ET.SubElement(root, f'{{{ns}}}Calendars'); cal = ET.SubElement(calendars, f'{{{ns}}}Calendar')
    for k,v in [('UID',1),('Name','Standard'),('IsBaseCalendar',1)]: add(cal,k,v)
    weekdays = ET.SubElement(cal, f'{{{ns}}}WeekDays')
    for day in range(1,8):
        wd = ET.SubElement(weekdays, f'{{{ns}}}WeekDay'); add(wd,'DayType',day); add(wd,'DayWorking',int(day not in (1,7)))
        if day not in (1,7):
            times = ET.SubElement(wd, f'{{{ns}}}WorkingTimes')
            for a,b in [('08:00:00','12:00:00'),('13:00:00','17:00:00')]:
                wt = ET.SubElement(times, f'{{{ns}}}WorkingTime'); add(wt,'FromTime',a); add(wt,'ToTime',b)
    add(root,'CalendarUID',1)
    collection = ET.SubElement(root, f'{{{ns}}}Tasks'); ids = {t.id:i for i,t in enumerate(tasks,1)}
    for task in tasks:
        node = ET.SubElement(collection, f'{{{ns}}}Task'); r = timings[task.id]
        fields = [('UID',ids[task.id]),('ID',ids[task.id]),('Name',task.name),('Type',0),('IsNull',0),('WBS',str(ids[task.id])),('OutlineLevel',1),('Priority',500),('Start',datetime.combine(workday(start,r['start']),time(8)).isoformat()),('Finish',datetime.combine(workday(start,r['finish']-1),time(17)).isoformat()),('Duration',f'PT{task.duration*8}H0M0S'),('DurationFormat',7),('PercentComplete',round(task.progress*100)),('Cost',task.budget),('ActualCost',task.actual),('Critical',int(r['float']==0))]
        for k,v in fields: add(node,k,v)
        for dep in task.dependencies:
            link = ET.SubElement(node, f'{{{ns}}}PredecessorLink'); add(link,'PredecessorUID',ids[dep]); add(link,'Type',1)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
