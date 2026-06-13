# U of T Econ Seminar Calendar
This repository contains a Python script that scrapes the University of Toronto Economics Department's seminar calendar and updates an .ics file with seminars. 

The script is designed to be run on a daily via GitHub Actions, which will automatically update the calendar with any new seminars.

## Usage
On Google Calendar (or your calendar app of choice), add a new calendar by URL and use the raw .ics file from this repository:
```
https://raw.githubusercontent.com/eschryver/seminarcal/main/seminars.ics
```
It's that simple. The calendar will automatically update every day (or so) with any new seminars added.