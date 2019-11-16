#!/usr/bin/env python3

# TODO: incorporate shorts without their own times into main feature
#       description
# TODO: properly handle unicode in imdb data

import sys
import argparse
import datetime
from pathlib import Path
import plistlib
import traceback

import requests
import toml

# from movies2ical.constants import (
from .constants import (
    CONFIG_DIR,
    CONFIG_FILE,
    IMDB_CACHE_DIR,
    ICAL_OUT_DIR,
    THEATER_CACHE_DIR,
    DEFAULT_PLIST_INFO,
    DEFAULT_CONFIG_TOML_STR,
)
from .parse_calendar import parse_html_calendar, compute_datetimes
from .schedule_acquire import fetch_schedule_htmls
from .verify import check_for_problems
from .imdb import get_imdb_info
from .outputs import gen_ical


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
