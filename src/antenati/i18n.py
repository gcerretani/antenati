# SPDX-FileCopyrightText: 2018 Giovanni Cerretani
# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal interface localisation for the CLI and GUI.

Catalogs are plain dicts keyed by the English source string, so no build
step or data files are needed (the PyInstaller one-file build keeps working
unchanged). Only user-interface strings are translated: exception messages
raised by the download core stay in English so they remain searchable in
bug reports, and CLI keywords (``resume``, ``full``, ...) are never
translated.

The language is detected once, lazily, from ``ANTENATI_LANG``, the POSIX
locale environment variables and finally the operating system settings.
"""

from __future__ import annotations

import locale
import os
import subprocess
import sys

SUPPORTED = ('en', 'it', 'fr', 'es')
DEFAULT_LANGUAGE = 'en'

_current: str | None = None


def _normalize(value: str | None) -> str | None:
    """Map a locale name (``it_IT.UTF-8``, ``fr-CA``, ``Italian_Italy``) to a supported code."""
    if not value:
        return None
    value = value.strip().lower()
    if value in {'c', 'posix'}:
        return None
    code = value.replace('-', '_').split('.')[0].split('@')[0].split('_')[0]
    if code in SUPPORTED:
        return code
    # Windows-style names returned by locale.getlocale(), e.g. 'Italian_Italy'.
    for name, lang in (('english', 'en'), ('italian', 'it'), ('french', 'fr'), ('spanish', 'es')):
        if value.startswith(name):
            return lang
    return None


def _windows_language() -> str | None:
    try:
        import ctypes

        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return None
    return _normalize(locale.windows_locale.get(lcid))


def _macos_language() -> str | None:
    try:
        result = subprocess.run(['defaults', 'read', '-g', 'AppleLocale'], capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return _normalize(result.stdout)


def detect_language() -> str:
    """Return the best supported language code for the current user."""
    override = os.environ.get('ANTENATI_LANG')
    if override:
        return _normalize(override) or DEFAULT_LANGUAGE

    # POSIX precedence: LANGUAGE (a colon-separated list), LC_ALL, LC_MESSAGES, LANG.
    for var in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        raw = os.environ.get(var)
        if not raw:
            continue
        for candidate in raw.split(':'):
            lang = _normalize(candidate)
            if lang:
                return lang
        if var != 'LANGUAGE':
            # An explicit but unsupported locale (e.g. de_DE) means English.
            return DEFAULT_LANGUAGE

    if sys.platform == 'win32':
        lang = _windows_language()
    elif sys.platform == 'darwin':
        lang = _macos_language()
    else:
        lang = None
    if lang is None:
        try:
            lang = _normalize(locale.getlocale()[0])
        except ValueError:
            lang = None
    return lang or DEFAULT_LANGUAGE


def set_language(lang: str | None) -> None:
    """Force a language (``None`` re-runs detection on next use)."""
    global _current
    _current = _normalize(lang) if lang else None


def get_language() -> str:
    global _current
    if _current is None:
        _current = detect_language()
    return _current


def _(message: str, /, **kwargs: object) -> str:
    """Translate ``message`` into the current language, then ``str.format`` it with ``kwargs``."""
    translated = CATALOGS.get(get_language(), {}).get(message, message)
    return translated.format(**kwargs) if kwargs else translated


# fmt: off
# ruff: noqa: E501 (translated catalog entries are kept on one line each)
_IT: dict[str, str] = {
    # Shared
    'Download image galleries from the Portale Antenati': 'Scarica le gallerie di immagini dal Portale Antenati',
    'Support this project': 'Sostieni il progetto',
    'Gallery or manifest URL': 'URL della galleria o del manifest',
    'Loading register metadata…': 'Caricamento dei metadati del registro…',
    'Existing output': 'Destinazione esistente',
    'Download complete': 'Download completato',
    'Download cancelled': 'Download annullato',
    'Download incomplete': 'Download incompleto',
    'Download': 'Scarica',
    'Error': 'Errore',
    # GUI
    'File': 'File',
    'Portale Antenati Website': 'Sito del Portale Antenati',
    'Project Website': 'Sito del progetto',
    'About': 'Informazioni',
    'Download options': 'Opzioni di download',
    'Size (px)': 'Dimensione (px)',
    'Maximum size': 'Dimensione massima',
    'First page': 'Prima pagina',
    'Zero-based index': 'Indice a partire da 0',
    'Last page': 'Ultima pagina',
    'Exclusive; leave empty for all remaining pages': 'Esclusa; lascia vuoto per tutte le pagine restanti',
    'Workers': 'Download paralleli',
    'Concurrent image downloads': 'Immagini scaricate contemporaneamente',
    'Filenames': 'Nomi dei file',
    'Include archive/image IDs': 'Includi ID di archivio e immagine',
    'Existing files': 'File esistenti',
    'Verified resume is recommended when reusing a destination': 'Se riusi una destinazione è consigliato «resume» (ripresa verificata)',
    'Destination': 'Destinazione',
    'Save in': 'Salva in',
    'Change…': 'Cambia…',
    'Create a separate folder for each register (recommended)': 'Crea una cartella separata per ogni registro (consigliato)',
    'Register folder': 'Cartella del registro',
    'Will be determined from metadata': 'Verrà determinata dai metadati',
    '(same as Save in)': '(uguale a «Salva in»)',
    'Cancel': 'Annulla',
    'Ready': 'Pronto',
    'Open folder': 'Apri cartella',
    'Folder unavailable': 'Cartella non disponibile',
    'The destination folder does not exist yet.': 'La cartella di destinazione non esiste ancora.',
    'The destination already contains files.\n\nYes: resume and verify existing downloads (recommended)\nNo: choose another action\nCancel: stop':
        'La destinazione contiene già dei file.\n\nSì: riprendi e verifica i download esistenti (consigliato)\nNo: scegli un\'altra azione\nAnnulla: interrompi',
    'Overwrite planned files?\n\nYes: overwrite\nNo: skip verified files and refuse ambiguous files\nCancel: stop':
        'Sovrascrivere i file previsti?\n\nSì: sovrascrivi\nNo: salta i file verificati e rifiuta quelli ambigui\nAnnulla: interrompi',
    'Please enter a valid URL.': 'Inserisci un URL valido.',
    'Resolving…': 'Risoluzione…',
    'Cancelling…': 'Annullamento…',
    'Preparing output…': 'Preparazione della destinazione…',
    'Planning download…': 'Pianificazione del download…',
    'Downloading {completed}/{total} pages…': 'Download di {completed}/{total} pagine…',
    'Downloaded {completed}, reused {skipped}. New data: {size}\n\nSaved to:\n{output}':
        'Scaricate {completed}, riutilizzate {skipped}. Nuovi dati: {size}\n\nSalvate in:\n{output}',
    'Completed {completed}/{expected}; failed {failed}.\n{details}': 'Completate {completed}/{expected}; fallite {failed}.\n{details}',
    'Cancelled': 'Annullato',
    'Download cancelled after {completed}/{expected} pages.': 'Download annullato dopo {completed}/{expected} pagine.',
    'Download failed': 'Download non riuscito',
    'Enter a gallery URL to preview the register.': "Inserisci l'URL di una galleria per vedere l'anteprima del registro.",
    # CLI
    'URL of the gallery page or its IIIF manifest': 'URL della pagina della galleria o del suo manifest IIIF',
    'Image size in pixels; 0 means full size': 'Dimensione dell\'immagine in pixel; 0 indica la dimensione massima',
    'Maximum number of concurrent download workers (--nthreads is a deprecated alias)':
        'Numero massimo di download paralleli (--nthreads è un alias deprecato)',
    'First image to download': 'Prima immagine da scaricare',
    'Exclusive end index: first image NOT to download': 'Indice finale escluso: prima immagine da NON scaricare',
    'Include archive and image IDs in saved file names': 'Includi gli ID di archivio e immagine nei nomi dei file',
    'Exact output directory (default: generated archive directory)': 'Cartella di destinazione esatta (predefinita: generata dall\'archivio)',
    'How to handle an existing output directory': 'Come gestire una cartella di destinazione già esistente',
    'Show the resolved download plan without writing image files': 'Mostra il piano di download senza scrivere immagini',
    'Output format: text or machine-readable JSON': 'Formato di output: testo o JSON leggibile da programmi',
    'Show version and exit': 'Mostra la versione ed esci',
    'Increase logging verbosity; repeat for DEBUG logging and full tracebacks': 'Aumenta il dettaglio dei log; ripeti per il livello DEBUG e i traceback completi',
    'URL is required with --format json.': 'L\'URL è obbligatorio con --format json.',
    'URL is required outside an interactive terminal.': 'L\'URL è obbligatorio fuori da un terminale interattivo.',
    'Output directory already exists and is not empty: {directory}. Choose an explicit --existing policy when using --format json.':
        'La cartella di destinazione esiste già e non è vuota: {directory}. Con --format json scegli una politica --existing esplicita.',
    'Policy': 'Politica',
    'Choose one of: resume, overwrite, skip, cancel.': 'Scegli tra: resume, overwrite, skip, cancel.',
    'Value must be >= {minimum}.': 'Il valore deve essere >= {minimum}.',
    'Pages [all/range]': 'Pagine [all/range]',
    'First image (0-based)': 'Prima immagine (da 0)',
    'Last image (exclusive)': 'Ultima immagine (esclusa)',
    'Image size [full/3000/2000/1000/custom]': 'Dimensione immagine [full/3000/2000/1000/custom]',
    'Image size in pixels': 'Dimensione immagine in pixel',
    'Choose full, 3000, 2000, 1000, or custom.': 'Scegli full, 3000, 2000, 1000 o custom.',
    'image size': 'dimensione immagine',
    'Output directory': 'Cartella di destinazione',
    'Start download?': 'Avviare il download?',
    'Cancelled by user.': 'Annullato dall\'utente.',
    'Downloading': 'Download',
    'Register': 'Registro',
    '{count} pages': '{count} pagine',
    'Verify and reuse valid downloads': 'Verifica e riusa i download validi',
    'recommended': 'consigliato',
    'Download again and replace planned files': 'Scarica di nuovo e sostituisci i file previsti',
    'Reuse verified files; refuse ambiguous existing files': 'Riusa i file verificati; rifiuta i file esistenti ambigui',
    'Stop without changing the directory': 'Interrompi senza modificare la cartella',
    'full resolution': 'risoluzione massima',
    '{count} workers': '{count} download paralleli',
    'Output': 'Destinazione',
    'Pages': 'Pagine',
    'Size': 'Dimensione',
    'Download plan': 'Piano di download',
    'Label': 'Etichetta',
    'Canvas / source': 'Canvas / sorgente',
    'Downloaded': 'Scaricate',
    'Reused': 'Riutilizzate',
    'Failed': 'Fallite',
    'Written': 'Scritti',
    'Failures': 'Errori',
    'Error: {message}': 'Errore: {message}',
}

_FR: dict[str, str] = {
    # Shared
    'Download image galleries from the Portale Antenati': 'Téléchargez les galeries d\'images du Portale Antenati',
    'Support this project': 'Soutenir le projet',
    'Gallery or manifest URL': 'URL de la galerie ou du manifeste',
    'Loading register metadata…': 'Chargement des métadonnées du registre…',
    'Existing output': 'Destination existante',
    'Download complete': 'Téléchargement terminé',
    'Download cancelled': 'Téléchargement annulé',
    'Download incomplete': 'Téléchargement incomplet',
    'Download': 'Télécharger',
    'Error': 'Erreur',
    # GUI
    'File': 'Fichier',
    'Portale Antenati Website': 'Site du Portale Antenati',
    'Project Website': 'Site du projet',
    'About': 'À propos',
    'Download options': 'Options de téléchargement',
    'Size (px)': 'Taille (px)',
    'Maximum size': 'Taille maximale',
    'First page': 'Première page',
    'Zero-based index': 'Index à partir de 0',
    'Last page': 'Dernière page',
    'Exclusive; leave empty for all remaining pages': 'Exclue ; laisser vide pour toutes les pages restantes',
    'Workers': 'Téléchargements parallèles',
    'Concurrent image downloads': 'Images téléchargées simultanément',
    'Filenames': 'Noms de fichiers',
    'Include archive/image IDs': 'Inclure les ID d\'archive et d\'image',
    'Existing files': 'Fichiers existants',
    'Verified resume is recommended when reusing a destination': 'La reprise vérifiée (« resume ») est recommandée pour réutiliser une destination',
    'Destination': 'Destination',
    'Save in': 'Enregistrer dans',
    'Change…': 'Modifier…',
    'Create a separate folder for each register (recommended)': 'Créer un dossier distinct pour chaque registre (recommandé)',
    'Register folder': 'Dossier du registre',
    'Will be determined from metadata': 'Sera déterminé à partir des métadonnées',
    '(same as Save in)': '(identique à « Enregistrer dans »)',
    'Cancel': 'Annuler',
    'Ready': 'Prêt',
    'Open folder': 'Ouvrir le dossier',
    'Folder unavailable': 'Dossier indisponible',
    'The destination folder does not exist yet.': 'Le dossier de destination n\'existe pas encore.',
    'The destination already contains files.\n\nYes: resume and verify existing downloads (recommended)\nNo: choose another action\nCancel: stop':
        'La destination contient déjà des fichiers.\n\nOui : reprendre et vérifier les téléchargements existants (recommandé)\nNon : choisir une autre action\nAnnuler : arrêter',
    'Overwrite planned files?\n\nYes: overwrite\nNo: skip verified files and refuse ambiguous files\nCancel: stop':
        'Écraser les fichiers prévus ?\n\nOui : écraser\nNon : ignorer les fichiers vérifiés et refuser les fichiers ambigus\nAnnuler : arrêter',
    'Please enter a valid URL.': 'Veuillez saisir une URL valide.',
    'Resolving…': 'Résolution…',
    'Cancelling…': 'Annulation…',
    'Preparing output…': 'Préparation de la destination…',
    'Planning download…': 'Planification du téléchargement…',
    'Downloading {completed}/{total} pages…': 'Téléchargement de {completed}/{total} pages…',
    'Downloaded {completed}, reused {skipped}. New data: {size}\n\nSaved to:\n{output}':
        'Téléchargées : {completed}, réutilisées : {skipped}. Nouvelles données : {size}\n\nEnregistrées dans :\n{output}',
    'Completed {completed}/{expected}; failed {failed}.\n{details}': 'Terminées {completed}/{expected} ; échecs {failed}.\n{details}',
    'Cancelled': 'Annulé',
    'Download cancelled after {completed}/{expected} pages.': 'Téléchargement annulé après {completed}/{expected} pages.',
    'Download failed': 'Échec du téléchargement',
    'Enter a gallery URL to preview the register.': "Saisissez l'URL d'une galerie pour afficher un aperçu du registre.",
    # CLI
    'URL of the gallery page or its IIIF manifest': 'URL de la page de la galerie ou de son manifeste IIIF',
    'Image size in pixels; 0 means full size': 'Taille de l\'image en pixels ; 0 signifie taille maximale',
    'Maximum number of concurrent download workers (--nthreads is a deprecated alias)':
        'Nombre maximal de téléchargements parallèles (--nthreads est un alias obsolète)',
    'First image to download': 'Première image à télécharger',
    'Exclusive end index: first image NOT to download': 'Index de fin exclu : première image à NE PAS télécharger',
    'Include archive and image IDs in saved file names': 'Inclure les ID d\'archive et d\'image dans les noms de fichiers',
    'Exact output directory (default: generated archive directory)': 'Dossier de destination exact (par défaut : généré à partir de l\'archive)',
    'How to handle an existing output directory': 'Comment gérer un dossier de destination existant',
    'Show the resolved download plan without writing image files': 'Afficher le plan de téléchargement sans écrire d\'images',
    'Output format: text or machine-readable JSON': 'Format de sortie : texte ou JSON lisible par machine',
    'Show version and exit': 'Afficher la version et quitter',
    'Increase logging verbosity; repeat for DEBUG logging and full tracebacks': 'Augmenter la verbosité des journaux ; répéter pour le niveau DEBUG et les traces complètes',
    'URL is required with --format json.': 'L\'URL est obligatoire avec --format json.',
    'URL is required outside an interactive terminal.': 'L\'URL est obligatoire hors d\'un terminal interactif.',
    'Output directory already exists and is not empty: {directory}. Choose an explicit --existing policy when using --format json.':
        'Le dossier de destination existe déjà et n\'est pas vide : {directory}. Avec --format json, choisissez une politique --existing explicite.',
    'Policy': 'Politique',
    'Choose one of: resume, overwrite, skip, cancel.': 'Choisissez parmi : resume, overwrite, skip, cancel.',
    'Value must be >= {minimum}.': 'La valeur doit être >= {minimum}.',
    'Pages [all/range]': 'Pages [all/range]',
    'First image (0-based)': 'Première image (à partir de 0)',
    'Last image (exclusive)': 'Dernière image (exclue)',
    'Image size [full/3000/2000/1000/custom]': 'Taille de l\'image [full/3000/2000/1000/custom]',
    'Image size in pixels': 'Taille de l\'image en pixels',
    'Choose full, 3000, 2000, 1000, or custom.': 'Choisissez full, 3000, 2000, 1000 ou custom.',
    'image size': 'taille de l\'image',
    'Output directory': 'Dossier de destination',
    'Start download?': 'Démarrer le téléchargement ?',
    'Cancelled by user.': 'Annulé par l\'utilisateur.',
    'Downloading': 'Téléchargement',
    'Register': 'Registre',
    '{count} pages': '{count} pages',
    'Verify and reuse valid downloads': 'Vérifier et réutiliser les téléchargements valides',
    'recommended': 'recommandé',
    'Download again and replace planned files': 'Télécharger à nouveau et remplacer les fichiers prévus',
    'Reuse verified files; refuse ambiguous existing files': 'Réutiliser les fichiers vérifiés ; refuser les fichiers existants ambigus',
    'Stop without changing the directory': 'Arrêter sans modifier le dossier',
    'full resolution': 'résolution maximale',
    '{count} workers': '{count} téléchargements parallèles',
    'Output': 'Destination',
    'Pages': 'Pages',
    'Size': 'Taille',
    'Download plan': 'Plan de téléchargement',
    'Label': 'Libellé',
    'Canvas / source': 'Canvas / source',
    'Downloaded': 'Téléchargées',
    'Reused': 'Réutilisées',
    'Failed': 'Échecs',
    'Written': 'Écrit',
    'Failures': 'Échecs',
    'Error: {message}': 'Erreur : {message}',
}

_ES: dict[str, str] = {
    # Shared
    'Download image galleries from the Portale Antenati': 'Descarga las galerías de imágenes del Portale Antenati',
    'Support this project': 'Apoya el proyecto',
    'Gallery or manifest URL': 'URL de la galería o del manifiesto',
    'Loading register metadata…': 'Cargando los metadatos del registro…',
    'Existing output': 'Destino existente',
    'Download complete': 'Descarga completada',
    'Download cancelled': 'Descarga cancelada',
    'Download incomplete': 'Descarga incompleta',
    'Download': 'Descargar',
    'Error': 'Error',
    # GUI
    'File': 'Archivo',
    'Portale Antenati Website': 'Sitio del Portale Antenati',
    'Project Website': 'Sitio del proyecto',
    'About': 'Acerca de',
    'Download options': 'Opciones de descarga',
    'Size (px)': 'Tamaño (px)',
    'Maximum size': 'Tamaño máximo',
    'First page': 'Primera página',
    'Zero-based index': 'Índice desde 0',
    'Last page': 'Última página',
    'Exclusive; leave empty for all remaining pages': 'Excluida; deja vacío para todas las páginas restantes',
    'Workers': 'Descargas paralelas',
    'Concurrent image downloads': 'Imágenes descargadas simultáneamente',
    'Filenames': 'Nombres de archivo',
    'Include archive/image IDs': 'Incluir ID de archivo e imagen',
    'Existing files': 'Archivos existentes',
    'Verified resume is recommended when reusing a destination': 'Se recomienda la reanudación verificada («resume») al reutilizar un destino',
    'Destination': 'Destino',
    'Save in': 'Guardar en',
    'Change…': 'Cambiar…',
    'Create a separate folder for each register (recommended)': 'Crear una carpeta separada para cada registro (recomendado)',
    'Register folder': 'Carpeta del registro',
    'Will be determined from metadata': 'Se determinará a partir de los metadatos',
    '(same as Save in)': '(igual que «Guardar en»)',
    'Cancel': 'Cancelar',
    'Ready': 'Listo',
    'Open folder': 'Abrir carpeta',
    'Folder unavailable': 'Carpeta no disponible',
    'The destination folder does not exist yet.': 'La carpeta de destino aún no existe.',
    'The destination already contains files.\n\nYes: resume and verify existing downloads (recommended)\nNo: choose another action\nCancel: stop':
        'El destino ya contiene archivos.\n\nSí: reanudar y verificar las descargas existentes (recomendado)\nNo: elegir otra acción\nCancelar: detener',
    'Overwrite planned files?\n\nYes: overwrite\nNo: skip verified files and refuse ambiguous files\nCancel: stop':
        '¿Sobrescribir los archivos previstos?\n\nSí: sobrescribir\nNo: omitir los archivos verificados y rechazar los ambiguos\nCancelar: detener',
    'Please enter a valid URL.': 'Introduce una URL válida.',
    'Resolving…': 'Resolviendo…',
    'Cancelling…': 'Cancelando…',
    'Preparing output…': 'Preparando el destino…',
    'Planning download…': 'Planificando la descarga…',
    'Downloading {completed}/{total} pages…': 'Descargando {completed}/{total} páginas…',
    'Downloaded {completed}, reused {skipped}. New data: {size}\n\nSaved to:\n{output}':
        'Descargadas {completed}, reutilizadas {skipped}. Datos nuevos: {size}\n\nGuardadas en:\n{output}',
    'Completed {completed}/{expected}; failed {failed}.\n{details}': 'Completadas {completed}/{expected}; fallidas {failed}.\n{details}',
    'Cancelled': 'Cancelado',
    'Download cancelled after {completed}/{expected} pages.': 'Descarga cancelada tras {completed}/{expected} páginas.',
    'Download failed': 'La descarga ha fallado',
    'Enter a gallery URL to preview the register.': 'Introduce la URL de una galería para ver una vista previa del registro.',
    # CLI
    'URL of the gallery page or its IIIF manifest': 'URL de la página de la galería o de su manifiesto IIIF',
    'Image size in pixels; 0 means full size': 'Tamaño de la imagen en píxeles; 0 significa tamaño máximo',
    'Maximum number of concurrent download workers (--nthreads is a deprecated alias)':
        'Número máximo de descargas paralelas (--nthreads es un alias obsoleto)',
    'First image to download': 'Primera imagen que descargar',
    'Exclusive end index: first image NOT to download': 'Índice final excluido: primera imagen que NO descargar',
    'Include archive and image IDs in saved file names': 'Incluir los ID de archivo e imagen en los nombres de archivo',
    'Exact output directory (default: generated archive directory)': 'Carpeta de destino exacta (por defecto: generada a partir del archivo)',
    'How to handle an existing output directory': 'Cómo gestionar una carpeta de destino existente',
    'Show the resolved download plan without writing image files': 'Mostrar el plan de descarga sin escribir imágenes',
    'Output format: text or machine-readable JSON': 'Formato de salida: texto o JSON legible por máquina',
    'Show version and exit': 'Mostrar la versión y salir',
    'Increase logging verbosity; repeat for DEBUG logging and full tracebacks': 'Aumentar el detalle de los registros; repetir para el nivel DEBUG y trazas completas',
    'URL is required with --format json.': 'La URL es obligatoria con --format json.',
    'URL is required outside an interactive terminal.': 'La URL es obligatoria fuera de un terminal interactivo.',
    'Output directory already exists and is not empty: {directory}. Choose an explicit --existing policy when using --format json.':
        'La carpeta de destino ya existe y no está vacía: {directory}. Con --format json elige una política --existing explícita.',
    'Policy': 'Política',
    'Choose one of: resume, overwrite, skip, cancel.': 'Elige entre: resume, overwrite, skip, cancel.',
    'Value must be >= {minimum}.': 'El valor debe ser >= {minimum}.',
    'Pages [all/range]': 'Páginas [all/range]',
    'First image (0-based)': 'Primera imagen (desde 0)',
    'Last image (exclusive)': 'Última imagen (excluida)',
    'Image size [full/3000/2000/1000/custom]': 'Tamaño de imagen [full/3000/2000/1000/custom]',
    'Image size in pixels': 'Tamaño de imagen en píxeles',
    'Choose full, 3000, 2000, 1000, or custom.': 'Elige full, 3000, 2000, 1000 o custom.',
    'image size': 'tamaño de imagen',
    'Output directory': 'Carpeta de destino',
    'Start download?': '¿Iniciar la descarga?',
    'Cancelled by user.': 'Cancelado por el usuario.',
    'Downloading': 'Descargando',
    'Register': 'Registro',
    '{count} pages': '{count} páginas',
    'Verify and reuse valid downloads': 'Verificar y reutilizar las descargas válidas',
    'recommended': 'recomendado',
    'Download again and replace planned files': 'Descargar de nuevo y reemplazar los archivos previstos',
    'Reuse verified files; refuse ambiguous existing files': 'Reutilizar los archivos verificados; rechazar los existentes ambiguos',
    'Stop without changing the directory': 'Detener sin modificar la carpeta',
    'full resolution': 'resolución máxima',
    '{count} workers': '{count} descargas paralelas',
    'Output': 'Destino',
    'Pages': 'Páginas',
    'Size': 'Tamaño',
    'Download plan': 'Plan de descarga',
    'Label': 'Etiqueta',
    'Canvas / source': 'Canvas / origen',
    'Downloaded': 'Descargadas',
    'Reused': 'Reutilizadas',
    'Failed': 'Fallidas',
    'Written': 'Escrito',
    'Failures': 'Errores',
    'Error: {message}': 'Error: {message}',
}
# fmt: on

CATALOGS: dict[str, dict[str, str]] = {'it': _IT, 'fr': _FR, 'es': _ES}
