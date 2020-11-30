from pathlib import Path
import sys
import textwrap

import pytz

# Stanford Theatre base url
THEATER_BASEURL = r"http://www.stanfordtheatre.org/"

# How many characters to limit plot descriptions to in entries
MAX_PLOT_LEN = 800

# Stanford Theatre is in the same timezone as Los Angeles
THEATER_TZ = pytz.timezone("America/Los_Angeles")

# where the configuration file is
CONFIG_DIR = Path.home() / ".config" / "movies2ical"
CONFIG_FILE = CONFIG_DIR / "config.toml"

# where to store cached imdb json files and stanford movie html files
CACHE_ROOT_DIR = Path.home() / ".cache" / "movies2ical"

# where to store cached json files for imdb movie data we fetch
IMDB_CACHE_DIR = CACHE_ROOT_DIR / "imdb_cache"

# where to put output .ics files
ICAL_OUT_DIR = Path(".")

# where to store cached stanford theater htmls files
THEATER_CACHE_DIR = CACHE_ROOT_DIR / "stanford_movie_cache"

# months in order to convert to/from numbers
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
MONTHS.extend(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)

IS_TTY = sys.stdout.isatty()

DEFAULT_PLIST_INFO = {
    "Label": "local.CheckStanfordMovies",
    "ProgramArguments": [
        "/usr/local/bin/python3",
        "/INSERT/FULL/PATH/TO/movies2ical.py",
        "--correct_times",
    ],
    "WorkingDirectory": "/INSERT/FULL/PATH/TO/Stanford Theatre Calendars/",
    "StandardOutPath": "/INSERT/FULL/PATH/TO/stanford_out.txt",
    "StandardErrorPath": "/INSERT/FULL/PATH/TO/stanford_err.txt",
    "StartCalendarInterval": [
        {"Hour": 3, "Minute": 0, "Weekday": 0},
        {"Hour": 3, "Minute": 0, "Weekday": 2},
        {"Hour": 3, "Minute": 0, "Weekday": 4},
    ],
}

DEFAULT_CONFIG_TOML_STR = textwrap.dedent(
    """
    # Information for movies2ical

    [notify17]
        new_calendar_url = "https://hook.notify17.net/api/template/<your-template-specifier>"
        error_url = "https://hook.notify17.net/api/template/<your-template-specifier>"

    [plist]
        ProgramArguments = [
            "/path/to/python3",
            "/path/to/movies2ical.py",
            "--correct_times",
            "--notify"
        ]
        WorkingDirectory = "/directory/to/output/calendars/"
        StandardOutPath = "/path/to/stanford_out.txt"
        StandardErrorPath = "/path/to/stanford_err.txt"
        # new [[plist.StartCalendarInterval]] for each new date/time to run command
        [[plist.StartCalendarInterval]]
        # Sunday 3:00am
        Hour = 3
        Minute = 0
        Weekday = 0
        [[plist.StartCalendarInterval]]
        # Tuesday 3:00am
        Hour = 3
        Minute = 0
        Weekday = 2
        [[plist.StartCalendarInterval]]
        # Thursday 3:00am
        Hour = 3
        Minute = 0
        Weekday = 4
    """
).strip()
