# mtdntg - Matrix to Telegram bridge.
## About
This is the source code for the Telegram bot [@MastodonBridgeBot](https://t.me/MastodonBridgeBot). It allows you to redirect messages from Mastodon to Telegram with absolutely no restrictions. The bridge requires minimal information and is easy to use.
## Setting up
- Linux
```
git clone https://github.com/unixource/mtdntg.git
cd mtdntg
python -m venv env
source env/bin/activate
pip install -r requirements.txt
pysondb create db/db.json
```
After that, create an .env file with the contents:
```
TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
```
Done :D
Now you can run the main script
