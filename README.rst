movies2ical
===========
Utility to read current HTML calendar from stanfordtheatre.org and output ical file.

Periodically running in the background on macOS
-----------------------------------------------
Modify local.CheckStanfordMovieSchedule.plist, changing all "/INSERT/FULL/PATH/TO/"
strings to proper full paths to the various files or directories.

The directory called "Stanford Theatre Calendars" is the working directory where
output ical files will be placed

to test local.CheckStanfordMovieSchedule.plist, can remove
        <key>StartCalendarInterval</key>
        <array>
        [...]
        </array>
and instead insert
        <key>RunAtLoad</key>
        <true/>
so it runs right after loading

put local.CheckStanfordMovieSchedule.plist into ~/Library/LaunchAgents/

# to put into launchd system
launchctl load ~/Library/LaunchAgents/local.CheckStanfordMovieSchedule.plist

# to remove from launchd system
launchctl unload ~/Library/LaunchAgents/local.CheckStanfordMovieSchedule.plist
