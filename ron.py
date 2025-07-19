import os
import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from dotenv import load_dotenv
from datetime import datetime, time as dtime
import pytz

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
MEME_CHANNEL_ID = int(os.getenv("MEME_CHANNEL_ID"))

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# To keep track of memes sent today to avoid repeats
sent_today_urls = set()

async def fetch_meme_from_api(subreddit=None):
    url = "https://meme-api.com/gimme"
    if subreddit:
        url += f"/{subreddit}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return {
                "title": data.get("title"),
                "post_link": data.get("postLink"),
                "url": data.get("url")
            }

async def fetch_batch(subreddit=None, batch_size=5):
    memes = []
    tries = 0
    max_tries = batch_size * 3  # avoid infinite loop
    while len(memes) < batch_size and tries < max_tries:
        meme = await fetch_meme_from_api(subreddit)
        tries += 1
        if meme and meme["url"] not in sent_today_urls:
            memes.append(meme)
            sent_today_urls.add(meme["url"])
    return memes

async def send_batch_for_validation(ctx, subreddit=None):
    memes = await fetch_batch(subreddit=subreddit)
    if not memes:
        await ctx.send("Sorry, couldn't fetch any new memes right now.")
        return

    # Send numbered list with images
    description = "\n\n".join(
        f"**{i+1}. {m['title']}**\n{m['url']}"
        for i, m in enumerate(memes)
    )
    await ctx.send(
        "Here are some memes for you to choose from! Reply with `yes <number>` to publish that meme, or `no` to get a new batch.\n\n"
        + description
    )

    def check(m):
        return (
            m.author.id == OWNER_ID and 
            isinstance(m.channel, discord.DMChannel) and
            (m.content.lower().startswith("yes") or m.content.lower() == "no")
        )

    try:
        while True:
            reply = await bot.wait_for("message", check=check, timeout=300)
            content = reply.content.lower()
            if content == "no":
                await ctx.send("Okay, fetching a new batch...")
                await send_batch_for_validation(ctx, subreddit)
                return
            elif content.startswith("yes"):
                parts = content.split()
                if len(parts) == 2 and parts[1].isdigit():
                    idx = int(parts[1]) - 1
                    if 0 <= idx < len(memes):
                        meme = memes[idx]
                        channel = bot.get_channel(MEME_CHANNEL_ID)
                        embed = discord.Embed(
                            title=meme["title"],
                            url=meme["post_link"],
                            description="*“It’s not really magic, it’s just a bit of wizardry!”* — Ron Weasley 🧙‍♂️"
                        )
                        embed.set_image(url=meme["url"])
                        await channel.send(embed=embed)
                        await ctx.send("✅ Meme published to the channel!")
                        return
                    else:
                        await ctx.send("Invalid number, please reply with a valid meme number.")
                else:
                    await ctx.send("Please reply with 'yes <number>' where <number> is the meme number.")
    except asyncio.TimeoutError:
        await ctx.send("⌛ Timeout: No response, cancelling meme selection.")

@bot.command()
async def fetch(ctx):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        await ctx.send("Fetching a batch of memes for you 🧙‍♂️...")
        await send_batch_for_validation(ctx)
    else:
        await ctx.send("Sorry, this command can only be used by the owner in DMs.")

@bot.command()
async def fetchsub(ctx, subreddit: str):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        await ctx.send(f"Fetching a batch of memes from r/{subreddit} 🧙‍♂️...")
        await send_batch_for_validation(ctx, subreddit)
    else:
        await ctx.send("Sorry, this command can only be used by the owner in DMs.")

@tasks.loop(minutes=1)
async def daily_meme_fetcher():
    tz = pytz.timezone('Europe/Paris')
    now = datetime.now(tz)
    target_time = dtime(hour=20, minute=0)

    if now.time().hour == target_time.hour and now.time().minute == target_time.minute:
        owner = await bot.fetch_user(OWNER_ID)
        await owner.send("⏰ It's 8 PM, fetching your daily meme for validation!")
        await send_batch_for_validation(owner)

bot.run(TOKEN)
