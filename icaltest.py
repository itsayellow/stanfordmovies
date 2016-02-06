#!/usr/bin/env python

# test of ical writing

from icalendar import Calendar, Event
from datetime import datetime
import pytz

pac_tz = pytz.timezone('US/Pacific')

cal = Calendar()
cal.add('prodid', '-//Stanford Theatre Calendar//itsayellow@gmail.com//')
cal.add('version', '2.0')

#event = Event()
#event.add('summary', 'UTC Python meeting about calendaring')
#event.add('dtstart', datetime(2013,8,11,8,0,0,tzinfo=pytz.utc))
#event.add('dtend', datetime(2013,8,11,10,0,0,tzinfo=pytz.utc))
#event.add('dtstamp', datetime(2013,11,4,0,10,0,tzinfo=pytz.utc))
#event['uid'] = '20130815T101010/27346262376@mxm.dk'
#event.add('priority', 5)
#cal.add_component(event)

summary = "Roman Holiday (1953)"
description = "http://www.imdb.com/title/tt0046250/\n\nDirector: William Wyler\n\nWriters: Ian McLellan Hunter (screenplay), John Dighton (screenplay), 2 more credits\n\nCast:\nGregory Peck\nAudrey Hepburn\nEddie Albert\nHartley Power\nHarcourt Williams\nMargaret Rawlings\nTullio Carminati\nPaolo Carlini\nClaudio Ermelli\nPaola Borboni\nAlfredo Rizzo\nLaura Solari\nGorella Gori\n"
url = "http://www.imdb.com/title/tt0046250/"
location = "221 University Ave, Palo Alto, CA (Stanford Theatre)"

event = Event()
event.add('summary', summary)
event.add('description', description)
event.add('url', url )
event.add('location', location )
event.add('rrule',{'FREQ':'DAILY','COUNT':2})

event.add('dtstart', datetime(2013,8,11,8,0,0,tzinfo=pac_tz))
event.add('dtend', datetime(2013,8,11,10,0,0,tzinfo=pac_tz))
event.add('dtstamp', datetime(2013,8,11,0,10,0,tzinfo=pac_tz))
event['uid'] = '20130811T000001Z-22079-0@cutepuppiesandkittens.fake'

cal.add_component(event)

f = open('example.ics', 'wb')
f.write(cal.to_ical())
f.close()
