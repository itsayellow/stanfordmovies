import datetime
from pathlib import Path
import re

from bs4 import BeautifulSoup
import bleach

from .constants import MONTHS


def parse_html_calendar(html_file, verbose=False):
    # start by assuming calendar is in current year
    calendar_year = datetime.date.today().year

    # most of the time Stanford Theatre doesn't put year in filename or in
    #   html.  But we will add year to end of stored test calendar html files
    cal_year_re = re.search(r"_(20\d\d)(\d{4})?($|\.)", str(Path(html_file).stem))
    if cal_year_re:
        calendar_year = int(cal_year_re.group(1))
    print("Calendar Year: %d" % calendar_year)

    with open(html_file, "rb") as html_fh:
        html_bin = html_fh.read()

    # weird characters used in stanford movies:
    # hex 96: en-dash

    # bad html seen:
    #   sometimes </tr> with no starting <tr>
    #   sometimes <td> with no closing </td>

    # bare bones html parse, keeps all weirdness from stanfordtheatre html
    # soup = BeautifulSoup(html_bin, 'html.parser')

    # html5lib parse outputs valid html from broken stanfordtheatre html!
    #   a little slower but worth it
    soup = BeautifulSoup(html_bin, "html5lib")

    tables = soup.find_all("table")

    assert len(tables) == 1

    # search only for td, because sometimes bad html has no <tr> start tag!
    #   (but html5lib should clean this up and add a <tr>)
    play_dates = []
    for td in tables[0].find_all("td"):
        td_play_dates = parse_td(td, calendar_year, verbose=verbose)

        if td_play_dates is not None:
            play_dates.extend(td_play_dates)

    return play_dates


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
        r"(?:" + "|".join(movie_regexs) + r")", "".join([str(x) for x in td.contents])
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
        time_str = bleach.clean(td_splits[i + 1].strip(), tags=[], strip=True)

        # if (movieyear) string is after link and ends up in time_str,
        #   cut it out and append it to movie_name
        movieyear_moviename_re = re.search(r"\(\D*\d{4}\D*\)\s*$", movie_name)
        movieyear_timestr_re = re.search(r"^\s*(\(\D*\d{4}\D*\))", time_str)
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
                    "name": movie_name,
                    "imdb_url": imdb_link,
                    "show_startdate": td_startdate,
                    "show_enddate": td_enddate,
                    "show_times": movie_times,
                }
            )
        return movie_return
    else:
        return None


def extract_movies_imdb(td):
    movies = []

    for link in td.find_all("a"):
        if re.search(r"https?://[^/]*imdb\.", link["href"]):
            movie_text = "".join([str(x) for x in link.contents])
            movies.append([str(link), link["href"], movie_text])

    return movies


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
    #   August 31-Sept 3
    # somebody occasionally uses month abbreviations, need to parse
    #   in month_regexp
    #   Oct 3-4
    month_regexp = "(" + "|".join(MONTHS) + ")"
    onemonth_multdate_re = re.search(
        month_regexp + r"\s+(\d+)\s*-\s*(\d+)($|\D)", content_str
    )
    multmonth_multdate_re = re.search(
        month_regexp + r"\s+(\d+)\s*-\s*" + month_regexp + r"\s*(\d+)($|\D)",
        content_str,
    )
    # note: will also match last date in multmonth_multdate_re
    onemonth_onedate_re = re.search(month_regexp + r"\s+(\d+)\s*($|[^-])", content_str)
    if onemonth_multdate_re:
        month_start_num = MONTHS.index(onemonth_multdate_re.group(1)) % 12 + 1
        date_start_num = int(onemonth_multdate_re.group(2))
        month_end_num = month_start_num
        date_end_num = int(onemonth_multdate_re.group(3))
    elif multmonth_multdate_re:
        month_start_num = MONTHS.index(multmonth_multdate_re.group(1)) % 12 + 1
        date_start_num = int(multmonth_multdate_re.group(2))
        month_end_num = MONTHS.index(multmonth_multdate_re.group(3)) % 12 + 1
        date_end_num = int(multmonth_multdate_re.group(4))
    elif onemonth_onedate_re:
        month_start_num = MONTHS.index(onemonth_onedate_re.group(1)) % 12 + 1
        date_start_num = int(onemonth_onedate_re.group(2))
        month_end_num = month_start_num
        date_end_num = date_start_num

    if month_start_num is not None:
        td_startdate = (calendar_year, month_start_num, date_start_num)
        td_enddate = (calendar_year, month_end_num, date_end_num)

    return (td_startdate, td_enddate)


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
            print("Warning: extra movie time " + paren_full + " is unparseable.")
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
