# <img src="/images/logo.png" width="28"/> Dex Bot

## Introduction

Telegram Bot that uses [dexonline.ro](https://dexonline.ro)'s API to search
Romanian words definitions. The bot currently runs as
[@DexRoBot](https://t.me/DexRoBot).

### Main functionality

<img alt="Main screenshot 1" src="images/screenshot_main_1@2x.png" width="276"
height="320"><img alt="Main screenshot 2" src="images/screenshot_main_2@2x.png"
width="276" height="320"><img alt="Main screenshot 3"
src="images/screenshot_main_3@2x.png" width="276" height="320">

### Toggle links feature

<img alt="Toggle links screenshot 1" src="images/screenshot_links_1@2x.png"
width="276" height="288"><img alt="Toggle links screenshot 2"
src="images/screenshot_links_2@2x.png" width="276" height="288"><img alt="Toggle
links screenshot 3" src="images/screenshot_links_3@2x.png" width="276"
height="288">

### Word of the day feature

<img alt="Word of the day screenshot" src="images/screenshot_wotd@2x.png"
width="414" height="681">

## Getting Started

These instructions will get you a copy of the project up and running on your
local machine for development and testing purposes.

### Prerequisites

You need to install [Homebrew](https://brew.sh) by running:

```sh
/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
```

### Installing

Clone the project and install the dependencies by running:

```sh
cd /desired/location/path
git clone https://github.com/revolter/DexRoBot.git
cd DexRoBot

brew install pipenv
pipenv --three
pipenv shell
pipenv install

cd src
cp config_sample.cfg config.cfg
```

On Linux, you might need to install the development package of Python by
running:

```sh
sudo apt install python3-dev
```

before trying to install the dependencies using `pipenv`.

Then, edit the file named `config.cfg` inside the `src` folder with the correct
values and run it using `./main.py --debug`.

Use `exit` to close the virtual environment.

## Deploy

You can easily deploy this to a cloud machine using
[Fabric](http://fabfile.org):

```
cd /project/location/path

pipenv shell
pipenv install --dev

cp fabfile_sample.cfg fabfile.cfg
```

Then, edit the file named `fabfile.cfg` inside the root folder with the correct
values and run Fabric using:

```
fab setup
fab deploy
```

You can also deploy a single file using `fab deploy --filename=main.py` or `fab
deploy --filename=Pipfile`.
