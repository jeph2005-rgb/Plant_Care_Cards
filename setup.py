"""
Setup script for creating macOS .app bundle of Leaf & Vessel Care Card Generator
"""

from setuptools import setup

APP = ['care_card_generator.py']
DATA_FILES = [
    'Small Version.png',
    'Card_Back.pdf',
    'plants.db'
]

OPTIONS = {
    'argv_emulation': False,
    'iconfile': None,  # You can add an .icns file here if you create one
    'plist': {
        'CFBundleName': 'Leaf & Vessel Care Card Generator',
        'CFBundleDisplayName': 'Care Card Generator',
        'CFBundleIdentifier': 'com.leafandvessel.carecardgenerator',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
    },
    'packages': [
        'anthropic',
        'customtkinter',
        'reportlab',
        'PIL',
        'pypdf',
        'sqlite3',
        'tkinter',
    ],
    'includes': [
        'customtkinter',
        'anthropic',
        'reportlab.pdfgen.canvas',
        'reportlab.lib.pagesizes',
        'reportlab.lib.utils',
        'reportlab.platypus',
        'pypdf',
    ],
    'excludes': [
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
    ],
    'resources': DATA_FILES,
}

setup(
    name='Leaf & Vessel Care Card Generator',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
