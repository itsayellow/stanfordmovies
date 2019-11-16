import datetime
import re

from .constants import THEATER_TZ, MONTHS


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
