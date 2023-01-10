# Istruzioni per principianti

## Windows
### Installare Python
Occorre Python 3 almeno alla versione 3.6. Il modo più veloce è passare dal Microsoft Store. Potete aprirlo e cercare "Python 3.10", o per semplicità [cliccare qui](https://www.microsoft.com/it-it/p/python-310/9pjpw5ldxlz5).

### Scaricare questo repository
Potete scaricare il contenuto di questo repository da [qui](https://github.com/gcerretani/antenati/archive/refs/heads/master.zip). Estraetene il contenuto, che dovrebbe chiamarsi **antenati-master**, da qualche parte, per esempio nella cartella dei Documenti.

### Aprire un terminale
Aprite un terminale. La PowerShell è la soluzione più semplice e moderna: cercate "Windows PowerShell" dal menu start ed apritela. Per cambiare la cartella di lavoro a quella dove avete scaricato il contenuto di questo repository, eseguite:

    cd $env:HOMEPATH\Documents\antenati-master

Controllate di essere nella cartella giusta. Eseguite:

    ls

e guardate che ci sia il contenuto di questo repository.

### Installare le dipendenze
Quindi, eseguite:

    pip install -r requirements.txt

Dovrebbe impiegare qualche secondo. Questa cosa va fatta solamente la prima volta, e serve a installare le dipendenze di questo programma. Le volte successive potete saltare questo passaggio

### Via!
Adesso siete pronti. Provate a scaricare un album copiando l'URL della pagina del Portale Antenati dopo a `python3 antenati.py`. Supponendo che siate interessati ai nati a Viareggio nel 1808, dovreste eseguire una cosa del genere:

    python3 antenati.py https://antenati.cultura.gov.it/ark:/12657/an_ua19944535/w9DWR8x

Buon divertimento!

## Linux
TODO

## macos
TODO
