#!/usr/bin/env python3
"""
antenati.py: a tool to download data from the Portale Antenati
"""

__author__      = "Giovanni Cerretani"
__copyright__   = "Copyright (c) 2018, MIT License"

import urllib3
import html.parser
import json
import sys
import os
import re
import click
import threading
import slugify

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


class ImageHTMLParser():
    def __init__(self, pool):
        super().__init__()
        self._pool = pool
        self._threads = []
    def get_threads(self):
        return self._threads
    def get_file(self, url, name):
            filename = 'img_archive_' + name + '.jpg'
            t = Downloader(self._pool, url, filename)
            self._threads.append(t)


def main():

    connection_pool = urllib3.HTTPSConnectionPool('iiif-antenati.san.beniculturali.it', maxsize = 10)
    img_parser = ImageHTMLParser(connection_pool)
    
    pool_manager = urllib3.PoolManager()
    r = pool_manager.request('GET', sys.argv[1])

    manifest = None

    for line in r.data.decode('utf-8').split('\n'):
        if 'manifestId' in line:
            print(line)
            splitting = re.split('[\']', line)
            manifest = splitting[1]

    if not manifest:
        print('No manifest found')
        return

    r = pool_manager.request('GET', manifest)

    manifest_json = json.loads(r.data.decode('utf-8'))

    foldername = slugify.slugify(manifest_json['label'] + '-' + manifest_json['metadata'][1]['value'])
    
    if os.path.exists(foldername):
        if not click.confirm('Directory ' + foldername + ' already exists. Do you want to copy images to this directory?'):
            print('Exiting')
            return
    else:
        os.mkdir(foldername)
        
    os.chdir(foldername)

    for img_desc in manifest_json['sequences'][0]['canvases']:
        url = img_desc['images'][0]['resource']['@id']
        name = slugify.slugify(img_desc['label'])
        img_parser.get_file(url, name)
    
    for t in img_parser.get_threads():
        t.join()

if __name__ == '__main__':
    main()
