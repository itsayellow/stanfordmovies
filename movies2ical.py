#!/usr/bin/env python3

# TODO: incorporate shorts without their own times into main feature
#       description
# TODO: properly handle unicode in imdb data

import re
import sys
import argparse
import datetime
import json
from pathlib import Path
import urllib.request
import urllib.error
import urllib.parse

import bleach
from bs4 import BeautifulSoup, Tag
from icalendar import Calendar, Event
from imdb import IMDb
import pytz
from tzlocal import get_localzone


# Stanford Theatre base url
THEATER_BASEURL = r"http://www.stanfordtheatre.org/"

# How many characters to limit plot descriptions to in entries
MAX_PLOT_LEN = 800

# Stanford Theatre is in the same timezone as Los Angeles
THEATER_TZ = pytz.timezone('America/Los_Angeles')

# where to store cached imdb json files and stanford movie html files
CACHE_ROOT_DIR = Path(sys.argv[0]).absolute().parent

# where to store cached json files for imdb movie data we fetch
IMDB_CACHE_DIR = CACHE_ROOT_DIR / "imdb_cache"

# where to put output .ics files
ICAL_OUT_DIR = Path(".")

# where to store cached stanford theater htmls files
THEATER_CACHE_DIR = CACHE_ROOT_DIR / "stanford_movie_cache"

# months in order to convert to/from numbers
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
        "August", "September", "October", "November", "December"]

IS_TTY = sys.stdout.isatty()

def process_command_line(argv):
    """Process command line invocation arguments and switches.

    Args:
        argv: list of arguments, or `None` from ``sys.argv[1:]``.

    Returns:
        args: Namespace with named attributes of arguments and switches
    """
    #script_name = argv[0]
    argv = argv[1:]

    # initialize the parser object:
    parser = argparse.ArgumentParser(
            description="Fetch latest web calendar from the Stanford "\
                    "Theatre, and convert it to ical format, complete "
                    "with info from imdb.com")

    # specifying nargs= puts outputs of parser in list (even if nargs=1)

    # required arguments
    parser.add_argument('srcfile', nargs='*',
            help="Source directory (recursively searched)."
            )

    # switches/options:
    parser.add_argument(
        '-f', '--file', action='store_true',
        help='Parse files from arguments instead of going to '\
                'www.stanfordtheatre.org to find calendar.')
    parser.add_argument(
        '-c', '--correct_times', action='store_true',
        help='If runtime from imdb causes movie end time to overlap next '\
                'movie\'s scheduled start time, correct end time.')
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help='More verbose messages.')

    args = parser.parse_args(argv)

    return args


def process_movie_time_str(movie_time):
    # Eliminate text after "ticket sale"
    #   Usually is entry saying what time tickets go on sale, not movie time.
    movie_time = re.sub(r"ticket.+sale.+$", "", movie_time, re.I)
    # Check every string in parentheses.
    #   Can be extra time typically for sat and/or sun
    #   Can be random jibberish
    time_extra = None
    paren_re = re.search(r"\(([^)]*)\)", movie_time)
    while paren_re:
        paren_full = paren_re.group(1)
        time_extra_re = re.search(r"(\d+:\d\d)", paren_full)
        if time_extra_re:
            time_extra = time_extra_re.group(1)
            if re.search(r"sat", paren_full, re.I):
                time_extra += " sat"
            if re.search(r"sun", paren_full, re.I):
                time_extra += " sun"
        else:
            print("Warning: extra movie time "+paren_full+" is unparseable.")
        # remove extra string in parens
        movie_time = re.sub(re.escape(paren_re.group(0)), "", movie_time).strip()
        paren_re = re.search(r"\(([^)]*)\)", movie_time)

    # change all non-digit, non-: to single space character
    movie_time = re.sub(r"[^0-9:]+", " ", movie_time).strip()
    # convert times to list
    movie_times = movie_time.split(" ")
    # remove all non-time entries
    movie_times = [x for x in movie_times if re.search(r"\d:\d\d", x)]

    if time_extra:
        movie_times.append(time_extra)

    return movie_times


def parse_datestr(content_str, calendar_year):
    """
    Args:
        content_str (str): String from html calendar with human-readable date
            usually with month and date
        calendar_year (int): full 4-digit year of calendar

    Returns:
        tuple: (td_startdate, td_enddate)
            where td_*date is tuple: (year_int, month_int, date_int)
    """
    td_startdate = None
    td_enddate = None
    month_start_num = None

    # movie dates (possibly)
    # Searching for one of:
    #   July 18-19
    #   August 31-September 1
    #   December 24
    month_regexp = "(" + "|".join(MONTHS) + ")"
    onemonth_multdate_re = re.search(
            month_regexp + r"\s+(\d+)\s*-\s*(\d+)($|\D)",
            content_str
            )
    multmonth_multdate_re = re.search(
            month_regexp + r"\s+(\d+)\s*-\s*" + month_regexp + r"\s*(\d+)($|\D)",
            content_str
            )
    # note: will also match last date in multmonth_multdate_re
    onemonth_onedate_re = re.search(
            month_regexp + r"\s+(\d+)\s*($|[^-])",
            content_str
            )
    if onemonth_multdate_re:
        month_start_num = MONTHS.index(onemonth_multdate_re.group(1)) + 1
        date_start_num = int(onemonth_multdate_re.group(2))
        month_end_num = month_start_num
        date_end_num = int(onemonth_multdate_re.group(3))
    elif multmonth_multdate_re:
        month_start_num = MONTHS.index(multmonth_multdate_re.group(1)) + 1
        date_start_num = int(multmonth_multdate_re.group(2))
        month_end_num = MONTHS.index(multmonth_multdate_re.group(3)) + 1
        date_end_num = int(multmonth_multdate_re.group(4))
    elif onemonth_onedate_re:
        month_start_num = MONTHS.index(onemonth_onedate_re.group(1)) + 1
        date_start_num = int(onemonth_onedate_re.group(2))
        month_end_num = month_start_num
        date_end_num = date_start_num

    if month_start_num is not None:
        td_startdate = (calendar_year, month_start_num, date_start_num)
        td_enddate = (calendar_year, month_end_num, date_end_num)

    return(td_startdate, td_enddate)


def extract_playdate(td, calendar_year):
    # The easy way, if we find structured html <p class="date">
    p_date = td.find("p", class_="date")

    # if we find <p class="date"> and contents of tag has non-space char
    if p_date and re.search(r"\S", "".join(p_date.contents)):
        (td_startdate, td_enddate) = parse_datestr(p_date.contents[0], calendar_year)
    else:
        print("Warning: could not find date in:", file=sys.stderr)
        print(str(td)[:78], file=sys.stderr)
        (td_startdate, td_enddate) = (None, None)

    return (td_startdate, td_enddate)


def extract_movies_imdb(td):
    movies = []

    for link in td.find_all("a"):
        if re.search(r"https?://[^/]*imdb\.", link['href']):
            movie_text = "".join([str(x) for x in link.contents])
            movies.append([str(link), link['href'], movie_text])

    return movies


def parse_td(td, calendar_year, verbose=False):
    # init
    movies = []

    # extract all links to imdb movies and text they contain
    movie_list = extract_movies_imdb(td)
    # if this td has no imdb link contained in it, presume not a movie playdate
    #   and return immediately
    if not movie_list:
        return None

    # extract month, date for this playdate
    (td_startdate, td_enddate) = extract_playdate(td, calendar_year)

    # split text inside td on full movie link strings, yielding a list of
    #   strings in-between movie names/links.  These will contain times.
    movie_regexs = [re.escape(x[0]) for x in movie_list]
    td_splits = re.split(
            r"(?:" + "|".join(movie_regexs) + r")",
            "".join([str(x) for x in td.contents])
            )
    # replace many space-like characters in a row with one space for all strings
    td_splits = [re.sub(r"\s+", " ", x) for x in td_splits]

    # len(td_splits) = len(movie_list) + 1
    # td_splits consists of a list of all text preceding/following movie link
    #   strings
    # movie_times for a movie will be in following td_split item
    for (i, movie) in enumerate(movie_list):
        # remove all tags to get text
        movie_name = bleach.clean(movie[2].strip(), tags=[], strip=True)
        imdb_link = movie[1].strip()
        time_str = bleach.clean(td_splits[i+1].strip(), tags=[], strip=True)

        # if (movieyear) string is after link and ends up in time_str,
        #   cut it out and append it to movie_name
        movieyear_moviename_re = re.search(r"\(\D*\d{4}\D*\)\s*$", movie_name)
        movieyear_timestr_re =re.search(r"^\s*(\(\D*\d{4}\D*\))", time_str)
        if not movieyear_moviename_re and movieyear_timestr_re:
            movieyear_str = movieyear_timestr_re.group(1)
            movie_name = movie_name + " " + movieyear_str
            time_str = re.sub(re.escape(movieyear_str), "", time_str).strip()

        # clean up movie times and parse to list
        movie_times = process_movie_time_str(time_str)

        if movie_times:
            # append to movies for this date if we have at least one valid time
            movies.append((movie_name, imdb_link, movie_times))

    if td_startdate is not None and movies:
        movie_return = []
        for movie in movies:
            (movie_name, imdb_link, movie_times) = movie
            movie_return.append(
                    {
                        'name':movie_name,
                        'imdb_url':imdb_link,
                        'show_startdate':td_startdate,
                        'show_enddate':td_enddate,
                        'show_times':movie_times,
                        }
                    )
        return movie_return
    else:
        return None


#def parse_td(td, calendar_year, verbose=False):
#    td_str = str(td)
#    td_startdate = None
#    td_enddate = None
#    movies = []
#
#    # this should work, but sometimes a class='playdate' has garbage
#    #if "playdate" in td['class']:
#
#    # seems every valid movie td has "imdb" inside of it
#    if "imdb" in td_str:
#        # Weird Stuff That Can Happen
#        #   <a href="..">movie_name</a> (year) instead of
#        #       <a href="..">movie_name (year)</a>
#        #   time can be in the next <p>
#        #   "movie_name (UK version 1940)" instead of
#        #       "movie_name (1940)"
#        #   "movie_name (<em>alt movie name</em>, 1940)" instead of
#        #       "movie_name (1940)"
#        for para in td.find_all("p"):
#            movie_name = None
#            imdb_link = None
#            movie_time = None
#            found_lone_year = False
#
#            for content in para.contents:
#                if isinstance(content, Tag) and content.name == 'a':
#                    # link (presumably to imdb for movie) and movie
#                    imdb_link = content['href']
#                    movie_name = content.get_text()
#                    if not re.search(r"\(\D*\d{4}\)", movie_name):
#                        # search the rest of the paragraph for a year
#                        year_re = re.search(r"\(\D*\d{4}\)", para.get_text())
#                        if year_re:
#                            movie_name = movie_name + " " + year_re.group(0)
#                            found_lone_year = True
#
#                elif isinstance(content, str) and re.search(r"\d:\d\d", content):
#                    # movie times
#                    movie_time = str(content).strip()
#
#                elif isinstance(content, str) and td_startdate is None:
#                    # movie dates (possibly)
#                    # Searching for one of:
#                    #   July 18-19
#                    #   August 31-September 1
#                    #   December 24
#                    (td_startdate, td_enddate) = parse_datestr(content, calendar_year)
#                elif isinstance(content, Tag) and content.name == 'br':
#                    # ignore line break tags </br>
#                    pass
#
#                elif isinstance(content, str) and re.search(r"^\s*$", content):
#                    # ignore whitespace or empty string
#                    pass
#
#                elif found_lone_year and re.search(r"^\s*\(\D*\d{4}\D*\)\s*$", content):
#                    # ignore year in parens in content if we had to find it
#                    #   before for previous movie content
#                    pass
#
#                else:
#                    # unknown (usually random chatter)
#                    if verbose:
#                        print("Unparsed string:\n    '" + str(content) + "'")
#
#            if imdb_link is not None:
#                # we got a movie in this para, so add movie to list
#                if movie_time is None:
#                    # check to see if time is in next paragraph(s)
#                    for sib in para.next_siblings:
#                        if isinstance(sib, Tag) and sib.name == 'p':
#                            if sib.find_all('a'):
#                                # next movie, so stop looking for time for this
#                                #   movie's times
#                                break
#                            sib_text = sib.get_text()
#                            if re.search(r"\d:\d\d", sib_text):
#                                movie_time = sib_text.strip()
#                                break
#
#                if movie_time is not None:
#                    # clean up movie times
#                    movie_times = process_movie_time_str(movie_time)
#
#                    # append to movies for this date
#                    movies.append((movie_name, imdb_link, movie_times))
#
#    if td_startdate is not None:
#        movie_return = []
#        for movie in movies:
#            (movie_name, imdb_link, movie_times) = movie
#            movie_return.append(
#                    {
#                        'name':movie_name.strip(),
#                        'imdb_url':imdb_link,
#                        'show_startdate':td_startdate,
#                        'show_enddate':td_enddate,
#                        'show_times':movie_times,
#                        }
#                    )
#        return movie_return
#    else:
#        return None


def fetch_imdb_info_cache(imdb_movie_num, movie_name):
    imdb_cache_filename = str(IMDB_CACHE_DIR / imdb_movie_num) + ".json"

    try:
        with open(imdb_cache_filename, 'r') as imdb_cache_fh:
            imdb_movie = json.load(imdb_cache_fh)
    except (FileNotFoundError, PermissionError):
        # only do a CR progress-display if we are in a terminal (not directed
        #   to a file)
        if sys.stdout.isatty():
            print("\r", end="")
        else:
            print("\n", end="")
        print("Fetching info: " + movie_name + " "*(60-len(movie_name)), end="")

        ia = IMDb()
        imdb_movie_web = ia.get_movie(imdb_movie_num, info=['main', 'plot'])

        imdb_movie = {}
        imdb_movie['title'] = str(imdb_movie_web['title'])
        imdb_movie['director'] = [str(x) for x in imdb_movie_web['director']]
        imdb_movie['writer'] = [str(x) for x in imdb_movie_web['writer']]
        imdb_movie['cast'] = [str(x) for x in imdb_movie_web['cast']]
        imdb_movie['runtimes'] = [str(x) for x in imdb_movie_web['runtimes']]
        try:
            imdb_movie['plot'] = [str(x) for x in imdb_movie_web['plot']]
        except KeyError:
            # no plot in imdb info
            imdb_movie['plot'] = ["",]
        imdb_movie['year'] = int(imdb_movie_web['year'])
        imdb_movie['rating'] = float(imdb_movie_web['rating'])

        try:
            with open(imdb_cache_filename, 'w') as imdb_cache_fh:
                json.dump(imdb_movie, imdb_cache_fh)
        except (IsADirectoryError, PermissionError) as err:
            print("Can't write to imdb_cache dir")
    except Exception as err:
        print("Can't load: " + imdb_cache_filename)
        print(type(err))
        print(err)

    return imdb_movie


def get_imdb_info(play_dates):
    for play_date in play_dates:
        imdb_mnum_re = re.search(r"\/tt(\d+)", play_date['imdb_url'])
        if imdb_mnum_re:
            imdb_movie_num = imdb_mnum_re.group(1)

        imdb_movie = fetch_imdb_info_cache(imdb_movie_num, play_date['name'])

        play_date['imdb_info'] = {}
        play_date['imdb_info']['title'] = imdb_movie['title']
        play_date['imdb_info']['director'] = imdb_movie['director']
        play_date['imdb_info']['writer'] = imdb_movie['writer']
        play_date['imdb_info']['cast'] = imdb_movie['cast']
        play_date['imdb_info']['runtimes'] = imdb_movie['runtimes']
        play_date['imdb_info']['plot'] = imdb_movie['plot']
        play_date['imdb_info']['year'] = imdb_movie['year']
        play_date['imdb_info']['rating'] = imdb_movie['rating']

    # blank out last "Fetching data" line if we're in a terminal, else just \n
    if sys.stdout.isatty():
        print("\r" + " "*78)
    else:
        print("\n", end="")


def persons_list_print(person_list):
    persons = []
    out_str = ""
    for person in person_list:
        if person not in persons:
            persons.append(person)
    if len(persons) < 2:
        out_str += ": "
        out_str += persons[0]
    else:
        out_str += "s: "
        for (i, person) in enumerate(persons):
            if i > 0:
                out_str += ", "
            out_str += person

    return out_str


def movie_synopsis(play_date):
    out_str = ""

    plot = re.sub(r"::.*$", "", play_date['imdb_info']['plot'][-1])
    # cut off plot descriptions that are too long
    if len(plot) > MAX_PLOT_LEN:
        plot = plot[:MAX_PLOT_LEN]
        # end plot string at end of word, add elipsis
        plot = re.sub(r"\s+\S*$", "", plot) + "..."
    out_str += play_date['imdb_url']
    out_str += "\n\n"
    out_str += plot
    out_str += "\n\n"
    out_str += "Director" + persons_list_print(play_date['imdb_info']['director'])
    out_str += "\n"
    out_str += "Writer" + persons_list_print(play_date['imdb_info']['writer'])
    out_str += "\n\n"
    out_str += "Cast:\n"
    for cast_member in play_date['imdb_info']['cast'][:10]:
        out_str += cast_member + "\n"

    return out_str


def report_playdates(play_dates):
    """Debug function to print out a text representation of play dates
    """
    for play_date in play_dates:
        print("-"*78)
        print(play_date['name'])
        print(play_date['show_startdate'][0], end="")
        print(" ", end="")
        print(MONTHS[play_date['show_startdate'][1] - 1], end="")
        print(" " + str(play_date['show_startdate'][2]), end="")
        print(" - ", end="")
        print(play_date['show_enddate'][0], end="")
        print(" ", end="")
        print(MONTHS[play_date['show_enddate'][1] - 1], end="")
        print(" " + str(play_date['show_enddate'][2]))
        print(play_date['show_times'])
        print("Runtimes: " + str(play_date['imdb_info']['runtimes']))
        print("")

        print(movie_synopsis(play_date))


def compute_datetimes(play_dates):
    for play_date in play_dates:
        # TODO: check for other runtimes instead of just using first one
        runtime = int(play_date['imdb_info']['runtimes'][0])
        play_date_start = datetime.date(*play_date['show_startdate'])
        play_date_end = datetime.date(*play_date['show_enddate'])

        play_date['showings'] = []

        for show_time in play_date['show_times']:
            if " " not in show_time:
                # normal showtime every day in range
                this_time = show_time
                this_play_date_start = play_date_start
                this_play_date_end = play_date_end
            else:
                # showtimes only on saturday and/or sunday

                # get weekday (e.g. Monday, Tuesday, etc.) number of
                #   play_date_start.  Monday=0, Tuesday=1, etc.
                weekday_start = play_date_start.weekday()

                # figure out play_date start and end based on sat and/or sun
                this_play_date_start = None
                this_play_date_end = None
                if "sat" in show_time:
                    # set this_play_date_start to saturday (weekday=5) after
                    #   play_date_start
                    this_play_date_start = play_date_start + \
                            datetime.timedelta(days=5-weekday_start)
                if "sun" in show_time:
                    # set this_play_date_end to sunday (weekday=6) after
                    #   play_date_start
                    this_play_date_end = play_date_start + \
                            datetime.timedelta(days=6-weekday_start)
                if not this_play_date_start:
                    this_play_date_start = this_play_date_end
                if not this_play_date_end:
                    this_play_date_end = this_play_date_start

                this_time = show_time.split(" ")[0]

            # process times, dates
            (hour, minute) = this_time.split(":")
            # assume all times are PM, so add 12 to time
            hour = int(hour) + 12
            minute = int(minute)

            # DON'T USE tzinfo!  USE pytz.timezone.localize()
            #   for some reason using tzinfo with datetime.combine
            #   gives a strange timezone (-07:53)
            datetime_start = datetime.datetime.combine(
                    this_play_date_start,
                    datetime.time(hour, minute, 0)
                    )
            # put extracted time in THEATER timezone
            datetime_start = THEATER_TZ.localize(datetime_start)
            # Convert to UTC timezone
            datetime_start = datetime_start.astimezone(pytz.utc)

            datetime_end = datetime_start + datetime.timedelta(minutes=runtime)
            # rrule_count is how many days including this one
            rrule_count = (this_play_date_end - this_play_date_start).days + 1

            play_date['showings'].append(
                    {
                        'datetime_start':datetime_start,
                        'datetime_end':datetime_end,
                        'rrule_count':rrule_count,
                        }
                    )


def gen_ical(play_dates, ical_filename='test.ics'):
    cal = Calendar()
    cal.add('prodid', '-//Stanford Theatre Calendar//itsayellow@gmail.com//')
    cal.add('version', '3.0')
    location = "221 University Ave, Palo Alto, CA (Stanford Theatre)"

    for play_date in play_dates:
        for showing in play_date['showings']:
            datetime_start = showing['datetime_start']
            datetime_end = showing['datetime_end']
            rrule_count = showing['rrule_count']

            # unique uid for each event
            uid = datetime_start.strftime('%Y%m%dT%H%M%S%Z')
            uid += '@itsayellow.com'

            # assemble event and add to calendar
            event = Event()
            event.add('dtstart', datetime_start)
            event.add('dtend', datetime_end)
            event.add('dtstamp', datetime_start)
            event.add('uid', uid)
            if rrule_count > 1:
                event.add('rrule', {'FREQ':'DAILY', 'COUNT':rrule_count})
            event.add('summary', play_date['name'])
            event.add('url', play_date['imdb_url'])
            event.add('description', movie_synopsis(play_date))
            event.add('location', location)
            cal.add_component(event)

    # icalendar writes out bytes, so use 'wb'
    try:
        with open(ical_filename, 'wb') as ical_fh:
            ical_fh.write(cal.to_ical())
    except (IsADirectoryError, PermissionError) as err:
        print("Can't write: " + str(ical_filename))
        print(type(err))
        print(err)
    else:
        print("\nWrote: " + str(ical_filename))


def check_name_year_consistency(play_dates):
    # check if stanford theatre name & year doesn't match imdb name & year
    for play_date in play_dates:
        stan_name = play_date['name']
        imdb_name = play_date['imdb_info']['title']
        imdb_year = play_date['imdb_info']['year']

        stan_year_re = re.search(r"\(.*(19\d\d).*\)", stan_name)
        if stan_year_re:
            stan_year = int(stan_year_re.group(1))
        else:
            stan_year = -1
        stan_name = re.sub(r"\s*\([^)]*\)\s*$", "", stan_name)

        # lower-case compared strings
        stan_name_cmp = stan_name.lower()
        imdb_name_cmp = imdb_name.lower()
        # ignore all double-quotes
        stan_name_cmp = re.sub(r'"', '', stan_name_cmp)
        imdb_name_cmp = re.sub(r'"', '', imdb_name_cmp)
        # ignore beginning "the"
        stan_name_cmp = re.sub(r"the\s+", "", stan_name_cmp, re.I)
        imdb_name_cmp = re.sub(r"the\s+", "", imdb_name_cmp, re.I)

        show_date_str = MONTHS[play_date['showings'][0]['datetime_start'].month - 1] + \
                " %d"%play_date['showings'][0]['datetime_start'].day
        if stan_name_cmp != imdb_name_cmp:
            print("%s, Warning, inconsistent title:"%show_date_str)
            print("    Stanford Theatre: " + stan_name)
            print("                IMDb: " + imdb_name)
        if stan_year != imdb_year:
            print("%s, Warning, inconsistent year:"%show_date_str)
            print("    Stanford Theatre: %s (%d)"%(stan_name, stan_year))
            print("                IMDb: %s (%d)"%(imdb_name, imdb_year))


def check_schedule_overlap(play_dates, correct_endtimes=False):
    # check for schedule overlaps (movie 1 ends after movie 2 begins, and
    #   before movie 2 ends)
    # O(n!)
    for (i, play_date1) in enumerate(play_dates):
        for play_date2 in play_dates[i+1:]:
            for showing1 in play_date1['showings']:
                for showing2 in play_date2['showings']:
                    show_start_name = None

                    if showing1['datetime_start'] < showing2['datetime_start'] < showing1['datetime_end']:
                        show_end_name = play_date1['name']
                        show_end_time = showing1['datetime_end']
                        show_start_name = play_date2['name']
                        show_start_time = showing2['datetime_start']
                        if correct_endtimes:
                            showing1['datetime_end'] = showing2['datetime_start'] - \
                                    datetime.timedelta(minutes=1)
                    if showing2['datetime_start'] < showing1['datetime_start'] < showing2['datetime_end']:
                        show_end_name = play_date2['name']
                        show_end_time = showing2['datetime_end']
                        show_start_name = play_date1['name']
                        show_start_time = showing1['datetime_start']
                        if correct_endtimes:
                            showing2['datetime_end'] = showing1['datetime_start'] - \
                                    datetime.timedelta(minutes=1)

                    if show_start_name:
                        show_end_time = show_end_time.astimezone(THEATER_TZ)
                        show_end_time_str = show_end_time.strftime('%I:%M%p %Z')
                        show_start_time = show_start_time.astimezone(THEATER_TZ)
                        show_start_time_str = show_start_time.strftime('%I:%M%p %Z')
                        show_date_str = MONTHS[show_start_time.month - 1] + \
                                " %d"%show_start_time.day
                        if correct_endtimes:
                            print("AUTOCORRECTING TO FIX:")
                        print("%s, Movie time conflict between:"%show_date_str)
                        print("    " + show_end_name + " (Ends at %s)"%show_end_time_str)
                        print("    " + show_start_name + " (Starts at %s)"%show_start_time_str)


def check_empty_schedule(play_dates):
    if not play_dates:
        print("Warning, no movies or showtimes found")


def check_for_problems(play_dates, correct_endtimes=False):
    # check if empty schedule
    check_empty_schedule(play_dates)

    # check if stanford theatre name & year doesn't match imdb name & year
    check_name_year_consistency(play_dates)

    # check for schedule overlaps (movie 1 ends after movie 2 begins, and
    #   before movie 2 ends)
    check_schedule_overlap(play_dates, correct_endtimes=correct_endtimes)


def parse_html_calendar(html_file, verbose=False):
    # start by assuming calendar is in current year
    calendar_year = datetime.date.today().year

    # most of the time Stanford Theatre doesn't put year in filename or in
    #   html.  But we will add year to end of stored test calendar html files
    cal_year_re = re.search(r"_(20\d\d)(\d{4})?($|\.)", str(Path(html_file).stem))
    if cal_year_re:
        calendar_year = int(cal_year_re.group(1))
    print("Calendar Year: %d"%calendar_year)

    with open(html_file, 'rb') as html_fh:
        html_bin = html_fh.read()

    # weird characters used in stanford movies:
    # hex 96: en-dash

    # bad html seen:
    #   sometimes </tr> with no starting <tr>
    #   sometimes <td> with no closing </td>

    # bare bones html parse, keeps all weirdness from stanfordtheatre html
    #soup = BeautifulSoup(html_bin, 'html.parser')

    # html5lib parse outputs valid html from broken stanfordtheatre html!
    #   a little slower but worth it
    soup = BeautifulSoup(html_bin, 'html5lib')

    tables = soup.find_all('table')

    assert len(tables) == 1

    # search only for td, because sometimes bad html has no <tr> start tag!
    #   (but html5lib should clean this up and add a <tr>)
    play_dates = []
    for td in tables[0].find_all('td'):
        td_play_dates = parse_td(td, calendar_year, verbose=verbose)
        #td_play_dates = parse_td(td, calendar_year, verbose=verbose)

        if td_play_dates is not None:
            play_dates.extend(td_play_dates)

    return play_dates


def lastmod_datetime(last_mod_str):
    """Extract valid UTC datetime from Last-Modified str
    """
    last_mod_re = re.search(
            r",\s*(\d+\s+\S+\s+\d+\s+\d+:\d+:\d+)\s*(\S+)",
            last_mod_str
            )
    if last_mod_re:
        last_mod_strp = last_mod_re.group(1)
        tz = last_mod_re.group(2)

        last_mod_tz = pytz.timezone(tz)
        last_mod_datetime = datetime.datetime.strptime(
                last_mod_strp,
                "%d %b %Y %H:%M:%S"
                )
        last_mod_datetime = last_mod_tz.localize(last_mod_datetime)
        last_mod_datetime = last_mod_datetime.astimezone(pytz.utc)
    else:
        last_mod_datetime = None

    return last_mod_datetime


def fetch_url(url, newer_than_date=None):
    """Fetch url and return html, optionally don't if not newer than date
    """
    # Any user_agent string EXCEPT 'Python-urllib' will work! (even empty)
    # 'Python-urllib' in string yields a HTTP Error 403: Forbidden
    user_agent = 'Mozilla/5.0'
    headers = {'User-Agent':user_agent}
    request = urllib.request.Request(url, headers=headers)
    html = None
    info = None
    try:
        response = urllib.request.urlopen(request)
    except urllib.error.URLError as err:
        if hasattr(err, 'code'):
            print(err.code)
        else:
            print(err.reason)
    else:
        info = response.info()
        if newer_than_date is not None:
            if info.get('Last-Modified', None):
                last_mod_datetime = lastmod_datetime(info['Last-Modified'])
            else:
                last_mod_datetime = None

            newer_than = datetime.datetime.combine(
                    newer_than_date,
                    datetime.time(0, 0, 1)
                    )
            tz_local = get_localzone()
            newer_than = tz_local.localize(newer_than)
            newer_than = newer_than.astimezone(pytz.utc)

            # fetch from web if no valid last_mod_datetime or
            #   last modified is after the newer_than date
            fetch_from_web = (last_mod_datetime is None) or last_mod_datetime > newer_than
        else:
            # always fetch from web if newer_than_date is None
            fetch_from_web = True

        if fetch_from_web:
            html = response.read()
        else:
            html = None

    return html


def make_cache_filename(filepath, filedate=datetime.date.today()):
    out_filename = "%s_%04d%02d%02d%s"%(
            str(Path(filepath).stem),
            filedate.year,
            filedate.month,
            filedate.day,
            str(Path(filepath).suffix)
            )
    return THEATER_CACHE_DIR / out_filename


def find_last_cachefile(filepath):
    matched_files = THEATER_CACHE_DIR.glob(
            "".join((Path(filepath).stem, "_*", Path(filepath).suffix))
            )

    matched_files = list(matched_files)
    #matched_files = [str(x) for x in matched_files]
    matched_files.sort()

    if matched_files:
        cache_file = matched_files[-1]
    else:
        cache_file = None

    return cache_file


def find_last_cachefile_date(filepath):
    # init to earliest possible date
    cache_date = None

    last_cache_file = find_last_cachefile(filepath)

    if last_cache_file:
        date_re = re.search(r"_(\d{4})(\d{2})(\d{2})", last_cache_file.stem)
        if date_re:
            cache_date = datetime.date(
                    int(date_re.group(1)),
                    int(date_re.group(2)),
                    int(date_re.group(3))
                    )

    return cache_date


def fetch_schedule_htmls():
    """
    Get latest versions of available theater calendar pages, and if they
    are newer than previous versions, deposit them in THEATER_CACHE_DIR

    Returns (list): of the latest versions of calendar html files, either
        from web (if newer than cache) or from cache (if web is not newer)
    """
    new_or_modified = 0

    mainpage_html = fetch_url(THEATER_BASEURL)

    soup = BeautifulSoup(mainpage_html, 'html5lib')

    links = soup.find_all('a')
    links = [x.get('href') for x in links]
    cal_links = [x for x in links if x.startswith('calendars')]
    cal_links = list(set(cal_links))
    if 'calendars/index.html' in cal_links:
        cal_links.remove('calendars/index.html')
    cal_links = [urllib.parse.quote(x) for x in cal_links]

    fetched_files = []
    for cal_link in cal_links:

        cache_date = find_last_cachefile_date(Path(cal_link).name)

        this_html = fetch_url(
                THEATER_BASEURL + cal_link,
                newer_than_date=cache_date
                )

        if this_html:
            cache_filename = make_cache_filename(Path(cal_link).name)

            with open(cache_filename, 'wb') as cache_fh:
                cache_fh.write(this_html)

            fetched_files.append(cache_filename)
            new_or_modified += 1
        else:
            cache_filename = find_last_cachefile(Path(cal_link).name)
            if cache_filename:
                fetched_files.append(cache_filename)

    # inform user on links and new/modified calendars
    print("%d calendar link%s found on %s"%(
        len(cal_links),
        's' if len(cal_links) > 1 else '',
        THEATER_BASEURL
        )
        )
    print("%d calendar%s that %s new or modified"%(
        new_or_modified,
        's' if new_or_modified != 1 else '',
        'are' if new_or_modified != 1 else 'is',
        )
        )

    return fetched_files


def main(argv=None):
    args = process_command_line(argv)

    # make sure cache dirs exist
    IMDB_CACHE_DIR.mkdir(exist_ok=True)
    THEATER_CACHE_DIR.mkdir(exist_ok=True)

    print("-"*78)
    print("Started at " + datetime.datetime.today().strftime("%I:%M%p %B %d, %Y"))
    print("-"*78, file=sys.stderr)
    print("Started at " + datetime.datetime.today().strftime("%I:%M%p %B %d, %Y"), file=sys.stderr)
    if args.file:
        srcfiles = [Path(x) for x in args.srcfile]
    else:
        srcfiles = fetch_schedule_htmls()

    for srcfile in srcfiles:
        print("-"*30)
        print(srcfile.name)
        print("-"*30, file=sys.stderr)
        print(srcfile.name, file=sys.stderr)

        ics_filename = ICAL_OUT_DIR / (srcfile.stem + '.ics')

        # parse html file, extract showtime info
        play_dates = parse_html_calendar(srcfile, args.verbose)

        # add imdb info to play_dates
        get_imdb_info(play_dates)

        # compute datetime data
        compute_datetimes(play_dates)

        # check for schedule overlap, inconsistent data
        check_for_problems(play_dates, correct_endtimes=args.correct_times)

        # (debug) text report of play_dates
        #report_playdates(play_dates)

        # write ical if we have any valid playdates
        if play_dates:
            gen_ical(play_dates, ical_filename=ics_filename)

        # print "finished" at date/time message
        print("Finished at " + datetime.datetime.today().strftime("%I:%M%p %B %d, %Y"))
        print("Finished at " + datetime.datetime.today().strftime("%I:%M%p %B %d, %Y"), file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        status = main(sys.argv)
    except KeyboardInterrupt:
        print("Stopped by Keyboard Interrupt", file=sys.stderr)
        # exit error code for Ctrl-C
        status = 130

    sys.exit(status)
