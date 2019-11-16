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
import plistlib
import traceback

from icalendar import Calendar, Event
from imdb import IMDb
import pytz
import requests
import toml

# from movies2ical.constants import (
from .constants import (
    MAX_PLOT_LEN,
    THEATER_TZ,
    CONFIG_DIR,
    CONFIG_FILE,
    IMDB_CACHE_DIR,
    ICAL_OUT_DIR,
    THEATER_CACHE_DIR,
    MONTHS,
    DEFAULT_PLIST_INFO,
    DEFAULT_CONFIG_TOML_STR,
)
from .parse_html import parse_html_calendar
from .schedule_acquire import fetch_schedule_htmls


def process_command_line(argv):
    """Process command line invocation arguments and switches.

    Args:
        argv: list of arguments, or `None` from ``sys.argv[1:]``.

    Returns:
        args: Namespace with named attributes of arguments and switches
    """
    # script_name = argv[0]
    argv = argv[1:]

    # initialize the parser object:
    parser = argparse.ArgumentParser(
        description="Fetch latest web calendar from the Stanford "
        "Theatre, and convert it to ical format, complete "
        "with info from imdb.com"
    )

    # specifying nargs= puts outputs of parser in list (even if nargs=1)

    # required arguments
    parser.add_argument(
        "srcfile", nargs="*", help="Source directory (recursively searched)."
    )

    # switches/options:
    parser.add_argument(
        "-f",
        "--file",
        action="store_true",
        help="Parse files from arguments instead of going to "
        "www.stanfordtheatre.org to find calendar.",
    )
    parser.add_argument(
        "-c",
        "--correct_times",
        action="store_true",
        help="If runtime from imdb causes movie end time to overlap next "
        "movie's scheduled start time, correct end time.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="More verbose messages."
    )
    parser.add_argument(
        "-n",
        "--notify",
        action="store_true",
        help="Use Notify17 to send notifications on success or failure.",
    )
    parser.add_argument(
        "--plist",
        action="store_true",
        help="Do nothing but output a macOS plist file to the current directory suitable for inclusion in LaunchAgents.",
    )

    args = parser.parse_args(argv)

    return args


def fetch_imdb_info_cache(imdb_movie_num, movie_name):
    imdb_cache_filename = str(IMDB_CACHE_DIR / imdb_movie_num) + ".json"

    try:
        with open(imdb_cache_filename, "r") as imdb_cache_fh:
            imdb_movie = json.load(imdb_cache_fh)
    except (FileNotFoundError, PermissionError):
        # only do a CR progress-display if we are in a terminal (not directed
        #   to a file)
        if sys.stdout.isatty():
            print("\r", end="")
        else:
            print("\n", end="")
        print("Fetching info: " + movie_name + " " * (60 - len(movie_name)), end="")

        ia = IMDb()
        imdb_movie_web = ia.get_movie(imdb_movie_num, info=["main", "plot"])

        imdb_movie = {}
        imdb_movie["title"] = str(imdb_movie_web["title"])
        imdb_movie["director"] = [str(x) for x in imdb_movie_web["director"]]
        imdb_movie["writer"] = [str(x) for x in imdb_movie_web["writer"]]
        imdb_movie["cast"] = [str(x) for x in imdb_movie_web["cast"]]
        imdb_movie["runtimes"] = [str(x) for x in imdb_movie_web["runtimes"]]
        try:
            imdb_movie["plot"] = [str(x) for x in imdb_movie_web["plot"]]
        except KeyError:
            # no plot in imdb info
            imdb_movie["plot"] = [""]
        imdb_movie["year"] = int(imdb_movie_web["year"])
        imdb_movie["rating"] = float(imdb_movie_web["rating"])

        try:
            with open(imdb_cache_filename, "w") as imdb_cache_fh:
                json.dump(imdb_movie, imdb_cache_fh)
        except (IsADirectoryError, PermissionError):
            print("Can't write to imdb_cache dir")
    except Exception as err:
        print("Can't load: " + imdb_cache_filename)
        print(type(err))
        print(err)

    return imdb_movie


def get_imdb_info(play_dates):
    for play_date in play_dates:
        imdb_mnum_re = re.search(r"\/tt(\d+)", play_date["imdb_url"])
        if imdb_mnum_re:
            imdb_movie_num = imdb_mnum_re.group(1)

        imdb_movie = fetch_imdb_info_cache(imdb_movie_num, play_date["name"])

        play_date["imdb_info"] = {}
        play_date["imdb_info"]["title"] = imdb_movie["title"]
        play_date["imdb_info"]["director"] = imdb_movie["director"]
        play_date["imdb_info"]["writer"] = imdb_movie["writer"]
        play_date["imdb_info"]["cast"] = imdb_movie["cast"]
        play_date["imdb_info"]["runtimes"] = imdb_movie["runtimes"]
        play_date["imdb_info"]["plot"] = imdb_movie["plot"]
        play_date["imdb_info"]["year"] = imdb_movie["year"]
        play_date["imdb_info"]["rating"] = imdb_movie["rating"]

    # blank out last "Fetching data" line if we're in a terminal, else just \n
    if sys.stdout.isatty():
        print("\r" + " " * 78)
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

    plot = re.sub(r"::.*$", "", play_date["imdb_info"]["plot"][-1])
    # cut off plot descriptions that are too long
    if len(plot) > MAX_PLOT_LEN:
        plot = plot[:MAX_PLOT_LEN]
        # end plot string at end of word, add elipsis
        plot = re.sub(r"\s+\S*$", "", plot) + "..."
    out_str += play_date["imdb_url"]
    out_str += "\n\n"
    out_str += plot
    out_str += "\n\n"
    out_str += "Director" + persons_list_print(play_date["imdb_info"]["director"])
    out_str += "\n"
    out_str += "Writer" + persons_list_print(play_date["imdb_info"]["writer"])
    out_str += "\n\n"
    out_str += "Cast:\n"
    for cast_member in play_date["imdb_info"]["cast"][:10]:
        out_str += cast_member + "\n"

    return out_str


def report_playdates(play_dates):
    """Debug function to print out a text representation of play dates
    """
    for play_date in play_dates:
        print("-" * 78)
        print(play_date["name"])
        print(play_date["show_startdate"][0], end="")
        print(" ", end="")
        print(MONTHS[play_date["show_startdate"][1] - 1], end="")
        print(" " + str(play_date["show_startdate"][2]), end="")
        print(" - ", end="")
        print(play_date["show_enddate"][0], end="")
        print(" ", end="")
        print(MONTHS[play_date["show_enddate"][1] - 1], end="")
        print(" " + str(play_date["show_enddate"][2]))
        print(play_date["show_times"])
        print("Runtimes: " + str(play_date["imdb_info"]["runtimes"]))
        print("")

        print(movie_synopsis(play_date))


def compute_datetimes(play_dates):
    for play_date in play_dates:
        # TODO: check for other runtimes instead of just using first one
        runtime = int(play_date["imdb_info"]["runtimes"][0])
        play_date_start = datetime.date(*play_date["show_startdate"])
        play_date_end = datetime.date(*play_date["show_enddate"])

        play_date["showings"] = []

        for show_time in play_date["show_times"]:
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
                    this_play_date_start = play_date_start + datetime.timedelta(
                        days=5 - weekday_start
                    )
                if "sun" in show_time:
                    # set this_play_date_end to sunday (weekday=6) after
                    #   play_date_start
                    this_play_date_end = play_date_start + datetime.timedelta(
                        days=6 - weekday_start
                    )
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
                this_play_date_start, datetime.time(hour, minute, 0)
            )
            # put extracted time in THEATER timezone
            datetime_start = THEATER_TZ.localize(datetime_start)
            # Convert to UTC timezone
            datetime_start = datetime_start.astimezone(pytz.utc)

            datetime_end = datetime_start + datetime.timedelta(minutes=runtime)
            # rrule_count is how many days including this one
            rrule_count = (this_play_date_end - this_play_date_start).days + 1

            play_date["showings"].append(
                {
                    "datetime_start": datetime_start,
                    "datetime_end": datetime_end,
                    "rrule_count": rrule_count,
                }
            )


def gen_ical(play_dates, ical_filename="test.ics"):
    cal = Calendar()
    cal.add("prodid", "-//Stanford Theatre Calendar//itsayellow@gmail.com//")
    cal.add("version", "3.0")
    location = "221 University Ave, Palo Alto, CA (Stanford Theatre)"

    for play_date in play_dates:
        for showing in play_date["showings"]:
            datetime_start = showing["datetime_start"]
            datetime_end = showing["datetime_end"]
            rrule_count = showing["rrule_count"]

            # unique uid for each event
            uid = datetime_start.strftime("%Y%m%dT%H%M%S%Z")
            uid += "@itsayellow.com"

            # assemble event and add to calendar
            event = Event()
            event.add("dtstart", datetime_start)
            event.add("dtend", datetime_end)
            event.add("dtstamp", datetime_start)
            event.add("uid", uid)
            if rrule_count > 1:
                event.add("rrule", {"FREQ": "DAILY", "COUNT": rrule_count})
            event.add("summary", play_date["name"])
            event.add("url", play_date["imdb_url"])
            event.add("description", movie_synopsis(play_date))
            event.add("location", location)
            cal.add_component(event)

    # icalendar writes out bytes, so use 'wb'
    try:
        with open(ical_filename, "wb") as ical_fh:
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
        stan_name = play_date["name"]
        imdb_name = play_date["imdb_info"]["title"]
        imdb_year = play_date["imdb_info"]["year"]

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
        stan_name_cmp = re.sub(r'"', "", stan_name_cmp)
        imdb_name_cmp = re.sub(r'"', "", imdb_name_cmp)
        # ignore beginning "the"
        stan_name_cmp = re.sub(r"the\s+", "", stan_name_cmp, re.I)
        imdb_name_cmp = re.sub(r"the\s+", "", imdb_name_cmp, re.I)

        show_date_str = (
            MONTHS[play_date["showings"][0]["datetime_start"].month - 1]
            + " %d" % play_date["showings"][0]["datetime_start"].day
        )
        if stan_name_cmp != imdb_name_cmp:
            print("%s, Warning, inconsistent title:" % show_date_str)
            print("    Stanford Theatre: " + stan_name)
            print("                IMDb: " + imdb_name)
        if stan_year != imdb_year:
            print("%s, Warning, inconsistent year:" % show_date_str)
            print("    Stanford Theatre: %s (%d)" % (stan_name, stan_year))
            print("                IMDb: %s (%d)" % (imdb_name, imdb_year))


def check_schedule_overlap(play_dates, correct_endtimes=False):
    # check for schedule overlaps (movie 1 ends after movie 2 begins, and
    #   before movie 2 ends)
    # O(n!)
    for (i, play_date1) in enumerate(play_dates):
        for play_date2 in play_dates[i + 1 :]:
            for showing1 in play_date1["showings"]:
                for showing2 in play_date2["showings"]:
                    show_start_name = None

                    if (
                        showing1["datetime_start"]
                        < showing2["datetime_start"]
                        < showing1["datetime_end"]
                    ):
                        show_end_name = play_date1["name"]
                        show_end_time = showing1["datetime_end"]
                        show_start_name = play_date2["name"]
                        show_start_time = showing2["datetime_start"]
                        if correct_endtimes:
                            showing1["datetime_end"] = showing2[
                                "datetime_start"
                            ] - datetime.timedelta(minutes=1)
                    if (
                        showing2["datetime_start"]
                        < showing1["datetime_start"]
                        < showing2["datetime_end"]
                    ):
                        show_end_name = play_date2["name"]
                        show_end_time = showing2["datetime_end"]
                        show_start_name = play_date1["name"]
                        show_start_time = showing1["datetime_start"]
                        if correct_endtimes:
                            showing2["datetime_end"] = showing1[
                                "datetime_start"
                            ] - datetime.timedelta(minutes=1)

                    if show_start_name:
                        show_end_time = show_end_time.astimezone(THEATER_TZ)
                        show_end_time_str = show_end_time.strftime("%I:%M%p %Z")
                        show_start_time = show_start_time.astimezone(THEATER_TZ)
                        show_start_time_str = show_start_time.strftime("%I:%M%p %Z")
                        show_date_str = (
                            MONTHS[show_start_time.month - 1]
                            + " %d" % show_start_time.day
                        )
                        if correct_endtimes:
                            print("AUTOCORRECTING TO FIX:")
                        print("%s, Movie time conflict between:" % show_date_str)
                        print(
                            "    " + show_end_name + " (Ends at %s)" % show_end_time_str
                        )
                        print(
                            "    "
                            + show_start_name
                            + " (Starts at %s)" % show_start_time_str
                        )


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


def send_notify17(notify17_url, data):
    r = requests.post(url=notify17_url, data=data)
    # print reply
    print(r.text, file=sys.stderr)


def setup_app_directories():
    # make sure cache dirs exist
    IMDB_CACHE_DIR.mkdir(exist_ok=True, parents=True)
    THEATER_CACHE_DIR.mkdir(exist_ok=True, parents=True)
    CONFIG_DIR.mkdir(exist_ok=True, parents=True)

    config_toml_example_path = CONFIG_DIR / "config.toml.example"
    with config_toml_example_path.open("w") as config_toml_example_fh:
        config_toml_example_fh.write(DEFAULT_CONFIG_TOML_STR)


def get_config_info():
    try:
        config_info = toml.load(CONFIG_FILE)
    except IOError:
        config_info = {"plist": {}, "notify17": {}}

    return config_info


def generate_plist_file(config_info):
    # default info
    plist_info = DEFAULT_PLIST_INFO
    plist_info.update(config_info["plist"])
    with open("local.CheckStanfordMovies.plist", "wb") as plist_fh:
        plistlib.dump(plist_info, plist_fh)


def main(config_info, argv=None):
    args = process_command_line(argv)

    if args.plist:
        generate_plist_file(config_info)
        return 0

    print("-" * 78)
    print("Started at " + datetime.datetime.today().strftime("%I:%M%p %B %d, %Y"))
    print("-" * 78, file=sys.stderr)
    print(
        "Started at " + datetime.datetime.today().strftime("%I:%M%p %B %d, %Y"),
        file=sys.stderr,
    )
    if args.file:
        new_srcfiles = [Path(x) for x in args.srcfile]
        old_srcfiles = []
    else:
        (new_srcfiles, old_srcfiles) = fetch_schedule_htmls()

    new_icals = []
    for srcfile in new_srcfiles + old_srcfiles:
        print("-" * 30)
        print(srcfile.name)
        print("-" * 30, file=sys.stderr)
        print(srcfile.name, file=sys.stderr)

        ics_filename = ICAL_OUT_DIR / (srcfile.stem + ".ics")

        # parse html file, extract showtime info
        play_dates = parse_html_calendar(srcfile, args.verbose)

        # add imdb info to play_dates
        get_imdb_info(play_dates)

        # compute datetime data
        compute_datetimes(play_dates)

        # check for schedule overlap, inconsistent data
        check_for_problems(play_dates, correct_endtimes=args.correct_times)

        # (debug) text report of play_dates
        # report_playdates(play_dates)

        # write ical if we have any valid playdates
        if play_dates:
            gen_ical(play_dates, ical_filename=ics_filename)
            if srcfile in new_srcfiles:
                new_icals.append(ics_filename)

        # print "finished" at date/time message
        print("Finished at " + datetime.datetime.today().strftime("%I:%M%p %B %d, %Y"))
        print(
            "Finished at " + datetime.datetime.today().strftime("%I:%M%p %B %d, %Y"),
            file=sys.stderr,
        )
    if new_icals and args.notify and "new_calendar_url" in config_info["notify17"]:
        send_notify17(
            notify17_url=config_info["notify17"]["new_calendar_url"],
            data={"calendar_name": new_icals[0], "calendar_list": new_icals},
        )

    return 0


def cli():
    try:
        setup_app_directories()
        config_info = get_config_info()
        status = main(config_info, sys.argv)
    except KeyboardInterrupt:
        print("Stopped by Keyboard Interrupt", file=sys.stderr)
        # exit error code for Ctrl-C
        status = 130
    except Exception as e:
        traceback.print_exc()
        if "error_url" in config_info["notify17"]:
            send_notify17(
                notify17_url=config_info["notify17"]["error_url"],
                data={"error_text": str(e)},
            )
        status = 1

    sys.exit(status)


if __name__ == "__main__":
    cli()
