from datetime import datetime
from cpm import Calendar, Schedule, Task, Link

D = datetime.fromisoformat

def test_hand_computed_parallel_paths():
    cal = Calendar.standard()
    tasks = [Task('A', 'Foundation', 16, cal), Task('B', 'Frame', 24, cal), Task('C', 'Electrical', 8, cal), Task('D', 'Finish', 8, cal)]
    s = Schedule(tasks, [Link('A','B','FS',0), Link('A','C','FS',0), Link('B','D','FS',0), Link('C','D','FS',0)], D('2026-01-05 08:00'))
    s.calculate()
    assert tasks[3].early_finish == D('2026-01-12 16:00')
    assert [t.id for t in tasks if t.float_hours == 0] == ['A','B','D']
    assert tasks[2].float_hours == 16

def test_ss_and_ff_with_lags():
    c = Calendar.standard()
    a,b,c_task = [Task('A','A',24,c), Task('B','B',8,c), Task('C','C',8,c)]
    s = Schedule([a,b,c_task], [Link('A','B','SS',8), Link('A','C','FF',8)], D('2026-01-05 08:00')).calculate()
    assert b.early_finish == D('2026-01-06 16:00')
    assert c_task.early_finish == D('2026-01-08 16:00')
    assert a.float_hours == 0 and c_task.float_hours == 0
    assert b.float_hours == 16

def test_calendar_exception_and_split_shift():
    from datetime import date, time
    c = Calendar({i:[(time(8),time(12)),(time(13),time(17))] for i in range(5)}, {date(2026,1,6):[]})
    assert c.move(D('2026-01-05 08:00'), 16) == D('2026-01-07 17:00')
    assert c.move(D('2026-01-07 17:00'), -16) == D('2026-01-05 08:00')

def test_xer_round_trip_progress_and_preservation(tmp_path):
    from cpm import Xer
    x = Xer('examples/building.xer'); s = x.model()
    s.data_date = D('2026-01-07 08:00')
    t = s.tasks[0]; t.actual_start = D('2026-01-05 08:00'); t.actual_finish = D('2026-01-06 16:00'); t.percent = 100; t.duration = 0
    s.calculate(); x.apply(s); output = tmp_path/'updated.xer'; x.write(output)
    y = Xer(output); updated = y.model()
    assert updated.data_date == s.data_date
    assert updated.tasks[0].actual_finish == t.actual_finish
    assert updated.tasks[0].duration == 0
    assert y.rows('CALENDAR') == x.rows('CALENDAR')
    assert y.rows('TASKPRED') == x.rows('TASKPRED')
    assert updated.calculate().tasks[-1].early_finish == D('2026-01-14 16:00')

def test_cycle_and_unknown_relationship_rejected():
    import pytest
    c=Calendar.standard(); tasks=[Task('A','A',8,c),Task('B','B',8,c)]
    with pytest.raises(ValueError, match='cycle'):
        Schedule(tasks,[Link('A','B','FS',0),Link('B','A','FS',0)],D('2026-01-05 08:00')).calculate()
    with pytest.raises(ValueError, match='Unsupported relationship'):
        Schedule(tasks,[Link('A','B','SF',0)],D('2026-01-05 08:00')).calculate()

def test_calendar_nested_week_and_holiday():
    from datetime import date
    from cpm import Xer
    x=Xer('examples/building.xer'); data=x.rows('CALENDAR')[0]['clndr_data']
    data=data.replace('(0||Exceptions()())','(0||Exceptions()((0||0(d|46028)())))')
    cal=Calendar.parse(data)
    assert cal.intervals(date(2026,1,6)) == []
    assert cal.move(D('2026-01-05 08:00'),16) == D('2026-01-07 16:00')

def test_deadline_reports_negative_float():
    c=Calendar.standard(); a=Task('A','A',16,c)
    s=Schedule([a],[],D('2026-01-05 08:00'))
    s.deadline=D('2026-01-05 16:00'); s.calculate()
    assert a.float_hours == -8

def test_started_predecessor_ss_uses_actual_start():
    c=Calendar.standard()
    a=Task('A','A',16,c,actual_start=D('2026-01-05 08:00'))
    b=Task('B','B',8,c)
    Schedule([a,b],[Link('A','B','SS',8)],D('2026-01-07 08:00')).calculate()
    assert b.early_start == D('2026-01-07 08:00')
