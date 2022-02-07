# antenati
A tool to download data from the *[Portale Antenati](http://www.antenati.san.beniculturali.it/)*, the genealogy digital archive maintained by the italian **Ministero per i beni e le attività culturali**.

Since the website tends to be pretty slow in the evening, we present a script to help the retrieval of the documents for your family tree. The script allows you to download **all the images of multiple archive at the same time** (launching multiple instance of the script), whithout any human action. Just launch the script, and have a coffee while it downloads all the stuff for you.

## Usage 
To install the dependencies, just use the classic:

    pip install -r requirements.txt

Then, run the script putting as first argument the first page of a collection you want to download:

    python3 antenati.py <URL of the album>

The files are put to a new folder named as *ARCHIVE-PLACE-YEAR-TYPE-ID* of the downloaded archive. For more options, see the help

    python3 antenati.py -h

### Example:
In the website, navigate to the archive you want to download. For example, for the people born in Viareggio in 1807 you should find the page:

[https://www.antenati.san.beniculturali.it/detail-registry/?s_id=19944549](https://www.antenati.san.beniculturali.it/detail-registry/?s_id=19944549)

Then, copy the link to the first page, and call the script with that link as argument:

    python3 antenati.py https://www.antenati.san.beniculturali.it/detail-registry/?s_id=19944549

The results will be placed in a folder named *archivio-di-stato-di-lucca-stato-civile-napoleonico-viareggio-1807-nati*.
