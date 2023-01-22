# antenati
A tool to download data from the *[Portale Antenati](http://antenati.cultura.gov.it/)*, the genealogy digital archive maintained by the italian **Ministero per i beni e le attività culturali**.

Since the website tends to be pretty slow in the evening, we present a script to help the retrieval of the documents for your family tree. The script allows you to download **all the images of any archive at the same time**, without any human action. Just launch the script and have a coffee while it downloads all the stuff for you.

## Requirements
The software is written in Python 3 and tested with Python 3.7. On Windows the version on the Microsoft Store is fine, on Linux use your distribution package manager.

## Usage
Open your preferite terminal and change directory to where you've extracted the content of this repo. Then execute the following commands.

### Install the dependencies
The first time you will have to install the dependencies:

    pip install -r requirements.txt

### Run
To download the images of a gallery, execute the script passing the URL of a collection you want to download as argument:

    python3 antenati.py <URL of the album>

The files will be downloaded to a new folder named as *ARCHIVE-PLACE-YEAR-TYPE-ID* of the downloaded archive. For more options, see the help:

    python3 antenati.py -h

### Example:
In the website, navigate to the archive you want to download. For example, for the people born in Viareggio in 1807 you should find the page:

[https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x](https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x)

Then, copy the link to the first page, and call the script with that link as argument:

    python3 antenati.py https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x

The results will be placed in a folder named *archivio-di-stato-di-lucca-stato-civile-napoleonico-viareggio-1807-nati-19944549*.
