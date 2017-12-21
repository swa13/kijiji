# kijiji
Tool for interacting / automating Kijiji

Currently set up to request pages from Kijiji depending on a specific ad query.
The returned HTML is parsed and extracted into a database which tracks what ads
you have read.

Current usage is:

Query Kijiji
    $ ./kijiji -q

Get New Ads
    $ ./kijiji -rm > out

Options Help 
    $ ./kijiji -h

Platforms:
This has currently only been tested and verified on Debian 8.0. I'm not planning
on modifying to add support for anything beyond what I use this for.

Modifying Script:
Modify the URL to change to the specific query and location you have for kijiji should
be all that is required.
