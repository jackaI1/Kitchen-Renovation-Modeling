# cpm-schedule-xer

I built a construction schedule calculator to learn how the underlying idea works. This is a learning project.

## Try it

Python 3.9 or newer is enough to run the tool. From this folder:

```sh
python3 cpm.py examples/building.xer --gantt gantt.html --output scheduled.xer
```

The terminal lists early finish, float in working hours, and critical activities. Open `gantt.html` in a browser; red bars have zero or negative float. The synthetic example follows excavation, concrete, electrical work, framing, and finishes. To compare against a deadline, add `--deadline "2026-01-13 16:00"`; negative float is reported as `LATE`.

To record progress and move the data date (the point from which remaining work is planned):

```sh
python3 cpm.py examples/building.xer --data-date "2026-01-07 08:00" --progress examples/progress.json --output updated.xer --gantt updated.html
```

The JSON file maps XER task IDs to actual start, optional actual finish, physical percent complete, and remaining working hours. Use the IDs printed in the report. For a finished activity, provide both actual dates and zero remaining hours. Percent complete is recorded independently; it does not automatically change remaining duration. Keep the original export and review the result before importing it into P6.

## How it works

The reader retains XER tables and fields it does not calculate, including calendar and relationship records. Each activity uses its assigned calendar's weekly shifts and dated exceptions. The forward pass finds the earliest dates allowed by each relationship; the backward pass works from the project finish or the optional deadline to find late dates and float. Finish-to-start (FS), start-to-start (SS), and finish-to-finish (FF) links support positive and negative lags. Lag uses the successor's calendar. Remaining work is scheduled from the data date; actual starts anchor SS relationships and completed work retains its actual dates.

This implementation expects one project and activity calendars with P6 `DaysOfWeek` and `Exceptions` records, or an empty calendar definition for a standard Monday to Friday, 08:00 to 16:00 week. It rejects cycles, missing relationship endpoints, SF links, level-of-effort and WBS summary activities. It does not model constraints, resource leveling, inherited calendars, P6 scheduling options, or all progress and out-of-sequence rules. The XER writer preserves other tables but has not been validated by importing every possible export into P6. Compare results with P6 before relying on them for a real project.

## Tests and limits

There are 1 test source files in this copy. No test pass count is claimed here: I have not re-run the project suite as part of this move. This is a source snapshot, and running it on a new machine may need environment-specific setup.


Project checks run from this directory through the path-filtered hub workflows: `cpm-schedule-xer-ci.yml`.
