# antenati
A tool to download data from the *[Portale Antenati](http://www.antenati.san.beniculturali.it/)*, the genealogy digital archive maintained by the italian **Ministero per i beni e le attività culturali**.

Since the website tends to be pretty slow in the evening, we present a script to help the retrieval of the documents for your family tree. The script allows you to download **all the images of multiple archive at the same time** (launching multiple instance of the script), whithout any human action. Just launch the script, and have a coffee while it downloads all the stuff for you.


## Usage 
Just run the script putting as first argument the first page of a collection you want to download:

    ./antenati.py <link to the first page>

The files are put to a new folder named with the gallery ID (the number after the year in the URL) of the downloaded archive.

### Example:
In the website, navigate to the archive you want to download. For example, for the people born in Montalcino in 1832, you should find the page:

[http://dl.antenati.san.beniculturali.it/v/Archivio+di+Stato+di+Firenze/Stato+civile+della+restaurazione/Montalcino+provincia+di+Siena/Nati/1832/179/](http://dl.antenati.san.beniculturali.it/v/Archivio+di+Stato+di+Firenze/Stato+civile+della+restaurazione/Montalcino+provincia+di+Siena/Nati/1832/179/)

The, copy the link to the first page, and call the script with that link as argument:

    ./antenati.py http://dl.antenati.san.beniculturali.it/v/Archivio+di+Stato+di+Firenze/Stato+civile+della+restaurazione/Montalcino+provincia+di+Siena/Nati/1832/179/005178080_00303.jpg.html
