import asyncio, requests, logging, pysondb
from telegram import InputMediaDocument, InputMediaPhoto
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import LinkPreviewOptions, Update, error
from telegram import ChatMember, ChatMemberUpdated, Update
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
    def __init__(self, name: str = "db/db.json"):
        self.db = pysondb.db.getDb(name)
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
        if "add" in name.lower():    name += " +"
        if "cancel" in name.lower(): name += " ⊘"
        if "delete" in name.lower(): name += " ×"
        reply_markup.append([InlineKeyboardButton(name, callback_data=data)])
    return InlineKeyboardMarkup(reply_markup)

# source: https://docs.python-telegram-bot.org/en/stable/examples.chatmemberbot.html
from typing import Optional
def extract_status_change(chat_member_update: ChatMemberUpdated) -> Optional[tuple[bool, bool]]:
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))
    if status_change is None:
        return None
    old_status, new_status = status_change
    was_member = old_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    is_member = new_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (new_status == ChatMember.RESTRICTED and new_is_member is True)
    return was_member, is_member

## DATABASE ##
db = database_()
channels = database_("db/channels.json")
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
            await update.message.reply_text("Invalid url!")
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
                            #  output = 2-infinite - new in db | mastodon id
                await update.message.reply_text("Already bridged!")
            else:
                await update.message.reply_text(
                    f"*Successfully bridged!*\n_FROM:_ {update.message.text}\n_TO:_ {channel.title}",
                    parse_mode="Markdown")

## MANAGING ##
async def manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = channels.get({"user_id": update.effective_sender.id})
    reply_markup = []
    channelsList = []
    for element in query:
        if element["channel_id"] in channelsList: continue
        channelsList.append(element["channel_id"])
        reply_markup.append( (element["channel_name"]+" | "+str(element["channel_id"]), "manage "+str(element["channel_id"])) )
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
            channel = channels.get({"channel_id": int(args[0])})[0]
            reply_markup = []
            for element in query:
                reply_markup.append( (element["mastodon_name"], f"manage_bridge {args[0]} {element['mastodon_id']}") )
            reply_markup.append(("Add bridge", f"add {args[0]}"))
            reply_markup.append(("Delete channel", f"del_channel {args[0]}"))
            await update.callback_query.delete_message()
            await update.effective_chat.send_message(f"Choose a bridge to *{channel['channel_name']}*",
                                                     reply_markup=inlineGen(reply_markup),
                                                     parse_mode="Markdown")
        case "manage_bridge":
            reply_markup = []
            reply_markup.append(("Delete", f"del_bridge {args[0]} {args[1]}"))
            reply_markup.append(("Exit", f"cancel"))
            query = db.get({"tg_channel_id": int(args[0]), "mastodon_id": args[1]})[0]
            await update.effective_chat.send_message(f"Actions for bridge {query['mastodon_name']} ➔ {query['tg_channel_name']}",
                                                     reply_markup=inlineGen(reply_markup))

        case "del_channel": 
            db.delete({"tg_channel_id": int(args[0])})
            channels.delete({"channel_id": int(args[0])})
            await application.bot.leave_chat(int(args[0]))
        case "del_bridge": db.delete({"tg_channel_id": int(args[0]), "mastodon_id": args[1]})
        case "add_channel": await update.effective_chat.send_message("Add me to one of your chat rooms and give me the ability to send messages if needed.")

        case "add":
            query = channels.get({"channel_id": int(args[0])})[0]
            await bridge(update, context, Chat(query["channel_id"], query["channel_name"]))

        case _:
            await update.effective_chat.send_message("WHAT")

    if type.startswith("del_"):
        await update.effective_chat.send_message("Deleted.")

## SENDING ##
from telegram.helpers import escape_markdown
import html
def html2md(text: str) -> str:
    i = 0
    while i < len(text):
        toReplace = ""
        tag = ""
        text = escape_markdown(text)
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
    return html.unescape(text.strip())

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
                        reblog = False
                        if post["reblog"] is not None:
                            reblog = True
                            post = post["reblog"]
                        postContent = html2md(post["content"]+"\n"+
                                              post["url"])
                        if reblog: postContent += f"\nReblog ❇"
                        print(postContent)
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
                        for u in db.get({"mastodon_id": user["mastodon_id"]}):
                            for _ in range(3):
                                try:
                                    if len(media) > 0:
                                        asyncio.run(application.bot.send_media_group(u["tg_channel_id"], media, caption=postContent, parse_mode="Markdown"))
                                        break
                                    else:
                                        asyncio.run(application.bot.send_message(u["tg_channel_id"], postContent, parse_mode="Markdown"))
                                        break
                                except Exception as e:
                                    logging.error(e)
                                    if type(e) == error.NetworkError and "Event loop is closed" in e.message: 
                                        logging.warning(e)
                                        break
                                    logging.warning("Retrying...")
                    elif not User in ids.keys():
                        ids[User] = post["id"]
        except Exception as e:
            logging.error(e)
            sleep(1)

## MAIN ##
from dotenv import load_dotenv
from os import getenv
load_dotenv()
application = ApplicationBuilder().token(getenv("TOKEN")).build()

async def bridge(update: Update, context: ContextTypes.DEFAULT_TYPE, chat=None):
    title = "unknown"
    
    if chat != None:
        bindings[update.effective_sender.id] = chat
        title = chat.title
    else:
        title = update.effective_chat.title

        bindings[update.effective_sender.id] = update.effective_chat
        if update.effective_chat.type == "private": return
        
        result = extract_status_change(update.my_chat_member)
        if result is None:
            return
        was_member, is_member = result
        if was_member and not is_member:
            channels.delete({"channel_id": update.effective_chat.id})
            db.delete({"tg_channel_id": update.effective_chat.id})
            return
        elif is_member and not was_member:
            channels.write({
                "user_id": update.effective_user.id,
                "channel_id": update.effective_chat.id,
                "channel_name": title,
            })

    await update.effective_sender.send_message(
            f"Bridging with *{title}*\nSend me a link to your Mastodon profile.",
            parse_mode="Markdown",
            reply_markup=inlineGen([("Cancel", "cancel")])
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vtext = ""
    if getenv("VERSION") is not None: vtext = "version: "+str(getenv("VERSION"))
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"""
Welcome to *Mastodon ➔ Telegram bridge* \\[mtdntg] 🐘
_To start using it, add me to one of your chat rooms and give me the ability to send messages if needed._

/start or /help - show this message
/manage - manage bridges

Also, I'm a completely open-source bot under GPLv3 license :3
github.com/unixource/mtdntg

bot picture by @ARYLUNEIX

{vtext}
""", parse_mode="Markdown", link_preview_options=LinkPreviewOptions(True))

from multiprocessing import Process
if __name__ == '__main__':
    process = Process(target = sender)
    process.start()

    #-#-#-#-#-#-#-#

    application.add_handler( CommandHandler('start', start) )
    application.add_handler( CommandHandler('help', start) )
    application.add_handler( CommandHandler('manage', manage))
    application.add_handler( ChatMemberHandler(bridge) )
    application.add_handler( MessageHandler(filters.TEXT, callback=message) )
    application.add_handler( CallbackQueryHandler(button) )

    application.run_polling()

    #-#-#-#-#-#-#-#

    process.close()
