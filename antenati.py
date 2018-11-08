#!/usr/bin/env python
import urllib3
import HTMLParser
import sys
import re


class ImageHTMLParser(HTMLParser.HTMLParser):
    filename = None
    def set_filename(self, name):
        self.filename = "img_archive_"+name+".jpg"
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            url = attrs[0][1]
            r = urllib3.PoolManager().request('GET', url)
            print url, r.status, self.filename
            f = open(self.filename, 'wb')
            f.write(r.data)
            f.close()


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
    
    stop = False
    
    while not stop:
        stop = True
        print url_parser.get_next()
        r = urllib3.PoolManager().request('GET', url_parser.get_next())
        splitting = re.split('[_/?.]', url_parser.get_next())
        img_parser.set_filename(splitting[13] + "_" + splitting[14] + "_" + splitting[15])
    
        for line in r.data.split("\n"):
            if "zoomAntenati1" in line:
                img_parser.feed(line)
            if "successivo" in line:
                stop = False
                url_parser.feed(line)

if __name__ == "__main__":
    main()