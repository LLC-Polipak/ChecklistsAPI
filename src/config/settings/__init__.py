import os

from split_settings.tools import include, optional

ENV = os.getenv('DJANGO_ENV', 'local')

base_settings = [
    'base.py',
    f'{ENV}.py',
]

include(*base_settings)