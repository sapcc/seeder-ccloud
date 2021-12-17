from setuptools import setup, find_packages

setup(
    name='seeder_ccloud',
    version='1.0.0',
    packages=find_packages(include=['seeder_ccloud', 'seeder_ccloud.*']),
    install_requires=[
        'python-keystoneclient',
        'python-novaclient',
        'python-neutronclient',
        'python-designateclient',
        'python-swiftclient',
        'python-manilaclient',
        'python-cinderclient',
        'osc-placement',
        'kubernetes',
        'kopf',
        'kubernetes_asyncio',
        'deepdiff',
    ],
    url='https://github.com/sapcc/seeder-ccloud',
    license='',
    author='SAP SE',
    description='Seeder CCloud',
    entry_points = {
        "console_scripts": [
            'seeder-ccloud-operator = seeder_ccloud:main',
        ]
    },
)