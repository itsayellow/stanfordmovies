import json
import re
import sys

from imdb import IMDb

from .constants import IMDB_CACHE_DIR


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
