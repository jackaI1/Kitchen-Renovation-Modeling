import csv
import math
from dataclasses import dataclass

@dataclass
class Task:
    id: str
    name: str
    duration: int
    dependencies: list
    budget: float
    actual: float
    progress: float = 0


def load_tasks(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = csv.DictReader(f)
        tasks = []
        for row in rows:
            try:
                task = Task(row['id'].strip(), row['name'].strip(), int(row['duration_days']),
                            [x.strip() for x in row['dependencies'].split(';') if x.strip()],
                            float(row['budget']), float(row['actual_cost']), float(row['progress']))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f'Invalid task row: {row}') from exc
            if not task.id or not task.name or task.duration < 1 or not all(math.isfinite(x) for x in (task.budget, task.actual, task.progress)) or task.budget < 0 or task.actual < 0 or not 0 <= task.progress <= 1:
                raise ValueError(f'Invalid task values: {task.id}')
            tasks.append(task)
    if not tasks:
        raise ValueError('Task list is empty')
    return tasks


def schedule(tasks):
    by_id = {t.id: t for t in tasks}
    if len(by_id) != len(tasks):
        raise ValueError('Duplicate task ID')
    result, visiting = {}, set()
    def visit(t):
        if t.id in visiting:
            raise ValueError('Dependency cycle detected')
        if t.id in result:
            return
        visiting.add(t.id)
        for dep in t.dependencies:
            if dep not in by_id:
                raise ValueError(f'Unknown dependency {dep}')
            visit(by_id[dep])
        start = max((result[d]['finish'] for d in t.dependencies), default=0)
        result[t.id] = {'start': start, 'finish': start + t.duration}
        visiting.remove(t.id)
    for task in tasks:
        visit(task)
    end = max((r['finish'] for r in result.values()), default=0)
    for task_id in reversed(list(result)):
        successors = [t.id for t in tasks if task_id in t.dependencies]
        latest_finish = min((result[s]['latest_start'] for s in successors), default=end)
        result[task_id]['latest_start'] = latest_finish - by_id[task_id].duration
        result[task_id]['float'] = result[task_id]['latest_start'] - result[task_id]['start']
    return result


def cost_metrics(budget, actual, progress):
    earned = budget * progress
    return {'earned': earned, 'variance': earned - actual,
            'forecast': budget * actual / earned if earned else None}
