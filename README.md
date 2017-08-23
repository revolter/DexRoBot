# <img src="/images/logo.png" width="28"/> Dex Bot

## Introduction

Telegram Bot that uses [dexonline.ro](https://dexonline.ro)'s API to search Romanian words definitions. The bot currently runs as [@DexRoBot](https://t.me/DexRoBot).

![Screenshot 1](images/screenshot_1.jpg)
![Screenshot 2](images/screenshot_2.jpg)
![Screenshot 3](images/screenshot_3.jpg)

## Installation

Clone the project and install the dependencies by running these commands in the terminal:

```
cd /desired/location/path
git clone https://github.com/revolter/DexRoBot.git
cd DexRoBot
virtualenv -p python3 env
source env/bin/activate
cd src
pip install -r requirements.txt
cp config_sample.cfg config.cfg
```

Then edit the file named `config.cfg` inside the `src` folder with the correct values and run it using `./main.py -d`.

## Deploy

You can easily deploy this to a cloud machine using [Fabric](http://fabfile.org):

```
cd /project/location/path
virtualenv -p python3 env-dev
source env-dev/bin/activate
pip install -r requirements-dev.txt
cp fabfile_sample.cfg fabfile.cfg
```

Then edit the file named `fabfile.cfg` inside the root folder with the correct values and run Fabric using:

```
fab setup
fab deploy
```

You can also deploy a single file using `fab deploy:filename=main.py`
