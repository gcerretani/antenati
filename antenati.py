#!/usr/bin/env python
import urllib3
import HTMLParser
import sys
import os
import re
from threading import Thread


def threadedDownloader(url, filename):
    print "Downloading", filename
    r = urllib3.PoolManager().request('GET', url)
    f = open(filename, 'wb')
    f.write(r.data)
    f.close()


class ImageHTMLParser(HTMLParser.HTMLParser):
    filename = None
    threads = []
    def get_threads(self):
        return self.threads
    def set_filename(self, name):
        self.filename = "img_archive_" + name + ".jpg"
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            url = attrs[0][1]
            t = Thread(target = threadedDownloader, args = (url, self.filename))
            t.start()
            self.threads.append(t)


class UrlHTMLParser(HTMLParser.HTMLParser):
    next = ""
    def set_next(self, name):
        self.next = name
    def get_next(self):
        return self.next
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            if attrs[1][1] == "next":
                self.set_next("http://dl.antenati.san.beniculturali.it" + attrs[0][1])


def main():
        
    img_parser = ImageHTMLParser()
    url_parser = UrlHTMLParser()
    
    url_parser.set_next(sys.argv[1])
    splitting = re.split('[_/?.]', url_parser.get_next())
    
    str_comune = splitting[10].replace('+', '_')
    str_type = splitting[11].replace('+', '_')
    str_year = splitting[12].replace('+', '_')
    foldername = '_'.join([str_comune, str_type, str_year])
    
    if os.path.exists(foldername):
        print("Directory " + foldername + " already exists. Please remove it.")
        return
    
    os.mkdir(foldername)
    os.chdir(foldername)

    stop = False
    
    while not stop:
        stop = True
        r = urllib3.PoolManager().request('GET', url_parser.get_next())
        splitting = re.split('[_/?.]', url_parser.get_next())
        img_parser.set_filename(splitting[13] + "_" + splitting[14] + "_" + splitting[15])
    
        for line in r.data.split("\n"):
            if "zoomAntenati1" in line:
                img_parser.feed(line)
            if "successivo" in line:
                stop = False
                url_parser.feed(line)
                
    for t in img_parser.get_threads():
        t.join()

if __name__ == "__main__":
    main()
