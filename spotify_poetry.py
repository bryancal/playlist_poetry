# Spotify Poetry
# This is a simple script that takes an input poem (NOT case sensitive)
# and attempts to design a playlist of songs that spell out the message.
#
# Once a valid input poem/string is given,
# this program first generates the solution set of possible poems,
# and then identifies the unique set of phrases that exist in the solution set,
#
# Next, this program iterates through the set of possible poems, which are sorted by size,
# and attempts to find valid representations (e.g., an exact match song exists for each phrase).
# The algorithm for selecting the optimal playlist is biased towards shorter playlists,
# and can be described as follows:
#       - If a valid representation is found, search remaining reps. of equal length and take
#       - rep. w/ highest geometric average of popularity scores.
#
# INPUTS: Valid String/Poem 
# OUTPUTS: List of Spotify tracks in the following format
#        - Song name: <Name>, link to track: <URL>
#
# Note. While this has been tested, it is still in rough development
# Author: Bryan Callaway (8/26/13)

from urlparse import urlparse
import threading, multiprocessing
import sys, Queue, time, re, math
import urllib2
import xml.etree.cElementTree as ET
import itertools as it


# threaded_api(phrases, in_dict = dict(), nthreads = 2)
# multithreaded/parallelized function for Spotify API calls.
# Because of cost of page requests, we can speed up our API calls by
# threading them.  This program currently admits a maximum of 300 threads.
# One caveat is that if the network connection is unreliable, we may not
# be able to evaluate all possible configurations.
def threaded_api(phrases, in_dict = dict(), nthreads = 2):
    def worker(phrases, outdict):
        base_url = 'http://ws.spotify.com/search/1/track?q='
    
        for i in phrases:
            #phrase = '/search/1/track?q=' + re.sub('\s{1,}', '+', i)
            url = base_url + re.sub('\s{1,}', '+', i)
            try:
                request = urllib2.Request(url, headers={"Accept" : "application/xml"})
                outdict[i] = urllib2.urlopen(request)
            except:
                print 'Connection problem observed.  Results may be affected.'
                continue

        return outdict

    # Set max threads at 300.
    if nthreads > 300:
        nthreads = 300

    # Generate chunk size.
    chunksize = int(math.ceil(len(phrases)) / float(nthreads))
    threads = list()
    outs = [in_dict for i in range(nthreads)]

    for i in range(nthreads - 1):
        t = threading.Thread(target = worker, args = (phrases[chunksize * i: chunksize * (i + 1)], outs[i]))
        threads.append(t)
        t.start()

    # Pass chunk + remainder to final thread.  This could be improved upon, but should be OK for now.
    t = threading.Thread(target = worker, args = (phrases[(nthreads - 1) * chunksize:], outs[nthreads - 1]))
    threads.append(t)
    t.start()

    for t in threads:
        t.join()

    return {k: v for out_d in outs for k, v in out_d.iteritems()}

# gen_possible_poems(phrase_set)
# Computes all feasible poem representations (solution set).
# Returns a list of tuples for each possible poem and its length.
# By construction, return list is sorted in ascending order of length.
def gen_possible_poems(phrase_set):
    #append unmodified poem
    possible_poems = list()
    possible_poems.append(([phrase_set], len([phrase_set])))
    words = phrase_set.split()
    ns = range(1, len(words)) # n = 1..(n-1)
    for n in ns: # split into 2, 3, 4, ..., n parts.
        for idxs in it.combinations(ns, n):
            phrase = [' '.join(words[i:j]) for i, j in zip((0,) + idxs, idxs + (None,))]
            possible_poems.append((list(phrase), len(phrase)))

    return possible_poems

# Takes a list of phrases and removes duplicates.
def unique(poss_poems):
   seen = {}
   pos = 0
   for i in poss_poems:
       for j in i[0]:
           if j not in seen:
               seen[j] = True
               pos += 1
   return list(seen.keys())

# Poem class.
# Class for representing and evaluating possible poems.
# This is a placeholder for possible multi-processing, which could build on this.
class Poem:

    def __init__(self, poem):
        self.poem = poem[0] # poem is a list of phrases
        self.song_count = poem[1]
        self.playlist = list()
        self.score = 0

    # Evaluates whether phrase is exact match of target.
    # Returns boolean for status.
    def exact_match(self, target, test):
        if target.lower() == test.lower():
            return True
        else:
            return False

    # Processes instance of a possible poem.    
    def process_poem(self, phrase_pages, phrase_data):

        # Compile regex needed.
        p = re.compile(r'(\{\S{0,}\})(\S{0,})')
        scores = list()
        valid = True
        for line in self.poem:
            # Check if we have already found the key.
            if phrase_data.has_key(line):
                self.playlist.append(phrase_data[line])
                _tup = phrase_data[line]
                if _tup[2] == False:
                    valid = False
                scores.append(_tup[1])
            else:
                page = phrase_pages[line]
            
                # Now parse out page and append to data dictionary.
                try:
                    tree = ET.parse(page)
                    root = tree.getroot()
                except:
                    phrase_data[line] = ('', 0.0, False, line)
                    valid = False
                
                xlmns = filter(None, p.split(root.tag))[0]
                _tag = xlmns + 'track'

                # Iterate until we find an exact phrase match, or exhaust list of tracks.
                for elem in tree.iter(tag = _tag):
                    if self.exact_match(line, elem.find(xlmns + 'name').text):
                        _code = elem.attrib['href'].split(':')[2]
                        _score = float(elem.find(xlmns + 'popularity').text)
                        scores.append(_score)
                        phrase_tup = (_code, _score, True, line)
                        phrase_data[line] = phrase_tup
                        self.playlist.append(phrase_data[line])
                        scores.append(phrase_tup[1])
                        break

                if phrase_data.has_key(line) == False:
                    phrase_data[line] = ('', 0.0, False, line)
                    valid = False
                
        if valid:
            self.rank_score(scores)
            return [True, phrase_data]
        else:
            return [False, phrase_data]

    # Computes an alternate rank score as 
    # the geometric average of the popularity scores of songs in the poem
    # divided by the playlist length squared.
    def rank_score(self, scores):
        self.score = (reduce(lambda x, y: x * y, scores) ** (1.0 / self.song_count)) / (self.song_count ** 2)


# build_playlist(phrase_set)
# Three tasks:
# (1) Build out solution set of playlists
# (2) Pull all phrase tracks from Spotify API (threaded/parallelized)
# (3) Evaluate poems based on algorithm:
#       - If a valid representation is found, search remaining reps. of equal length and take
#       - rep. w/ highest geometric average (popularity).
# Returns a boolean indicating whether representation was found.
def build_playlist(phrase_set):

    poems = gen_possible_poems(phrase_set)
    phrases = unique(poems)
    song_pages = threaded_api(phrases, {}, len(phrases))
    song_data = dict()
    # Base URL for song tracks.  Will be used in final output.
    song_base_url = 'https://play.spotify.com/track/'
    # Place holders for top playlist.
    best_play_len = sys.maxint
    best_play = None

    # Iterate over phrases.  If we find a valid phrase, we continue iterating
    # over only the phrases that are of an equivalent length (favor small poems)
    # and pick the option that yields the highest average score.
    for _poem in poems:

        # Check if we keep going.
        if _poem[1] <= best_play_len:
            p = Poem(_poem)
            valid, song_data = p.process_poem(song_pages, song_data)
            # Update info if we find valid poem.
            if valid == True:
                # If none found yet, set this as best
                if best_play == None:
                    best_play = p
                    best_play_len = p.song_count
                else:
                    # If playlist of equivalent length has better score set that as new playlist
                    # Note that our score function decreases in playlist length,
                    # since we prefer shorter playlists.
                    try:
                        if p.score > best_play.score:
                            best_play = p
                    except:
                            continue
            else:
                continue
        else:
            # We break loop only after we selected top poem based on algorithm.
            break

    if best_play != None:
        print 'The chosen playlist is the following:'
        
        for song in best_play.playlist:
            print 'Song name: ' + song[3] + ', link to track: ' + song_base_url + song[0]
        return True
    else:
        return False
    
# Evaluation and execution of poem builder.
if __name__ == '__main__':
    poem_found = False
    regex = re.compile(r'y(es)?$', flags=re.IGNORECASE)

    # Optional iteration if no results found.
    while poem_found == False:
        # Iterate till a valid input is entered.
        while True == True:
            phrase_set = raw_input('Please enter a poem: ').lower()
            if len(phrase_set) > 0:
                break

        # Process poems and see if valid representation exists.
        poem_found = build_playlist(phrase_set)

        if poem_found == False:
            _input = raw_input('Unable to find valid representation.  Would you like to try a new phrase? (y/n) ').lower()
            if regex.match(_input):
                continue
            else:
                poem_found = True
            

        




