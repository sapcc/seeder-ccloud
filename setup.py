from setuptools import setup

setup(
    name='seeder_ccloud',
    version='1.0.0',
    packages='.',
    install_requires=[
        'python-keystoneclient>=3.20.0',
        'python-novaclient>=14.2.0',
        'python-neutronclient>=6.12.0',
        'python-designateclient>=2.11.0',
        'python-swiftclient>=3.8.0',
        'python-manilaclient>=1.27.0',
        'python-cinderclient>=6.0.0',
        'osc-placement>=1.4.0',
        'kubernetes',
        'kopf',
        'kubernetes_asyncio',
        'deepdiff',
    ],
    url='https://github.com/sapcc/seeder-ccloud',
    license='',
    author='Rudolf Vriend',
    author_email='rudolf.vriend@sap.com',
    description='Seeder CCloud',
    entry_points = {
        "console_scripts": [
            'seeder-ccloud-operator = seeder_ccloud:main',
        ]
        },
)