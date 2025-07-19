import os
import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from dotenv import load_dotenv
from datetime import datetime, time as dtime, timedelta
import pytz

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
MEME_CHANNEL_ID = int(os.getenv("MEME_CHANNEL_ID"))

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.dm_messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# To track daily sent memes and current batch + session control
daily_meme_urls = set()
daily_meme_date = None

current_batch = []
current_ctx = None
current_wait_task = None

async def reset_daily_memes():
    global daily_meme_urls, daily_meme_date
    tz = pytz.timezone('Europe/Paris')
    today = datetime.now(tz).date()
    if daily_meme_date != today:
        daily_meme_urls.clear()
        daily_meme_date = today

async def fetch_meme_from_api(subreddit=None):
    url = "https://meme-api.com/gimme"
    if subreddit:
        url += f"/{subreddit}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            meme_data = {
                "title": data.get("title"),
                "post_link": data.get("postLink"),
                "url": data.get("url")
            }
            return meme_data

async def fetch_unique_memes(batch_size=5, subreddit=None):
    memes = []
    attempts = 0
    max_attempts = batch_size * 5
    while len(memes) < batch_size and attempts < max_attempts:
        meme = await fetch_meme_from_api(subreddit)
        attempts += 1
        if meme and meme["url"] not in daily_meme_urls and meme["url"] not in [m["url"] for m in memes]:
            memes.append(meme)
    return memes

async def send_batch_for_validation(memes, ctx):
    global current_wait_task, current_batch, current_ctx

    current_batch = memes
    current_ctx = ctx

    msg_text = "**Alright mate, here are some memes for you!** 🧙‍♂️\n"
    for i, meme in enumerate(memes, start=1):
        msg_text += f"**{i}. {meme['title']}**\n{meme['url']}\n\n"
    msg_text += (
        "Reply with `yes <number>` to post a meme, or `no` to discard and get a new batch.\n"
        "Or use `!stop` to cancel this session."
    )
    await ctx.send(msg_text)

    def check(m):
        return (
            m.author.id == OWNER_ID and
            m.channel == ctx.channel and
            (m.content.lower().startswith("yes") or m.content.lower() == "no")
        )

    async def wait_for_reply():
        try:
            reply = await bot.wait_for("message", check=check, timeout=3600)
            content = reply.content.lower()

            if content == "no":
                await ctx.send("Okay, discarding these memes and fetching a new batch...")
                await start_fetching_session(ctx)
                return

            elif content.startswith("yes"):
                parts = content.split()
                if len(parts) == 2 and parts[1].isdigit():
                    idx = int(parts[1]) - 1
                    if 0 <= idx < len(current_batch):
                        selected = current_batch[idx]
                        daily_meme_urls.add(selected["url"])
                        channel = bot.get_channel(MEME_CHANNEL_ID)
                        # Post clean meme with Ron flavor text
                        await channel.send(
                            f"Here's one from your pal Ron Weasley: **{selected['title']}**\n"
                            f"{selected['url']}\n"
                            "*Mischief managed! 🔥*"
                        )
                        await ctx.send("✅ Meme published! Session ended.")
                        # Clear current batch/session
                        clear_session()
                        return
                await ctx.send("Invalid number, please reply `yes <number>` with a valid meme number.")
                await wait_for_reply()
            else:
                await ctx.send("Please reply with `yes <number>` or `no`.")
                await wait_for_reply()

        except asyncio.TimeoutError:
            await ctx.send("⌛ No response in time, session ended and memes discarded.")
            clear_session()

    current_wait_task = asyncio.create_task(wait_for_reply())

def clear_session():
    global current_batch, current_ctx, current_wait_task
    current_batch = []
    current_ctx = None
    if current_wait_task and not current_wait_task.done():
        current_wait_task.cancel()
    current_wait_task = None

async def start_fetching_session(ctx, subreddit=None):
    await reset_daily_memes()
    memes = await fetch_unique_memes(batch_size=5, subreddit=subreddit)
    if not memes:
        await ctx.send("Sorry, couldn't find any new memes for you right now.")
        clear_session()
        return
    await send_batch_for_validation(memes, ctx)

@bot.command()
async def fetch(ctx):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        await ctx.send("Fetching some fresh memes for you 🧙‍♂️...")
        await start_fetching_session(ctx)
    else:
        await ctx.send("This command can only be used by the owner in DMs.")

@bot.command()
async def fetchsub(ctx, subreddit: str):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        await ctx.send(f"Fetching memes from r/{subreddit} for you 🧙‍♂️...")
        await start_fetching_session(ctx, subreddit=subreddit)
    else:
        await ctx.send("This command can only be used by the owner in DMs.")

@bot.command()
async def stop(ctx):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        if current_wait_task and not current_wait_task.done():
            clear_session()
            await ctx.send("🛑 Fetching session stopped, memes discarded.")
        else:
            await ctx.send("No active meme fetching session to stop.")
    else:
        await ctx.send("This command can only be used by the owner in DMs.")

@tasks.loop(minutes=1)
async def daily_meme_fetcher():
    tz = pytz.timezone('Europe/Paris')  # GMT+2 with daylight saving
    now = datetime.now(tz)
    target_time = dtime(hour=20, minute=0)  # 8 PM

    if now.time().hour == target_time.hour and now.time().minute == target_time.minute:
        owner = await bot.fetch_user(OWNER_ID)
        await owner.send("⏰ It's 8 PM, fetching your daily memes for validation!")
        await start_fetching_session(owner)

@bot.event
async def on_ready():
    print(f"⚡ Ron Weasley bot ready as {bot.user}!")
    daily_meme_fetcher.start()

bot.run(TOKEN)
