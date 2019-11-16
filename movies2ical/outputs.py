import re

from icalendar import Calendar, Event

from .constants import MAX_PLOT_LEN, MONTHS


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
