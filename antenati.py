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
import concurrent.futures
import urllib3
import click
import slugify
import humanize

def get_manifest_from_url(url):
    pool_manager = urllib3.PoolManager()
    http_reply = pool_manager.request('GET', url)
    manifest_url = None
    for line in http_reply.data.decode('utf-8').split('\n'):
        if 'manifestId' in line:
            url_pattern = re.search(r"'([A-Za-z0-9.:/-]*)'", line)
            manifest_url = url_pattern.group(1)
    if not manifest_url:
        raise RuntimeError(f'No Mirador manifest found at {url}')
    http_reply = pool_manager.request('GET', manifest_url)
    return json.loads(http_reply.data.decode('utf-8'))

def get_foldername_from_manifest(manifest):
    archive_label = manifest['label']
    archive_content_type = 'unknown'
    for metadata in manifest['metadata']:
        if metadata['label'] == 'Tipologia':
            archive_content_type = metadata['value']
    return slugify.slugify(f'{archive_label}-{archive_content_type}')

def check_folder(foldername):
    if os.path.exists(foldername):
        click.echo(f'Directory {foldername} already exists.')
        click.confirm('Do you want to proceed?', abort=True)
    else:
        os.mkdir(foldername)
    os.chdir(foldername)

def get_img_data(img_desc):
    img = {}
    label = slugify.slugify(img_desc['label'])
    img['url'] = img_desc['images'][0]['resource']['@id']
    img['filename'] = f'img_archive_{label}.jpg'
    return img

def run(img, pool):
    http_reply = pool.request_encode_url('GET', img['url'])
    with open(img['filename'], 'wb') as img_file:
        img_file.write(http_reply.data)
    http_reply_size = len(http_reply.data)
    return http_reply_size

def get_images(manifest):
    total_size = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        host = 'iiif-antenati.san.beniculturali.it'
        pool_http = urllib3.HTTPSConnectionPool(host, maxsize=10, block=True)
        canvases = manifest['sequences'][0]['canvases']
        img_list = [ get_img_data(i) for i in canvases ]
        future_img = { executor.submit(run, i, pool_http): i for i in img_list }
        for future in concurrent.futures.as_completed(future_img):
            img = future_img[future]
            filename = img['filename']
            try:
                size = future.result()
            except RuntimeError as exc:
                print(f'{filename} error ({exc})')
            else:
                total_size = total_size + size
                print(f'{filename} done ({humanize.naturalsize(size)})')
    return total_size
	
def print_result(total_size):
    print(f'Done. Total size: {humanize.naturalsize(total_size)}')

def main():

    # Get Mirador manifest from HTTP
    manifest = get_manifest_from_url(sys.argv[1])
	
    # Get folder name from metadata
    foldername = get_foldername_from_manifest(manifest)
	
    # Check if folder already exists and chdir to it
    check_folder(foldername)

    # Run
    total_size = get_images(manifest)

    # Done
    print_result(total_size)

if __name__ == '__main__':
    main()
