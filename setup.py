from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="pymabibli",
    version="0.0.1",
    author="Bestycame",
    author_email="bestycame@gmail.com",
    description="An async Python client for mabibli.be, the libraries of the Province of Liège",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/bestycame/pymabibli",
    packages=find_packages(exclude=["tests", "tests.*", "examples"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Framework :: AsyncIO",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    ],
    python_requires=">=3.12",
    install_requires=[
        "aiohttp>=3.9",
        "beautifulsoup4>=4.12",
    ],
)
