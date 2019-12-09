#!/usr/bin/env python3
"""
antenati.py: a tool to download data from the Portale Antenati
"""

__author__      = "Giovanni Cerretani"
__copyright__   = "Copyright (c) 2018, MIT License"

import urllib3
import html.parser
import sys
import os
import re
import click
import threading


class Downloader(threading.Thread):
    def __init__ (self, pool, url, filename):
        super().__init__(target = self.run)
        self._pool = pool
        self._url = url
        self._filename = filename
        self.start()
    def run(self):
        print('Downloading ', self._filename)
        r = self._pool.request_encode_url('GET', self._url)
        with open(self._filename, 'wb') as f:
            f.write(r.data)
        print('Done ', self._filename)


class ImageHTMLParser(html.parser.HTMLParser):
    def __init__(self, pool):
        super().__init__()
        self._pool = pool
        self._filename = None
        self._threads = []
    def get_threads(self):
        return self._threads
    def set_filename(self, name):
        self._filename = 'img_archive_' + name + '.jpg'
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attr_dict = dict(attrs)
            url = attr_dict['href']
            t = Downloader(self._pool, url, self._filename)
            self._threads.append(t)


class UrlHTMLParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self._next = None
    def set_next(self, next):
        self._next = next
    def get_next(self):
        return self._next
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attr_dict = dict(attrs)
            if attr_dict['class'] == 'next':
                url = attr_dict['href']
                self._next = url


def main():
    connection_pool = urllib3.HTTPConnectionPool('dl.antenati.san.beniculturali.it', maxsize = 10)
    img_parser = ImageHTMLParser(connection_pool)
    url_parser = UrlHTMLParser()
    
    url_parser.set_next(sys.argv[1])
    
    splitting = re.split('[_/?.]', url_parser.get_next())
    
    html_element = splitting.index('html')
    gallery_name_elements = splitting[10 : html_element - 3]
    foldername = '_'.join(gallery_name_elements).replace('+', '_')
    
    if os.path.exists(foldername):
        if not click.confirm('Directory ' + foldername + ' already exists. Do you want to copy images to this directory?'):
            print('Exiting')
            return
    else:
        os.mkdir(foldername)
        
    os.chdir(foldername)

    stop = False
    
    while not stop:
        stop = True
        r = connection_pool.request('GET', url_parser.get_next())
        splitting = re.split('[_/?.]', url_parser.get_next())
        html_element = splitting.index('html')
        file_name_elements = splitting[html_element - 3 : html_element - 1]
        local_filename = '_'.join(file_name_elements)
        img_parser.set_filename(local_filename)
    
        for line in r.data.decode('utf-8').split('\n'):
            if 'zoomAntenati1' in line:
                img_parser.feed(line)
            if 'successivo' in line:
                stop = False
                url_parser.feed(line)
                
    for t in img_parser.get_threads():
        t.join()

if __name__ == '__main__':
    main()
