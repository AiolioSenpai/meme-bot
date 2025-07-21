import os
import io
import discord
from discord.ext import commands
import aiohttp
import asyncio
from dotenv import load_dotenv
from datetime import datetime
import pytz
import asyncio
import random
from datetime import datetime

TIMEZONE_OFFSET = 2  # adjust to match your Hogwarts time if needed

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

bot.remove_command('help')
sent_memes_today = set()
current_batch = []
current_ctx = None
current_wait_task = None
current_subreddit = None

async def reset_daily_memes():
    global sent_memes_today
    tz = pytz.timezone('Europe/Paris')
    now = datetime.now(tz)
    if now.hour == 0 and now.minute < 5:
        sent_memes_today = set()

async def fetch_unique_memes(batch_size=5, subreddit=None):
    memes = []
    tries = 0
    while len(memes) < batch_size and tries < batch_size * 4:
        meme = await fetch_meme_from_api(subreddit=subreddit)
        if meme and meme['post_link'] not in sent_memes_today:
            sent_memes_today.add(meme['post_link'])
            memes.append(meme)
        tries += 1
    return memes

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

def clear_session():
    global current_batch, current_ctx, current_wait_task, current_subreddit
    current_batch = []
    current_ctx = None
    current_subreddit = None
    if current_wait_task and not current_wait_task.done():
        current_wait_task.cancel()
    current_wait_task = None

async def send_batch_for_validation(memes, ctx):
    global current_batch, current_ctx, current_wait_task
    current_batch = memes
    current_ctx = ctx
    desc = ""
    for idx, meme in enumerate(memes, start=1):
        desc += f"**{idx}. {meme['title']}**\n{meme['url']}\n\n"
    await ctx.send(f"Here are some memes for today!\nReply `yes <number>` to post, `no` for new batch, or `!stop` to cancel.\n\n{desc}")

    def check(m):
        return m.author.id == OWNER_ID and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=3600)
        content = msg.content.lower().strip()
        if content.startswith("yes"):
            parts = content.split()
            if len(parts) == 2 and parts[1].isdigit():
                choice = int(parts[1])
                if 1 <= choice <= len(memes):
                    meme = memes[choice - 1]
                    channel = bot.get_channel(MEME_CHANNEL_ID)
                    # Post clean with only image URL:
                    await channel.send(meme["url"])
                    await ctx.send("✅ Meme published!")
                    clear_session()
                    return
            await ctx.send("Invalid selection. Please reply again with `yes <number>`.")
            await send_batch_for_validation(memes, ctx)
        elif content == "no":
            await ctx.send("Okay, fetching a new batch...")
            await start_fetching_session(ctx, subreddit=current_subreddit)
        elif content == "!stop":
            await ctx.send("Session stopped, memes discarded.")
            clear_session()
        else:
            await ctx.send("Invalid response. Please reply with `yes <number>`, `no`, or `!stop`.")
            await send_batch_for_validation(memes, ctx)
    except asyncio.TimeoutError:
        await ctx.send("⌛ No response in time, session discarded.")
        clear_session()

async def start_fetching_session(ctx, subreddit=None):
    global current_subreddit
    current_subreddit = subreddit
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
        await ctx.send("Fetching a fresh batch of memes for you 🧙‍♂️...")
        await start_fetching_session(ctx)
    else:
        await ctx.send("This command can only be used by the owner in DMs.")

@bot.command()
async def fetchsub(ctx, subreddit: str):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        await ctx.send(f"Fetching a fresh batch from r/{subreddit} 🧙‍♂️...")
        await start_fetching_session(ctx, subreddit=subreddit)
    else:
        await ctx.send("This command can only be used by the owner in DMs.")

@bot.command()
async def stop(ctx):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        clear_session()
        await ctx.send("Fetching session stopped and memes discarded.")
    else:
        await ctx.send("This command can only be used by the owner in DMs.")

@bot.command()
async def post(ctx, *, args):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        try:
            parts = args.strip().split()
            if len(parts) < 2:
                await ctx.send("❌ Usage: `!post <custom-title> <image-url>`")
                return
            image_url = parts[-1]
            custom_title = " ".join(parts[:-1])
            channel = bot.get_channel(MEME_CHANNEL_ID)

            # Post clean with custom title + image URL
            await channel.send(f"**{custom_title}**\n{image_url}")
            sent_memes_today.add(image_url)

            await ctx.send("✅ Meme posted successfully!")
        except Exception as e:
            await ctx.send(f"❌ Error posting meme: {e}")
    else:
        await ctx.send("This command can only be used by the owner in DMs.")

@bot.command()
async def help(ctx):
    help_text = (
        "**Available Commands:**\n"
        "`!fetch` - Fetch a fresh batch of random memes for validation.\n"
        "`!fetchsub <subreddit>` - Fetch a fresh batch of memes from a specific subreddit.\n"
        "`!stop` - Stop the current meme fetching session.\n"
        "`!post <custom-title> <image-url>` - Instantly post a meme with a custom title to the meme channel.\n"
        "`!help` - Display this help message.\n\n"
        "Reply with `yes <number>` to post a meme from a batch, `no` for a new batch, or `!stop` to cancel during a fetching session."
    )
    await ctx.send(help_text)

@bot.event
async def on_ready():
    print(f"⚡ Ron Weasley meme bot ready as {bot.user}!")
    bot.loop.create_task(status_loop())

async def status_loop():
    day_statuses = [
        "🧹 Practicing Quidditch",
        "🐭 Chasing Scabbers",
        "🍽️ Eating at the Great Hall",
        "🏰 Exploring Hogwarts"
    ]

    night_statuses = [
        "🌙 Dreaming of the Chudley Cannons",
        "💤 Sleeping in the Gryffindor Tower",
        "✨ Watching the stars from the Astronomy Tower"
    ]

    while True:
        hour_utc = datetime.utcnow().hour
        local_hour = (hour_utc + TIMEZONE_OFFSET) % 24

        if 6 <= local_hour < 22:
            status_message = random.choice(day_statuses)
        else:
            status_message = random.choice(night_statuses)

        activity = discord.Game(status_message)
        await bot.change_presence(activity=activity)

        await asyncio.sleep(7200)  # update every 2 hours

bot.run(TOKEN)
