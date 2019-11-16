from pathlib import Path
import sys

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
