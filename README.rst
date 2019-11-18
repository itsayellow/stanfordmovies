movies2ical
===========

Utility to read current HTML calendar from stanfordtheatre.org and output ical file.

Installation
------------

::

    pipx install --spec git+https://github.com/itsayellow/stanfordmovies movies2ical

Periodically running in the background on macOS
-----------------------------------------------
Modify local.CheckStanfordMovieSchedule.plist, changing all "/INSERT/FULL/PATH/TO/"
strings to proper full paths to the various files or directories.

The directory called "Stanford Theatre Calendars" is the working directory where
output ical files will be placed

to test local.CheckStanfordMovieSchedule.plist, can remove::

        <key>StartCalendarInterval</key>
        <array>
        [...]
        </array>

and instead insert::

        <key>RunAtLoad</key>
        <true/>

so it runs right after loading

put local.CheckStanfordMovieSchedule.plist into ~/Library/LaunchAgents/

to put into launchd system
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    launchctl load ~/Library/LaunchAgents/local.CheckStanfordMovieSchedule.plist

To remove from launchd system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    launchctl unload ~/Library/LaunchAgents/local.CheckStanfordMovieSchedule.plist

To view configuration in launchd system
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    launchctl list local.CheckStanfordMovieSchedule
