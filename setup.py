# setup for datadiary

# import os.path
from setuptools import setup, find_packages

# here = os.path.abspath(os.path.dirname(__file__))

setup(
    name="movies2ical",
    version="0.3.0",
    description="Generate ical files from Stanford Movie Theater calendar webpage.",
    author="Matthew A. Clapp",
    author_email="itsayellow+dev@gmail.com",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
    #keywords="report",
    url="https://github.com/itsayellow/stanfordmovies",
    # include_package_data=True,  # so we get html files in datadiary/templates
    packages=["movies2ical"],
    install_requires=[
        "bleach",
        "beautifulsoup4",
        "icalendar",
        "html5lib",
        "imdbpy>=6.5",
        "pytz",
        "requests",
        "toml",
        "tzlocal",
    ],
    entry_points={"console_scripts": ["movies2ical=movies2ical.main:cli"]},
    python_requires=">=3.3",
)
