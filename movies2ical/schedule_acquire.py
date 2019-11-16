import datetime
from pathlib import Path
import re
import urllib.request
import urllib.error
import urllib.parse

from bs4 import BeautifulSoup
import pytz
from tzlocal import get_localzone

from .constants import THEATER_BASEURL, THEATER_CACHE_DIR


def make_cache_filename(filepath, filedate=datetime.date.today()):
    out_filename = "%s_%04d%02d%02d%s" % (
        str(Path(filepath).stem),
        filedate.year,
        filedate.month,
        filedate.day,
        str(Path(filepath).suffix),
    )
    return THEATER_CACHE_DIR / out_filename


def lastmod_datetime(last_mod_str):
    """Extract valid UTC datetime from Last-Modified str
    """
    last_mod_re = re.search(
        r",\s*(\d+\s+\S+\s+\d+\s+\d+:\d+:\d+)\s*(\S+)", last_mod_str
    )
    if last_mod_re:
        last_mod_strp = last_mod_re.group(1)
        tz = last_mod_re.group(2)

        last_mod_tz = pytz.timezone(tz)
        last_mod_datetime = datetime.datetime.strptime(
            last_mod_strp, "%d %b %Y %H:%M:%S"
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
    user_agent = "Mozilla/5.0"
    headers = {"User-Agent": user_agent}
    request = urllib.request.Request(url, headers=headers)
    html = None
    info = None
    try:
        response = urllib.request.urlopen(request)
    except urllib.error.URLError as err:
        if hasattr(err, "code"):
            print(err.code)
        else:
            print(err.reason)
    else:
        info = response.info()
        if newer_than_date is not None:
            if info.get("Last-Modified", None):
                last_mod_datetime = lastmod_datetime(info["Last-Modified"])
            else:
                last_mod_datetime = None

            newer_than = datetime.datetime.combine(
                newer_than_date, datetime.time(0, 0, 1)
            )
            tz_local = get_localzone()
            newer_than = tz_local.localize(newer_than)
            newer_than = newer_than.astimezone(pytz.utc)

            # fetch from web if no valid last_mod_datetime or
            #   last modified is after the newer_than date
            fetch_from_web = (
                last_mod_datetime is None
            ) or last_mod_datetime > newer_than
        else:
            # always fetch from web if newer_than_date is None
            fetch_from_web = True

        if fetch_from_web:
            html = response.read()
        else:
            html = None

    return html


def fetch_schedule_htmls():
    """
    Get latest versions of available theater calendar pages, and if they
    are newer than previous versions, deposit them in THEATER_CACHE_DIR

    Returns (list): only new versions of calendar html files, either
        from web (if newer than cache) or from cache (if newer than web)
    """
    new_or_modified = 0

    mainpage_html = fetch_url(THEATER_BASEURL)

    soup = BeautifulSoup(mainpage_html, "html5lib")

    links = soup.find_all("a")
    links = [x.get("href") for x in links]
    cal_links = [x for x in links if x.startswith("calendars")]
    cal_links = list(set(cal_links))
    if "calendars/index.html" in cal_links:
        cal_links.remove("calendars/index.html")
    cal_links = [urllib.parse.quote(x) for x in cal_links]

    new_files = []
    old_files = []
    for cal_link in cal_links:

        cache_date = find_last_cachefile_date(Path(cal_link).name)

        this_html = fetch_url(THEATER_BASEURL + cal_link, newer_than_date=cache_date)

        if this_html:
            cache_filename = make_cache_filename(Path(cal_link).name)

            with open(cache_filename, "wb") as cache_fh:
                cache_fh.write(this_html)

            new_files.append(cache_filename)
            new_or_modified += 1
        else:
            cache_filename = find_last_cachefile(Path(cal_link).name)
            if cache_filename:
                old_files.append(cache_filename)

    # inform user on links and new/modified calendars
    print(
        "%d calendar link%s found on %s"
        % (len(cal_links), "s" if len(cal_links) > 1 else "", THEATER_BASEURL)
    )
    print(
        "%d calendar%s that %s new or modified"
        % (
            new_or_modified,
            "s" if new_or_modified != 1 else "",
            "are" if new_or_modified != 1 else "is",
        )
    )

    return (new_files, old_files)


def find_last_cachefile(filepath):
    matched_files = THEATER_CACHE_DIR.glob(
        "".join((Path(filepath).stem, "_*", Path(filepath).suffix))
    )

    matched_files = list(matched_files)
    # matched_files = [str(x) for x in matched_files]
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
                int(date_re.group(1)), int(date_re.group(2)), int(date_re.group(3))
            )

    return cache_date
