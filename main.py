import asyncio, requests, logging, pysondb
from telegram import InputMedia, InputMediaDocument, InputMediaPhoto, LinkPreviewOptions, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackContext, CallbackQueryHandler, ContextTypes, CommandHandler, ChatMemberHandler, MessageHandler, filters
from urllib.parse import urlparse

import urllib3
urllib3.disable_warnings()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

bindings = {}

## UTILITIES ##
class database_:
    def __init__(self):
        self.db = pysondb.db.getDb("db/db.json")
    def write(self, some: dict) -> int:
        if self.db.getByQuery(some) == []:
            self.db.add(some)
            return 0
        return 1
    def get(self, some: dict = {}) -> list:
        if some == {}: return self.db.getAll()
        return self.db.getByQuery(some)
    def delete(self, some: dict) -> None:
        for element in self.get(some):
            self.db.deleteById(element["id"])

class Chat:
    def __init__(self, id, title):
        self.id = id
        self.title = title

def inlineGen(elements: list) -> InlineKeyboardMarkup:
    reply_markup = []
    for element in elements:
        name, data = element
        if "add" in name.lower():    name += " ▫️"
        if "cancel" in name.lower(): name += " ⊘"
        if "delete" in name.lower(): name += " ⊘"
        reply_markup.append([InlineKeyboardButton(name, callback_data=data)])
    return InlineKeyboardMarkup(reply_markup)

## DATABASE ##
db = database_()
async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith("http") and update.effective_chat.type == "private":
        urlp = urlparse(update.message.text)
        instance = urlp.netloc
        username = "unknown"
        for p in urlp.path.split("/"):
            if p.startswith("@"):
                username = p
                break
        if username == "unknown":
            await update.message.reply_text("Unknown url!")
        else:
            channel = bindings[update.effective_sender.id]
            output = db.write({
                "tg_user_id": update.effective_sender.id,
                "tg_channel_name": channel.title,
                "tg_channel_id": channel.id,
                "mastodon_id": requests.get(f"https://{instance}/api/v1/accounts/lookup?acct={username}", verify=False).json()["id"],
                "mastodon_name": username,
                "mastodon_instance": instance,
                })
            if output == 1: #  output = 1 - already in db
                            #  output = 2-infinity - new in db | mastodon id
                await update.message.reply_text("Already bridged!")
            else:
                await update.message.reply_text(
                    f"*Successfully bridged!*\n_FROM:_ {update.message.text}\n_TO:_ {channel.title}",
                    parse_mode="Markdown")

## MANAGING ##
async def manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = db.get({"tg_user_id": update.effective_sender.id})
    reply_markup = []
    channels = []
    for element in query:
        if element["tg_channel_id"] in channels: continue
        channels.append(element["tg_channel_id"])
        reply_markup.append( (element["tg_channel_name"]+" | "+str(element["tg_channel_id"]), "manage "+str(element["tg_channel_id"])) )
    reply_markup.append( ("Add channel", "add_channel") )
    await update.message.reply_text("Choose.", reply_markup=inlineGen(reply_markup))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    data = update.callback_query.data
    type = data.split()[0]
    args = data.split()[1:]
    match type:
        case "cancel":
            await update.callback_query.delete_message()
            bindings[update.effective_sender.id] = None

        case "manage":
            query = db.get({"tg_channel_id": int(args[0])})
            reply_markup = []
            for element in query:
                reply_markup.append( (element["mastodon_name"], f"manage_bridge {args[0]} {element['mastodon_id']}") )
            reply_markup.append(("Add bridge", f"add {args[0]}"))
            reply_markup.append(("Delete channel", f"del_channel {args[0]}"))
            await update.callback_query.delete_message()
            await update.effective_chat.send_message(f"Choose a bridge to *{query[0]['tg_channel_name']}*",
                                                     reply_markup=inlineGen(reply_markup),
                                                     parse_mode="Markdown")
        case "manage_bridge":
            reply_markup = []
            reply_markup.append(("Delete", f"del_bridge {args[0]} {args[1]}"))
            reply_markup.append(("Exit", f"cancel"))
            query = db.get({"tg_channel_id": int(args[0]), "mastodon_id": args[1]})[0]
            await update.effective_chat.send_message(f"Actions for bridge {query['mastodon_name']} -> {query['tg_channel_name']}",
                                                     reply_markup=inlineGen(reply_markup))

        case "del_channel": db.delete({"tg_channel_id": int(args[0])})
        case "del_bridge": db.delete({"tg_channel_id": int(args[0]), "mastodon_id": args[1]})
        case "add_channel": await update.effective_chat.send_message("Use the /bind command in a group or channel.")

        case "add":
            query = db.get({"tg_channel_id": int(args[0])})[0]
            await join(update, context, Chat(query["tg_channel_id"], query["tg_channel_name"]))

        case _:
            await update.effective_chat.send_message("WHAT")

    if type.startswith("del_"):
        await update.effective_chat.send_message("Deleted.")

## SENDING ##
def html2md(text: str) -> str:
    i = 0
    while i < len(text):
        toReplace = ""
        tag = ""
        if text[i] == "<":
            while i < len(text) and text[i] != ">":
                toReplace += text[i]
                i += 1
            if i < len(text):
                tag = toReplace.split()[0][1:].replace("/", "")
                toReplace += ">"
                print(toReplace)
                match tag:
                    case "a":
                        text = text.replace(toReplace, "*")
                    case "br":
                        text = text.replace(toReplace, "\n")
                    case "p":
                        text = text.replace(toReplace, "\n")
                    case _:
                        text = text.replace(toReplace, "")
            i -= len(toReplace)-1
        else:
            i += 1
    return text.strip()

from time import sleep
def sender():
    ids = {"@example_example.com": 209302}
    while True:
        try:
            users = db.get()
            for user in users:
                sleep(1) ### based on Mastodon rate limit
                Id = user["mastodon_id"]
                Instance = user["mastodon_instance"]
                User = user["mastodon_name"]+"_"+Instance
                r = requests.get(f"https://{Instance}/api/v1/accounts/{Id}/statuses", verify=False, timeout=3)
                for post in r.json():
                    post["id"] = int(post["id"])
                    if User in ids.keys() and post["id"] > ids[User]:
                        ids[User] = post["id"]
                        postContent = html2md(post["content"]+"\n\n"+post["url"])
                        media = []
                        if len(post["media_attachments"]) > 0:
                            hasPhoto = False
                            for m in post["media_attachments"]:
                                if not m["url"].endswith(".mp4"): hasPhoto = True ### Fixes `BadRequest: Document can't be mixed with other media types`
                            media = []
                            for m in post["media_attachments"]:
                                if hasPhoto:
                                    media.append(InputMediaPhoto(m["url"]))
                                else:
                                    media.append(InputMediaDocument(m["url"]))
                        for u in db.get({"tg_user_id": user["tg_user_id"]}):
                            for _ in range(3):
                                try:
                                    if len(media) > 0:
                                        asyncio.run(application.bot.send_media_group(u["tg_channel_id"], media, caption=postContent, parse_mode="Markdown"))
                                        break
                                    else:
                                        asyncio.run(application.bot.send_message(u["tg_channel_id"], postContent, parse_mode="Markdown"))
                                        break
                                except: pass
                    elif not User in ids.keys():
                        ids[User] = post["id"]
        except Exception as e:
           print(e)
           sleep(1)

## MAIN ##
from dotenv import load_dotenv
from os import getenv
load_dotenv()
application = ApplicationBuilder().token(getenv("TOKEN")).build()

async def bridge(update: Update, context: ContextTypes.DEFAULT_TYPE, chat=None):
    if chat != None:
        bindings[update.effective_sender.id] = chat
        update.effective_chat.title = chat.title
    else:
        bindings[update.effective_sender.id] = update.effective_chat
        if update.effective_chat.type == "private": return
    await update.effective_sender.send_message(
            f"Bridging with *{update.effective_chat.title}*\nSend me a link to your Mastodon profile.",
            parse_mode="Markdown",
            reply_markup=inlineGen([("Cancel", "cancel")])
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="""
Welcome to *Mastodon -> Telegram bridge* \\[mtdn tg] 🐘
_To start using it, add me to one of your chat rooms and give me the ability to send messages if needed._

/start or /help - show this message
/bind - link with chat \\[only in groups/channels]
/manage - manage bridges

Also, I'm a completely open-source bot under GPLv3 license :3
github.com/unixource/mtdntg

bot picture by @ARYLUNEIX
""", parse_mode="Markdown", link_preview_options=LinkPreviewOptions(True))

from multiprocessing import Process
if __name__ == '__main__':
    process = Process(target = sender)
    process.start()

    #-#-#-#-#-#-#-#

    application.add_handler( CommandHandler('start', start) )
    application.add_handler( CommandHandler('help', start) )
    application.add_handler( CommandHandler('manage', manage))
    application.add_handler( CommandHandler('bind', bridge))
    application.add_handler( ChatMemberHandler(bridge) )
    application.add_handler( MessageHandler(filters.TEXT, callback=message) )
    application.add_handler( CallbackQueryHandler(button) )

    application.run_polling()

    #-#-#-#-#-#-#-#

    process.close()
