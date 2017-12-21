#!/usr/bin/python

################################################################################
# Copyright         (2017)
# COPYRIGHT HOLDER  (mxdev)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
################################################################################

from HTMLParser import HTMLParser
from optparse import OptionParser
import subprocess
import ast
import shutil
import timeit


parser = OptionParser()
parser.add_option("-q", "--query", action="store_true", dest="queryKijiji", default=False, help="Queries New Ads and Updates DB")
parser.add_option("-r", "--read", action="store_true", dest="readDb", default=False, help="Returns new Ad entries in the database")
parser.add_option("-a", "--all", action="store_true", dest="readAll", default=False, help="If reading, will return all entries in database")
parser.add_option("-m", "--markread", action="store_true", dest="markRead", default=False, help="Will mark all unread messages in the database as read")
parser.add_option("-b", "--recover", action="store_true", dest="recoverDb", default=False, help="Will attempt to recover the database by using the backup version")

(options, args) = parser.parse_args()

# Database file of all ads
dbFile = "db.dict"

# Specific query for adding specific radius on kijiji
endFile = "c110l1700212r60.0"

# Base service
baseUrl = "https://www.kijiji.ca"
# Tools in Kitchener/Waterloo
secUrl = "/b-tool/kitchener-waterloo"
# Parameter to add in for additional pages
pageUrl = "/page-"
endUrl = "/" + endFile

# Statistics to determine where time has been spent
dbReadTime = 0.0
dbEvalTime = 0.0
dbWriteTime = 0.0
dbQueryParseTime = 0.0
dbQueryCurlTime = 0.0
dbReadOpTime = 0.0

adDictionary = {}

# HTML Parser State machine
class MyHTMLParser( HTMLParser ):

    # Keeps track of the current state of the state machine. 
    adState = 0

    # Keeps track of how many HTML divisions we are deep
    divLevel = 0

    # Keeps track of the number of new ads we got for this page
    newAds = 0

    # Keeps track of the final amount of consecutive ads. This determines exit conditions to
    # stop querying
    lastExistingAds = 0

    # There are the various ad states. We determine what state we are in based upon the start tag.
    # The state machine is called again with the actual data, so we need some reference on what to do
    # with the received data
    AD_STATE_NONE = 0
    AD_STATE_BASE = 1
    AD_STATE_PRICE = 2
    AD_STATE_TITLE = 3
    AD_STATE_DISTANCE = 4
    AD_STATE_LOCATION = 5
    AD_STATE_DESCRIPTION = 6

    # Dictionary element of the current ad being processed
    currentAd = {}

    # Reset the entire state machine for handling a new html page
    def adReset( self ):
        self.adState = 0
        self.divLevel = 0
        self.newAds = 0
        self.currentAd = {}
        self.lastExistingAds = 0

    # Accessor function for number of ads received during html parsing
    def getNewAds( self ):
        return self.newAds

    # Accessor function for number of consecutive known ads
    def getLastExistingAds( self ):
        return self.lastExistingAds

    # This initializes an ad with the initial information provided in the "data-ad-id" starttag
    # Captures the unique id, initializes as unread, grabs the ad url
    def PrepareAndCreateAd( self,  attrs ):
        #print "Printing Attributes:"
        self.adState = self.AD_STATE_BASE
        for attr in attrs:
            if( "data-ad-id" in attr[0] ):
                self.currentAd['id'] = attr[1].strip().encode('ascii','replace')
                self.currentAd['read'] = False
            elif( "data-vip-url" in attr[0] ):
                self.currentAd['url'] = baseUrl + attr[1].strip().encode('ascii','replace')
            elif( "class" in attr[0] ):
                # Only give regular ads. This throws away paid ads on kijiji for ebay/etc
                if( "regular-ad" not in attr[1] ):
                    self.AbortCurrentAd()
                    return

    # Finalizes the current ad. This means verifying that it doesn't already exist in the database, replacing
    # ads that have changed/updated and reseting the state
    def FinalizeCurrentAd( self ):
        if (self.currentAd['id'] in adDictionary) and (adDictionary[self.currentAd['id']]['title'] == self.currentAd['title']):
            print "Ad already exists: " + self.currentAd['id']
            #print "\tCurrent Title: [" + adDictionary[self.currentAd['id']]['title'] + "] Previous Title [" + self.currentAd['title'] + "]"
            self.lastExistingAds = self.lastExistingAds + 1
        else:
            if self.currentAd['id'] in adDictionary:
                print "************Replacing existing ad*****************: " + self.currentAd['id']
            else:
                print "New ad found: " + self.currentAd['id']
            self.newAds = self.newAds + 1
            self.lastExistingAds = 0
            adDictionary[self.currentAd['id']] = self.currentAd
            
        self.currentAd = {}
        self.adState = self.AD_STATE_NONE

    # Aborts current ad and resets the state
    def AbortCurrentAd( self ):
        print "Aborting Ad"
        self.currentAd = {}
        self.adState = self.AD_STATE_NONE

    # Handles an html starttag. Each tag is the beginning of a section <> and contains several attributes.
    # We are looking for "data-ad-id" tag to start an ad.
    # Once we are in an ad, we set the current state depending on what the tag is telling us is in the data section
    def handle_starttag( self, tag, attrs ):
        #print "Start Tag ", tag
        if( "div" in tag ):
            if( self.adState == self.AD_STATE_NONE ):
                for attr in attrs:
                    if( "data-ad-id" in attr ):
                        self.PrepareAndCreateAd( attrs )
            elif( self.adState == self.AD_STATE_BASE ):
                for attr in attrs:
                    if( "price" in attr[1] ):
                        #print "Found price in " + str(attr)
                        self.adState = self.AD_STATE_PRICE
                    elif( "title" in attr[1] ):
                        #print "Found title in " + str(attr)
                        self.adState = self.AD_STATE_TITLE
                    elif( "distance" in attr[1] ):
                        #print "Found distance in " + str(attr)
                        self.adState = self.AD_STATE_DISTANCE
                    elif( "location" in attr[1] ):
                        #print "Found location in " + str(attr)
                        self.adState = self.AD_STATE_LOCATION
                    elif( "description" in attr[1] ):
                        #print "Found descriptionM in " + str(attr)
                        self.adState = self.AD_STATE_DESCRIPTION

            # Keep track of the current division level. We use this to know when we have reached the end of the ad
            if( self.adState != self.AD_STATE_NONE ):
                self.divLevel = self.divLevel + 1

    # The endtag is currently only used to determine when we have reached the end of the current ad to finalize it.
    def handle_endtag( self, tag ):
        #print "End Tag " , tag
        if( "div" in tag and self.adState != self.AD_STATE_NONE ):
            self.divLevel = self.divLevel - 1
            #print "Reducing the div leve [%d]" % self.divLevel
            if( self.divLevel == 0 ):
                self.FinalizeCurrentAd( )

    # Handles the content that is contained within a tag. Populate the current ad dictionary with the content
    # depending on the state gathered from the starttag.
    def handle_data( self, data ):
        if( len(data.strip()) > 0 ):
            if( self.adState == self.AD_STATE_PRICE ):
                self.currentAd['price'] = data.strip().encode('ascii','replace')
                self.adState = self.AD_STATE_BASE
            elif( self.adState == self.AD_STATE_TITLE ):
                self.currentAd['title'] = data.strip().encode('ascii','replace')
                self.adState = self.AD_STATE_BASE
            elif( self.adState == self.AD_STATE_DISTANCE ):
                self.currentAd['distance'] = data.strip().encode('ascii','replace')
                self.adState = self.AD_STATE_BASE
            elif( self.adState == self.AD_STATE_LOCATION ):
                self.currentAd['location'] = data.strip().encode('ascii','replace')
                self.adState = self.AD_STATE_BASE
            elif( self.adState == self.AD_STATE_DESCRIPTION ):
                self.currentAd['description'] = data.strip().encode('ascii','replace')
                self.adState = self.AD_STATE_BASE


# Imports the current database of ads and evaluates the content.
def importDb( db ):
    global dbReadTime
    global dbEvalTime

    readDb = {}
    try:
        with open( db, 'r' ) as f:
            start_time = timeit.default_timer()
            s = f.read()
            dbReadTime = timeit.default_timer() - start_time
            
            start_time = timeit.default_timer()
            readDb = ast.literal_eval( s )
            dbEvalTime = timeit.default_timer() - start_time
    except: 
        print "Database file " + db + " doesn't exist. Creating now"
        f = open( db, 'w' )
        f.write( str(readDb) )
        f.close()

    return readDb

# Writes the updated database back to file. Move the existing database to a backup so
# we have atleast one step back incase of failure
def writeDb( db ):
    global dbWriteTime
    start_time = timeit.default_timer()

    shutil.move( db, db+".bak" )
    f = open( db, 'w' )
    f.write( str(adDictionary) )
    f.close()

    dbWriteTime = timeit.default_timer() - start_time

# Builds the kijiji url to request a certain page. page-1 is just base url. All other 
# pages add in an addition url parameter. Returns the html of the specific page
def getPageNum( page ):
    if( page == 1 ):
        url = baseUrl + secUrl + endUrl
    else:
        url = baseUrl + secUrl + pageUrl + str(page) + endUrl

    print "Getting url: " + url
    # TODO Right now we are calling curl directly as a subprocess and blocking until it has completed.
    # This sort of makes it linux specific. Maybe look into different ways of getting the page?
    # Maybe something built in to python?
    data = subprocess.check_output(["curl", url])
    return data

# Mainline
if __name__== "__main__":
    pageNum = 1
    lastExistingAds = 0
    totalNewAds = 0

    totalTime = timeit.default_timer()

    # TODO Add in recovery option which takes the backup database instead of the default database
    # TODO Option to discard old ads to keep the database from getting too big. Maybe just keep the id and marked as read. Everything else can be trimmed
    # TODO Website output? Could put the new ads as a series of websites so I can access remotely. Could grab and link the images as well
    #       Also need to factor how I am going to get the queried, and read information
    # TODO Could save some data by stopping when several consecutive old ads instead of getting the next page.
    # TODO Several backups that get cycled?
    # TODO Clean up the database, after reading content, we only care about the unique identifiers 

    # Read in the current database of ads
    adDictionary = importDb( dbFile )

    # If the query option has been selected, look for new ads
    if options.queryKijiji:
        start_time = timeit.default_timer()
        
        # Keep requesting ads until we have reached 10 pages, or the final two
        # ads we got are known
        while (lastExistingAds <= 2) and (pageNum <= 10):
            start_time = timeit.default_timer()

            # Get the html for the specific page
            data = getPageNum( pageNum )

            # The html page returns data in unicode, which the HTML Parser can't handle
            # replace all unknown characters and convert to ascii.
            data = data.decode('ascii','replace')
            dbQueryCurlTime = dbQueryCurlTime + timeit.default_timer() - start_time

            start_time = timeit.default_timer()
    
            # Parse the contents of the received HTML page
            parser = MyHTMLParser()
            parser.feed( data )
    
            # Keep track of the stats from the html parsing
            newAds = parser.getNewAds()
            lastExistingAds = parser.getLastExistingAds()
            totalNewAds = totalNewAds + newAds
            pageNum = pageNum + 1
            parser.adReset()
            print "We got [%d] new ads" % (newAds)

            dbQueryParseTime = dbQueryParseTime + timeit.default_timer() - start_time
            

    # Option to read database and return new ads
    if options.readDb:
        start_time = timeit.default_timer()

        # Iterate through all ads in the dictionary. 
        # TODO This is far from the best way of doing it. Not an issue yet...
        for ad in adDictionary:
            # Option to dump every single ad...
            # Otherwise, only dump the ads that are currently unread
            if options.readAll is False:
                if adDictionary[ad]['read']:
                    continue
                
            # If we are marking items as read, do so. Otherwise we can query new ads until
            # we are done with them.
            if options.markRead:
                adDictionary[ad]['read'] = True

            # Initialize and extract all the contents from the dictionary element
            title = "N\\A"
            price = "N\\A"
            location = "N\\A"
            distance = "N\\A"
            url = "N\\A"
            description = "N\\A"

            if 'title' in adDictionary[ad]:
                title = adDictionary[ad]['title']

            if 'price' in adDictionary[ad]:
                price = adDictionary[ad]['price']

            if 'location' in adDictionary[ad]:
                location = adDictionary[ad]['location']

            if 'distance' in adDictionary[ad]:
                distance = adDictionary[ad]['distance']

            if 'url' in adDictionary[ad]:
                url = adDictionary[ad]['url']

            if 'description' in adDictionary[ad]:
                description = adDictionary[ad]['description']

            # Print out the contents of the ads
            print title + "\t" + price
            print "\t" + location + "\t" + distance + "\t" + ad
            print "\t" + url
            print "\t" + description
            print ""
        dbReadOpTime = timeit.default_timer() - start_time

    if totalNewAds is not 0:
        print "We got a total of [%d] new ads" % totalNewAds

    writeDb( dbFile )

    print "Total Time [%f]\n\tReading Database [%f]\n\tEvaluating Data [%f]\n\tWriting Database [%f]\n\tQuery Curl Time [%f]\n\tQuery Parse Time [%f]\n\tRead Operation Time [%f]" % (timeit.default_timer() - totalTime, dbReadTime, dbEvalTime, dbWriteTime, dbQueryCurlTime, dbQueryParseTime, dbReadOpTime)

