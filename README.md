# <img src="/images/logo.png" width="28"/> Dex Bot 

## Introduction

Telegram Bot that uses [dexonline.ro](https://dexonline.ro)'s API to search Romanian words definitions. The bot currently runs as [@DexRoBot](https://t.me/DexRoBot).

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
```

Then create a file named `config.cfg` inside the `src` folder with this format:

```
[Telegram]
TestKey: <Telegram Bot API token key>
```

And run it using `./main.py -d`.
