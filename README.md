# img tagger

[![CI](https://github.com/juusolatva/img_tagger/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/juusolatva/img_tagger/actions/workflows/ci.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=juusolatva_img_tagger&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=juusolatva_img_tagger)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=juusolatva_img_tagger&metric=coverage)](https://sonarcloud.io/summary/new_code?id=juusolatva_img_tagger)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/github/license/juusolatva/img_tagger)](LICENSE)

A python script that tags all the **JPEG**, **WebP**, **PNG** and **GIF** files in the directory (and possibly subdirectories) by sending them to a local vision-language model (either **ollama** or **LM Studio** running on the same computer or the local network). The tags the model sends back are added as metadata to the images. The accuracy of the tags depends on the model.

## Features

- Creates tags for **JPEGs**, **WebPs**, **PNGs** and **GIFs**
- Skips already processed files that have the marker: ***[PROCESSED BY AI]***
- Runs **1 to 4** workers concurrently
- Collects simple performance metrics
- Optional logging for troubleshooting


---


## Installation
Clone the repository and run *img_tagger.py* with Python.

### System prerequisites
You must have [Python](https://www.python.org/downloads/) 3.10 or newer and either **[ollama](https://ollama.com/download)** or **[LM Studio](https://lmstudio.ai/download)** with a vision-capable model for processing the images.

### Installing dependencies
*pip install -r requirements.txt*


---


## Usage
Just give it the folder with your images:

*python img_tagger.py path/to/images*

### Arguments
- *directory* - the folder with your images
- *-r* or *--recursive* - go through the subfolders too
- *--backend* - *ollama* (default) or *lm-studio*
- *--host* - address of the model server if it's not running on the default local address
- *--model* - the model to use (*qwen3-vl:8b* by default)
- *--workers* - how many images to process at the same time, from 1 to 4 (1 by default)
- *--log* - save a log file for troubleshooting, e.g. *--log logs/run.log*
- *--clear* - remove all metadata (EXIF/XMP/IPTC) and comments from images instead of tagging

### Examples
Tag a folder and all of its subfolders with ollama:

*python img_tagger.py ~/Pictures/memes -r*

Use LM Studio with 4 workers and save a log:

*python img_tagger.py ~/Pictures/memes --backend lm-studio --workers 4 --log run.log*

Clear all tags and metadata from a folder recursively:

*python img_tagger.py ~/Pictures/memes -r --clear*


---


### Notes
- Run *img_tagger.py -h* or *img_tagger.py --help* to see the arguments and options
- Press `Q` to quit and then wait for it to finish all the work in progress
- The script doesn't respect preexisting tags so keep in mind that they will be overwritten
- The default model is **Qwen3 VL 8B** but any model capable of processing image inputs should work
- Allows a maximum of 4 workers which is the default limit for both **ollama** and **LM Studio**
- In case you need to you can clear all the tags in a folder using the *--clear* flag

### Running tests
*pip install -r requirements-dev.txt* and then *python -m pytest*. The default tests run offline (no model server needed).

To check tagging quality against real images, put them in a *test_images/* folder and run *python -m pytest -m integration --run-integration -s* with ollama or LM Studio running. Use *--tagger-backend*, *--tagger-host*, *--tagger-model* and *--images-dir* to change the defaults. The images are copied to a temporary folder so the originals are not modified.

### Continuous integration
Every push to *main* and every pull request runs [GitHub Actions](.github/workflows/ci.yml): **Ruff** lint and format checks, the offline tests with coverage on Python 3.10 to 3.14, and a **SonarQube Cloud** scan. To run the same checks locally, use *ruff check .*, *ruff format --check .* and *python -m pytest --cov*.

CI installs the exact package versions in *requirements-dev.lock*. If you change *requirements.txt* or *requirements-dev.txt*, regenerate the lock with [uv](https://docs.astral.sh/uv/):

*uv pip compile requirements-dev.txt --universal --python-version 3.10 --generate-hashes --no-header -o requirements-dev.lock*

### Known issues
- Animated **WebPs** keep their animation but the model might only see the first frame
