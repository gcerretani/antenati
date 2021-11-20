#!/usr/bin/env python3
"""
antenati.py: a tool to download data from the Portale Antenati
"""

__author__      = 'Giovanni Cerretani'
__copyright__   = 'Copyright (c) 2021, Giovanni Cerretani'
__license__     = 'MIT License'
__version__     = '2.1'

import argparse
import json
import os
import re
import concurrent.futures
import urllib3
import click
import slugify
import humanize

def get_mirador_manifest(url):
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

def generate_foldername(manifest):
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

def get_images(manifest, n_workers, n_connections):
    total_size = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
        host = 'iiif-antenati.san.beniculturali.it'
        pool_http = urllib3.HTTPSConnectionPool(host, maxsize=n_connections, block=True)
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

    # Parse arguments
    parser = argparse.ArgumentParser(
                description='a tool to download data from the Portale Antenati',
                formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('url', metavar='URL', type=str, help='url of the gallery page')
    parser.add_argument('-n', '--nthreads', type=int, help='max n. of threads', default=8)
    parser.add_argument('-c', '--nconn', type=int, help='max n. of connections', default=4)
    args = parser.parse_args()

    # Get Mirador manifest from HTTP
    manifest = get_mirador_manifest(args.url)

    # Get folder name from metadata
    foldername = generate_foldername(manifest)

    # Check if folder already exists and chdir to it
    check_folder(foldername)

    # Run
    total_size = get_images(manifest, args.nthreads, args.nconn)

    # Done
    print_result(total_size)

if __name__ == '__main__':
    main()
