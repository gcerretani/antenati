#!/usr/bin/env python3
"""
antenati.py: a tool to download data from the Portale Antenati
"""

__author__      = "Giovanni Cerretani"
__copyright__   = "Copyright (c) 2021, MIT License"

import json
import sys
import os
import re
import threading
import urllib3
import click
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
        http_reply = self._pool.request_encode_url('GET', self._url)
        with open(self._filename, 'wb') as img_file:
            img_file.write(http_reply.data)
        print('Done ', self._filename)


class ImageGetter():
    def __init__(self):
        super().__init__()
        host = 'iiif-antenati.san.beniculturali.it'
        self._pool = urllib3.HTTPSConnectionPool(host, maxsize = 10, block = True)
        self._threads = []
    def wait(self):
        for thrd in self._threads:
            thrd.join()
    def get_file_on_thread(self, url, name):
        filename = 'img_archive_' + name + '.jpg'
        thrd = Downloader(self._pool, url, filename)
        self._threads.append(thrd)


def main():
    pool_manager = urllib3.PoolManager()
    http_reply = pool_manager.request('GET', sys.argv[1])

    # Get Mirador manifest from HTTP
    manifest_url = None
    for line in http_reply.data.decode('utf-8').split('\n'):
        if 'manifestId' in line:
            url_pattern = re.search(r"'([A-Za-z0-9.:/-]*)'", line)
            manifest_url = url_pattern.group(1)
    if not manifest_url:
        print('No manifest found')
        return
    http_reply = pool_manager.request('GET', manifest_url)
    manifest = json.loads(http_reply.data.decode('utf-8'))

    # Get folder name from metadata
    archive_label = manifest['label']
    archive_content_type = 'unknown'
    for metadata in manifest['metadata']:
        if metadata['label'] == 'Tipologia':
            archive_content_type = metadata['value']
    foldername = slugify.slugify(f'{archive_label}-{archive_content_type}')

    # Check if folder already exists and chdir to it
    if os.path.exists(foldername):
        click.echo(f'Directory {foldername} already exists.')
        if not click.confirm('Do you want to proceed?'):
            print('Aborting')
            return
    else:
        os.mkdir(foldername)
    os.chdir(foldername)

    # Download images
    img_getter = ImageGetter()
    for img_desc in manifest['sequences'][0]['canvases']:
        url = img_desc['images'][0]['resource']['@id']
        name = slugify.slugify(img_desc['label'])
        img_getter.get_file_on_thread(url, name)
    img_getter.wait()

    # Done
    print('Done')

if __name__ == '__main__':
    main()
