#!/usr/bin/env python2

# go to http://www.stanfordtheatre.org/
# find the link to http://www.stanfordtheatre.org/calendars/* on that page
# download that link
# scrape that link to get for each day
#   Year
#   dates/times/movies/imdb urls
#   from imdb url, fetch director, writer, cast, runtime
# put each movie into ical
# finish ical
# upload ical to google?
#   pip2 install beautifulsoup4
#   pip2 install dateutils
#   pip2 install icalendar
#   pip2 install lxml

# TODO: find all imdb urls and fetch them all with threads simultaneously

import sys
import optparse 

import urllib2
import re
from bs4 import BeautifulSoup
#from dateutil.parser import parse
import dateutil.parser as dparse
import dateutil.relativedelta as drel
import datetime
import os
import errno
import pytz
# ical stuff
from icalendar import Calendar, Event
import codecs
import filecmp

#-----------------------------------------------------------------------
# debug/config variables

# debug level (0 is no debug, higher number prints messages)
DEBUG = 0
# base url of stanford theatre
BASEURL = r"http://www.stanfordtheatre.org/"
# normal is USE_INTERNET = True
# to debug without fetching real webpages use False here
#USE_INTERNET = False
# directory location of cache
CACHE_DIR = 'cache'
# force cache_only (no http) pages (set by switch argument)
CACHE_ONLY = False
#-----------------------------------------------------------------------
# globals
# Pacific Timezone (TODO: does this automatically do DST? A: I think it does)
PAC_TZ = pytz.timezone('US/Pacific')

def debug(level, message):
    if DEBUG > level:
        try:
            print message
        except UnicodeEncodeError:
            # maybe we need to translate unicode if print has error
            print message.encode('utf8')

def get_page_mod_time(url):
    url = urllib2.quote(url,':/')
    usock = urllib2.urlopen(url)
    page_info = usock.info()
    page_httpstatuscode = usock.getcode()
    usock.close()
    debug(1, page_info)
    debug(0, 'Content-Length: '+page_info['Content-Length'] )
    return page_info['Last-Modified']

def ensure_dir_exists(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise

def fetch_page_cache(url):
    """
    fetch page to cache if it is newer than the saved version in the cache
    return fh to cache
    """
    debug(0,"url="+url)
    # get just filename ending of url (or last thing before slash if slash
    #   ends url)
    filename = re.search(r'/([^/]+)\/?$',url).group(1)
    filename = urllib2.quote(url,'')
    # get page from internet if it does not exist in cache or cache
    #   is out of date
    # make impossibly early initial value for cache_last_mod_str
    cache_last_mod_str = "30 Jul 1971 00:00:01 GMT"
    # make sure cache dir is here
    ensure_dir_exists( CACHE_DIR )
    ensure_dir_exists( CACHE_DIR+"/info/" )
    # check for existing file in cache
    try:
        cache_h = open( CACHE_DIR+"/info/"+filename )
        cache_last_mod_str = cache_h.readline()
        cache_h.close()
        file_in_cache = True
    except IOError:
        debug(0, filename + " not in cache" )
        file_in_cache = False
    # get page modified info unless CACHE_ONLY==True
    # TODO: handle no file in cache and CACHE_ONLY==True
    if not CACHE_ONLY or not file_in_cache:
        # make a url safe for urlopen (no spaces) don't modify : or / so
        #   http:// still works properly  (but : in path will be problem!)
        url = urllib2.quote(url,':/')
        # TODO: catch URLError (e.g. for network timeout)
        usock = urllib2.urlopen(url)
        page_info = usock.info()
        #print page_info
        #TODO: imdb has no Last-Modified property???
        try:
            web_last_mod_str = page_info['Last-Modified']
        except:
            # TODO: hack this is just wrong (cache will always be up-to-date)
            debug(0,"No Last-Modified for "+url)
            web_last_mod_str = "30 Aug 1971 00:00:01 GMT"
        if dparse.parse(web_last_mod_str) > dparse.parse(cache_last_mod_str):
            # internet page is newer than cache so load and write it to cache
            debug(0, filename + ": updating cache from web" )
            try:
                os.rename(CACHE_DIR+"/"+filename, CACHE_DIR+"/"+filename+".old" )
                debug(0, "Moving old file to " + CACHE_DIR+"/"+filename+".old" )
            except OSError:
                debug(0, "No old file in cache to rename" )
            cache_h = open(CACHE_DIR+"/"+filename,'w')
            cache_h.write(usock.read())
            cache_h.close()
            cache_info_h = open(CACHE_DIR+"/info/"+filename,'w')
            cache_info_h.write(web_last_mod_str)
            cache_info_h.close()
        else:
            debug(0, filename + ": cache is up-to-date" )
    else:
        debug(0, "Forcing CACHE_ONLY for" + filename  )


    # return filehandle to cache
    return open(CACHE_DIR+"/"+filename,'r')

def get_current_schedule():
    #mainpage_h = fetch_page_cache(BASEURL+"index.html")
    mainpage_h = fetch_page_cache(BASEURL)
    mainpage_text = mainpage_h.read()
    mainpage_h.close()
    mainpage = BeautifulSoup(mainpage_text,"lxml")

    debug(1, mainpage.title.string )

    for link in mainpage.find_all('a'):
        # if the text includes the text "Current" and link involves /calendars/
        #   then this is the current list
        #print link
        if ( re.search(r'calendars',link.get('href')) and
                re.search(r'current',link.get_text(),re.I) ):
            url = BASEURL+link.get('href')
            if DEBUG > 1:
                print "LINK:"
                print link
                print "CONTENTS:"
                print link.contents
                print "CHILDREN:"
                for child in link.children:
                    print child
                    print "-----------------------"
                print "GET_TEXT:"
                print link.get_text()
                print "URL:"
                print url
    return url

def get_all_current_schedules():
    #mainpage_h = fetch_page_cache(BASEURL+"index.html")
    mainpage_h = fetch_page_cache(BASEURL)
    mainpage_text = mainpage_h.read()
    mainpage_h.close()
    mainpage = BeautifulSoup(mainpage_text,"lxml")

    debug(1, mainpage.title.string )

    urls = set()
    for link in mainpage.find_all('a'):
        # if the text includes the text "Current" and link involves /calendars/
        #   then this is the current list
        #print link
        if ( re.search(r'calendars',link.get('href')) and not
                re.search(r'index.html$',link.get('href'))
                 ):
            urls.add( BASEURL+link.get('href') )
            if DEBUG > 1:
                print "LINK:"
                print link
                print "CONTENTS:"
                print link.contents
                print "CHILDREN:"
                for child in link.children:
                    print child
                    print "-----------------------"
                print "GET_TEXT:"
                print link.get_text()
                print "URL:"
                #print urls[-1]
    return list(urls)

def extract_playdates(url):
    # TODO: get current year:
    #   either assume current real year, or 
    #   search for r'[ ,]20\d\d\D' (and maybe see if it matches current year?)

    # get handle to cached page
    html_schedule_h = fetch_page_cache(url)
    sched_soup = BeautifulSoup(html_schedule_h,"lxml")
    html_schedule_h.close()
    # find eventyear
    yearline = sched_soup.find(text=re.compile(r'\b20\d\d\b'))
    if yearline is not None:
        eventyear = int(re.search(r'\b20\d\d\b', yearline).group(0)) 
    else:
        print "No year found in schedule, using current year"
        eventyear = datetime.date.today().year
    debug(0, "eventyear = %d"%eventyear )
    return (sched_soup.find_all('td','playdate'), eventyear )

def startend_dates(datestring, eventyear):
    # replace en-dash with dash
    #datestring = re.sub('\xe2\x80\x93','-', datestring)
    datestring = re.sub(u'\u2013','-', datestring)
    debug(0, "datestring = %s"%datestring )
    startmatch = re.search(r'([a-zA-Z]+)\s*(\d+)', datestring)
    if startmatch is None:
        return (None, None)
    startmonth = startmatch.group(1)
    startdate = int(startmatch.group(2))
    endmatch = re.search(r'-\s*([a-zA-Z]+)?\s*(\d+)', datestring)
    if endmatch:
        # TODO: isn't this overruled by next endmonth=?
        endmonth = endmatch.group(1)
        enddate = int(endmatch.group(2))
        if endmonth is None:
            endmonth = startmonth
        else:
            endmonth = re.search(r'-\s*(\w+)', datestring).group(1)
    else:
        endmonth = startmonth
        enddate = startdate
    start_date_str = "%s %d, %d"%(startmonth,startdate,eventyear)
    end_date_str = "%s %d, %d"%(endmonth,enddate,eventyear)
    debug(0, "start = %s"%start_date_str )
    debug(0, "end = %s "%end_date_str )
    start_d = dparse.parse(start_date_str)
    end_d = dparse.parse(end_date_str)
    return (start_d, end_d)

def datetimes(startdate, enddate, movie_times, runtime):
    # each time separately
    # (startdatetime, enddate)
    # 7:30 (plus 3:55 Sunday)
    # 7:30 (plus 3:45 Sat/Sun)
    # 7:30 (plus Sat/Sun 3:50)
    # 7:30 (plus 2:00 Saturday)
    # 7:30 (plus 2:00 matinee Sat/Sun)
    # 5:55, 9:10

    # assemble times into list of strings, with "plus" if extra time on day
    debug(0,"movie_times=%s"%movie_times)
    extra_match = re.search(r'\(([^)]+)\)',movie_times )
    times_str = re.search(r'^[^(]+', movie_times).group(0)
    times_list = re.findall(r'\d{1,2}:\d{2}',times_str)
    if extra_match:
        extra_str = extra_match.group(1).strip()
        debug(0,"extra match, extra_str=%s"%extra_str)
        if not re.search(r'plus',extra_str):
            extra_str = "plus "+extra_str
        times_list.append(extra_str)
    # init list to empty list
    datetime_list = []
    # go through each time separately for the given movie, find days
    if DEBUG>0:
        print "times_list=",times_list
    for time_str in times_list:
        debug(0,"time_str = '%s'"%time_str)
        if re.search(r'plus', time_str):
            # extra time only for certain days
            # init days with False
            extra_sun = False
            extra_sat = False
            if re.search(r'sun',time_str,re.IGNORECASE):
                extra_sun = True
            if re.search(r'sat',time_str,re.IGNORECASE):
                extra_sat = True
            if DEBUG>0:
                extra_time = re.search(r'\d{1,2}:\d{2}',time_str).group(0)
                print "extra_time = ",extra_time
            if extra_sat:
                # startdatetime = sat after startdate with extra_time
                startdatetime = startdate + drel.relativedelta(weekday=drel.SA)
                if extra_sun:
                    # enddate = sun after startdate with extra_time
                    enddate_recur = startdate + drel.relativedelta(weekday=drel.SU)
                    rrule_count = 2
                else:
                    enddate_recur = startdate + drel.relativedelta(weekday=drel.SA)
                    rrule_count = 1
            elif extra_sun:
                # startdatetime = sun after startdate with extra_time
                # enddate = sun after startdate with extra_time
                startdatetime = startdate + drel.relativedelta(weekday=drel.SU)
                enddate_recur = startdate + drel.relativedelta(weekday=drel.SU)
                rrule_count = 1
            else:
                # errors
                raise Exception("extra time that is not Sat. or Sun.?\n%s"%extra_str)
        else:
            # regular time uses regular original dates
            startdatetime = startdate
            enddate_recur = enddate
            # number of total events is end-start+1
            rrule_count = (enddate-startdate).days + 1
        #startdatetime = startdatetime with time replaced by actual time
        time_match = re.search(r'(\d\d?):(\d\d)',time_str)
        # hour is always PM, so add 12
        thishour = int(time_match.group(1)) + 12
        thisminute = int(time_match.group(2))
        startdatetime = startdatetime.replace(hour=thishour, minute=thisminute)
        startdatetime = PAC_TZ.localize(startdatetime)
        # TODO: do we need to convert to utc below?
        # TODO: problem with converting to utc, is that times become the next
        #       day!  In which case maybe number of recurring days is safest
        startdatetime = startdatetime.astimezone(pytz.utc)
        stopdatetime = startdatetime + datetime.timedelta(minutes=runtime)
        if DEBUG>0:
            print "startdatetime ",startdatetime
            print "enddate_recur ",enddate_recur # DEPRECATED (erroneous?)
            print "rrule_count ",rrule_count
        datetime_list.append(
                {'startdatetime':startdatetime,
                'stopdatetime':stopdatetime, 'rrule_count':rrule_count }
                )
    return(datetime_list)

def info_from_imdb(imdb_url):
    # TODO: use ur'' for raw-unicode search strings in re.* functions
    info = {}
    runtime = 0
    imdb_h = fetch_page_cache(imdb_url)
    imdb_text = imdb_h.read()
    imdb_h.close()
    imdb = BeautifulSoup(imdb_text,"lxml")
    # Movie Title
    # <meta property='og:title' content="Roman Holiday (1953)" />
    # <meta property='og:title' content="Our Mr. Sun (TV Movie 1956)" />
    # TODO: extra title
    #<span class="title-extra" itemprop="name"> "Bank Holiday"
    #   <i>(original title)</i> </span> 
    title_tag = imdb.find(name='meta', attrs={'property':'og:title'})
    titleyear = title_tag.attrs['content']
    title = re.search(ur'^(.*\S)\s+\(',titleyear).group(1)
    year = re.search(ur'\(\D*(\d{4})\D*\)',titleyear).group(1)
    info['title'] = title
    info['year'] = int(year)
    # Runtime
    # use the first runtime
    #<div class="txt-block">
    #<h4 class="inline">Runtime:</h4> 
    #<time itemprop="duration" datetime="PT118M">118 min</time>
    #<span class="ghost">|</span>
    #<time itemprop="duration" datetime="PT117M">117 min</time>
    #(cut)
    #</div>
    runtime_tag = imdb.find(name='time',attrs={'itemprop':'duration'})
    if runtime_tag:
        runtime_str = runtime_tag.attrs['datetime']
        debug(0,"runtime_str = "+str(runtime_str))
        debug(0,"runtime text= "+runtime_tag.string.strip())
        runtime = int(re.search(r'(\d+)M',runtime_str).group(1))
    else:
        # assume runtime is 90 minutes if we can't find a runtime
        runtime = 90
    debug(0,"runtime = "+str(runtime)+" min")
    info['runtime'] = runtime
    # Director(s)
    #<div class="txt-block" itemprop="director" itemscope itemtype="http://schema.org/Person"> 
    #<h4 class="inline">Director:</h4>
    #<a href="/name/nm0943758/?ref_=tt_ov_dr" itemprop='url'>
    #<span class="itemprop" itemprop="name">William Wyler</span></a>
    #</div> 
    # IMDB seems to use span sometimes, first try div and then span
    director_tag = imdb.find(name='div',attrs={'itemprop':'director'})
    if director_tag is None:
        director_tag = imdb.find(name='span',attrs={'itemprop':'director'})
    # e.g The Lady from Shanghai http://www.imdb.com/title/tt0040525/
    #   has no directors.  TODO: could check http://..../fullcredits
    if director_tag is not None:
        directors_tags = director_tag.find_all(name='span',attrs={'itemprop':'name'})
        directors = [x.get_text() for x in directors_tags]
    else:
        debug(0, "can't find director_tag for "+title)
        directors = [""]
    # use get_text() instead of string so we get plain unicode not object
    info['directors'] = directors
    # Writer(s)
    #<div class="txt-block" itemprop="creator" itemscope itemtype="http://schema.org/Person"> 
    #<h4 class="inline">Writers:</h4>
    #<a href="/name/nm0402848/?ref_=tt_ov_wr" itemprop='url'>
    #<span class="itemprop" itemprop="name">Ian McLellan Hunter</span></a>               (screenplay), 
    #<a href="/name/nm0226538/?ref_=tt_ov_wr" itemprop='url'>
    #<span class="itemprop" itemprop="name">John Dighton</span></a>               (screenplay),
    #<a href="fullcredits?ref_=tt_ov_wr#writers" >2 more credits</a>&nbsp;&raquo;
    #</div> 
    # IMDB seems to use span sometimes, first try div and then span
    writer_tag = imdb.find(name='div',attrs={'itemprop':'creator'})
    if writer_tag is None:
        writer_tag = imdb.find(name='span',attrs={'itemprop':'creator'})
    if writer_tag is not None:
        writer_text = writer_tag.get_text().strip()
        # get text before the &nbsp; char (\xa0) and >> char (\xbb)
        writer_text = re.search(ur'[^\xa0\xbb]+',writer_text).group(0)
        # consolidate multi-spaces into one space
        writer_text = re.sub(r'\s+',' ',writer_text.strip())
        # remove "Writer:" or "Writers:"
        writer_text = re.sub(r'Writers?:','',writer_text.strip())
        writers = writer_text.split(',')
        writers = [x.strip() for x in writers]
    else:
        debug(0, "can't find creator_tag for "+title)
        writers = [""]
    info['writers'] = writers
    # Cast
    cast_tag = imdb.find(name='table', attrs={'class':'cast_list'} )
    cast_list_tags = cast_tag.find_all(name='span', attrs={'itemprop':'name'})
    cast_members = [x.string.strip() for x in cast_list_tags]
    info['cast'] = cast_members

    # Description (TODO: experimental)
    # <meta name="description" content="Directed by William Wyler.  With Gregory Peck, Audrey Hepburn, Eddie Albert, Hartley Power. A bored and sheltered princess escapes her guardians and falls in love with an American newsman in Rome." />
    if False:
        description_tag = imdb.find(name='meta', attrs={'name':'description'})
        description = description_tag.attrs['content']
        # remove "Directed by..." and "With..." sentences at start
        description = re.sub(ur'^Directed.+\.\s*With[^.]+\.\s*','',description)
    if True:
        description_tag = imdb.find(name='p', attrs={'itemprop':'description'})
        if description_tag is None:
            debug(0, "found div description_tag for "+title)
            description_tag = imdb.find(name='div', attrs={'itemprop':'description'})
        #TODO: some imdb have no description, and description_tag=None
        #if imdb.find(name='p', attrs={'itemprop':'description'}) is not None:
        #    description = description_tag.text.strip()
        if description_tag is not None:
            description = description_tag.text.strip()
        else:
            debug(0, "can't find description_tag for "+title)
            description = ur''
        # get rid of many spaces and anything after it ("See full summary >>")
        # TODO: also can look for "..." which is at end of truncated descrip
        description = re.sub(ur'\s{4,}.+','',description)
    debug(0,description.encode('utf-8'))
    info['description'] = description
    return info

def parse_playdate(playdate, eventyear):
    debug(1,'parse_playdate')
    debug(1,playdate)
    date = playdate.find('p','date')
    returnlist = []
    # TODO: farm the next for list out in parallel to threads
    loop = 0
    # iterate over all paragraphs in playdate.  Each paragraph typically
    #   has movie+time combo
    for movieinfo in date.find_next_siblings('p'):
        loop = loop + 1
        debug(1,"\nparse_playdate:loop %d iteration start------------------------"%loop)
        debug(1,movieinfo)
        debug(1,movieinfo.contents)
        debug(1,movieinfo.text)
        movieinfo_text = re.sub(r'\n','',movieinfo.text)
        movie = movieinfo.find('a')
        if movie is None:
            debug(1,'continue')
            continue
        moviename_year = movie.text
        debug(0,moviename_year);
        moviename = re.search(r'([^(]+[^( ])',moviename_year).group(1)
        # TODO: sometimes they only wrap the moviename in <a> and leave
        #   the movie year outside of it!
        # TODO: clean up movie year handling code
        if (re.search(r'\((\d{4})\)',moviename_year)):
            movieyear = re.search(r'\((\d{4})\)',moviename_year).group(1)
        else:
            movieyear = -1
        movie_imdburl = movie.get('href')
        # last item in movieinfo.contents ends in times, but weird author
        #   may not make <br> between (movieyear) and times, so we just need
        #   to parse the end of last item to find times
        # Used to use movieinfo.contents[-1].strip() but this only works
        #   if movie times have a <br> before them.  Instead find first
        #   time (with ':') in movieinfo_text, and use that until end of str
        #movie_times = movieinfo.contents[-1].strip()
        debug(0,movieinfo_text)
        if re.search(r'\d+:.+',movieinfo_text):
            movie_times = re.search(r'\d+:.+',movieinfo_text).group(0)
        else:
            #print "\nWARNING: had to skip to next paragraph for movie %s to find times.\n"%moviename
            # possibly stupid person makes new paragraph between movie and
            # times, check here if we find no times in movie <p>
            # TODO: this may break things? skip a movie?
            movieinfo = movieinfo.findNextSibling('p')
            movieinfo_text = re.sub(r'\n','',movieinfo.text)
            debug(1,movieinfo)
            movie_times = re.search(r'\d+:.+',movieinfo_text).group(0)
        debug(0,"movie_times=%s"%movie_times)
        movie_times = movie_times.strip()
        (startdate, enddate) = startend_dates(date.text, eventyear)
        # did this for no real start end dates
        if startdate is None:
            debug(1,'continue')
            continue
        imdb_info = info_from_imdb(movie_imdburl)
        # TODO: clean up movie year handling code
        if movieyear==-1:
            movieyear = str(imdb_info['year'])
        # check if imdb movie matches schedule
        # TODO: drop beginning "The" in title before comparing
        #if imdb_info['title'] != moviename:
        if re.sub(r'^The\s+','',imdb_info['title']).lower() != re.sub(r'^The\s+','',moviename).lower():
            print "\rWARNING: imdb title (%s) doesn't match schedule (%s)"%(
                    imdb_info['title'], moviename
                    )
        if imdb_info['year'] != int(movieyear):
            print "\rWARNING: imdb year (%d) doesn't match schedule (%d)"%(
                    imdb_info['year'], int(movieyear)
                    )
        runtime = imdb_info['runtime']
        movie_datetimes = datetimes(startdate, enddate, movie_times, runtime)
        returnlist.append(
                {'name':moviename, 'movieyear':movieyear, 
                    'imdburl':movie_imdburl,
                    'dates':date.text, 'times':movie_times,
                    'movie_datetimes':movie_datetimes,
                    'startdate':startdate,
                    'enddate':enddate,
                    'imdb_info':imdb_info
                    }
                )
        print "\r" + moviename + " "*(70-len(moviename)),
        sys.stdout.flush()
        debug(0,"")
        if DEBUG > 1:
            print movie_imdburl
            print date.text
            print movie_times
            print "\n",
        debug(0,"")
    return returnlist

def parse_playdates(playdates, eventyear):
    movielist = []
    for playdate in playdates:
        # TODO: experimental try surrounding parse_playdate
        #       bad form!
        try:
            movielist.extend(parse_playdate(playdate, eventyear))
        except:
            print "Problem parsing playdate ("+playdate.text+")\n"
    print "\r" + " "*70 + "\r",
    return movielist

def write_ical(movielist, url):
    # construct output filename from url
    ical_filename = re.search(r'([^/]+).html',url).group(1) + ".ics"
    # Calendar object
    cal = Calendar()
    cal.add('prodid', '-//Stanford Theatre Calendar//itsayellow@gmail.com//')
    cal.add('version', '2.0')
    location = "221 University Ave, Palo Alto, CA (Stanford Theatre)"

    event_counter = 0
    #event = Event()
    #event.add('summary', 'UTC Python meeting about calendaring')
    #event.add('dtstart', datetime(2013,8,11,8,0,0,tzinfo=pytz.utc))
    #event.add('dtend', datetime(2013,8,11,10,0,0,tzinfo=pytz.utc))
    #event.add('dtstamp', datetime(2013,11,4,0,10,0,tzinfo=pytz.utc))
    #event['uid'] = '20130815T101010/27346262376@mxm.dk'
    #event.add('priority', 5)
    #cal.add_component(event)

    #summary = "Roman Holiday (1953)"
    #description = "http://www.imdb.com/title/tt0046250/\n\nDirector: William Wyler\n\nWriters: Ian McLellan Hunter (screenplay), John Dighton (screenplay), 2 more credits\n\nCast:\nGregory Peck\nAudrey Hepburn\nEddie Albert\nHartley Power\nHarcourt Williams\nMargaret Rawlings\nTullio Carminati\nPaolo Carlini\nClaudio Ermelli\nPaola Borboni\nAlfredo Rizzo\nLaura Solari\nGorella Gori\n"
    #url = "http://www.imdb.com/title/tt0046250/"

    for movie in movielist:
        if len(movie['imdb_info']['writers'] ) > 1:
            writ_s = "s"
        else:
            writ_s = ""
        if len(movie['imdb_info']['directors'] ) > 1:
            direct_s = "s"
        else:
            direct_s = ""
        description = u""
        description += movie['imdburl'] + u"\n\n"
        description += movie['imdb_info']['description'] + u"\n\n"
        description += u"Director" + direct_s + ": "
        description += u', '.join(movie['imdb_info']['directors'] ) + u"\n"
        description += u"Writer" + writ_s + ": "
        description += u', '.join(movie['imdb_info']['writers'] ) + u"\n\n"
        description += u"Cast:\n"
        description += u'\n'.join(movie['imdb_info']['cast'] ) + u"\n"
        description = description.encode('utf8')

        for movie_datetime in movie['movie_datetimes']:
            event = Event()
            event.add('summary', movie['name'] + " (" +movie['movieyear']+ ")" )
            event.add('description', description )
            event.add('url', movie['imdburl'] )
            event.add('location', location )
            if movie_datetime['rrule_count']>1:
                event.add('rrule',
                        {'FREQ':'DAILY','COUNT':movie_datetime['rrule_count']}
                        )
            event.add('dtstart', movie_datetime['startdatetime'])
            event.add('dtend', movie_datetime['stopdatetime'])
            # TODO: dtstamp?
            event.add('dtstamp', movie_datetime['startdatetime'])
            uid = movie_datetime['startdatetime'].strftime('%Y%m%dT%H%M%S%Z')
            # TODO: is it ok not to have the sequential counter?  it should
            #   be, because we shouldn't have two things at the same time
            #uid += '-%d@cutepuppiesandkittens.fake'%event_counter
            uid += '@cutepuppiesandkittens.fake'
            event['uid'] = uid

            cal.add_component(event)
            event_counter += 1

    #ical_h = open(ical_filename, 'wb')
    #ical_h.write(cal.to_ical())
    #ical_h.close()

    # NOTE: google calendar seems to screw up special characters if the ics
    #       file has file encoding 'utf-8'  But it gets proper special 
    #       charaters if file encoding is 'latin1'.
    #       So use latin1 to output ics file!
    # save to ical_filename + ".new", only if new file is different 
    #   do we rename it later
    ical_filename_new = ical_filename + ".new"
    icalc_h = codecs.open(ical_filename_new, 'w', encoding='latin1')
    icalc_h.write( unicode(cal.to_ical(),encoding='utf8') )
    icalc_h.close()

    # if file exists, move it to different name, don't overwrite it
    if not os.path.isfile(ical_filename):
        # no pre-existing file with ical_filename, so rename to std name
        os.rename(ical_filename_new, ical_filename )
    else:
        # remove ical_old_rename file if new file is not different
        if filecmp.cmp(ical_filename_new, ical_filename):
            # new file is same as old file
            print "No new updates to "+ical_filename
            os.remove(ical_filename_new)
        else:
            # new file is different, archive old file
            i = 0
            while(1):
                ical_old_rename = ical_filename + ".old%02d"%i
                if not os.path.isfile(ical_old_rename):
                    os.rename(ical_filename, ical_old_rename)
                    break
                i += 1
            # rename .new to std name
            os.rename(ical_filename_new, ical_filename )

def process_command_line(argv):
    """
    Return a 2-tuple: (settings object, args list).
    `argv` is a list of arguments, or `None` for ``sys.argv[1:]``.
    """
    # initialize the parser object:
    parser = optparse.OptionParser(
        formatter=optparse.TitledHelpFormatter(width=78),
        add_help_option=None,
        usage = "usage: %prog [options]")

    # define options here:
    parser.add_option(      # customized description; put --help last
        '-h', '--help', action='help',
        help='Show this help message and exit.')
    parser.add_option(
        '-d', '--debug', dest="debuglevel", default=None,
        help='Specify debug level.')
    parser.add_option(
        '-c', '--cacheonly', dest="cacheonly", default=False,
        action="store_true",
        help='Use cache for all urls, do not fetch from internet.')
        # TODO: flesh out cacheonly!

    (settings, args) = parser.parse_args(argv)
    if settings.debuglevel is not None:
        global DEBUG
        DEBUG = int(settings.debuglevel)
        print "setting DEBUG=%d"%DEBUG
    CACHE_ONLY = settings.cacheonly

    #if len(args) == 0:
    #    parser.print_help()
    #    exit()
    # Matt: use this????
    # check number of arguments, verify values, etc.:
    #if len(args) != 2:
    #    parser.error('program takes 2 command-line arguments; '
    #                 '"%s" ignored.' % (args,))

    # further process settings & args if necessary

    return (settings, args)

def main(argv):
    (settings, args) = process_command_line(argv)
    debug(1, args )
    # get urls to all calendars on home page
    urls = get_all_current_schedules()
    # get url to current schedule
    #url = get_current_schedule()
    for url in urls:
        print url
        if url.endswith(".html"):
            # get list of every <td> objects (playdates) from url
            (playdates, eventyear) = extract_playdates(url)
            # parse list of playdate objects
            movielist = parse_playdates(playdates, eventyear)
            # print info
            debug(0, url )
            debug(0, get_page_mod_time(url) )
            write_ical(movielist, url)
            #for movie in movielist:
            #    print movie,"\n"

if __name__ == "__main__":
    status = main(sys.argv[1:])
    sys.exit(status)
