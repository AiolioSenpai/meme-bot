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

@bot.event
async def on_ready():
    print(f"⚡ Ron Weasley bot ready as {bot.user}!")
    daily_meme_fetcher.start()

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

async def send_meme_for_validation(meme_data, ctx):
    title = meme_data["title"]
    post_link = meme_data["post_link"]
    meme_url = meme_data["url"]

    await ctx.send(f"**{title}**\n\n{meme_url}\n\nReply `yes` to publish or `no` to discard.")

    def check(m):
        return m.author.id == OWNER_ID and m.channel == ctx.channel and m.content.lower() in ["yes", "no"]

    try:
        reply = await bot.wait_for("message", check=check, timeout=3600)
        if reply.content.lower() == "yes":
            channel = bot.get_channel(MEME_CHANNEL_ID)
            await channel.send(f"**{title}**\n{meme_url}")
            await ctx.send("✅ Meme published to the channel!")
        else:
            await ctx.send("❌ Meme discarded.")
    except asyncio.TimeoutError:
        await ctx.send("⌛ No response in time, meme discarded.")

@bot.command()
async def fetch(ctx):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        await ctx.send("Alright, fetching a meme for you 🧙‍♂️...")
        meme_data = await fetch_meme_from_api()
        if meme_data:
            await send_meme_for_validation(meme_data, ctx)
        else:
            await ctx.send("Sorry, I couldn't fetch a meme from the internet.")
    else:
        await ctx.send("Sorry, this command can only be used by the owner in DMs.")

@bot.command()
async def fetchsub(ctx, subreddit: str):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        await ctx.send(f"Alright, fetching a meme from r/{subreddit} 🧙‍♂️...")
        meme_data = await fetch_meme_from_api(subreddit=subreddit)
        if meme_data:
            await send_meme_for_validation(meme_data, ctx)
        else:
            await ctx.send(f"Sorry, I couldn't fetch a meme from r/{subreddit}. It may not exist or has no memes.")
    else:
        await ctx.send("Sorry, this command can only be used by the owner in DMs.")

@tasks.loop(minutes=1)
async def daily_meme_fetcher():
    tz = pytz.timezone('Europe/Paris')  # GMT+2 with daylight saving
    now = datetime.now(tz)
    target_time = dtime(hour=20, minute=0)  # 8 PM

    # If the current time is within the first minute of the target time
    if now.time().hour == target_time.hour and now.time().minute == target_time.minute:
        owner = await bot.fetch_user(OWNER_ID)
        await owner.send("⏰ It's 8 PM, fetching your daily meme for validation!")
        meme_data = await fetch_meme_from_api()
        if meme_data:
            await send_meme_for_validation(meme_data, owner)
        else:
            await owner.send("Sorry, I couldn't fetch a meme from the internet.")

bot.run(TOKEN)
