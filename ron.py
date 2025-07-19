import os
import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from dotenv import load_dotenv
from datetime import datetime, time as dtime, timedelta
import pytz

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
MEME_CHANNEL_ID = int(os.getenv("MEME_CHANNEL_ID"))

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.dm_messages = True
intents.reactions = True  # Important for reaction tracking
bot = commands.Bot(command_prefix="!", intents=intents)

# Store URLs of memes sent today to avoid duplicates
sent_memes_today = set()
last_reset_date = datetime.now().date()

BATCH_SIZE = 5

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

async def fetch_batch(subreddit=None):
    batch = []
    tries = 0
    while len(batch) < BATCH_SIZE and tries < BATCH_SIZE * 5:
        meme = await fetch_meme_from_api(subreddit)
        if meme and meme["url"] not in sent_memes_today:
            batch.append(meme)
            sent_memes_today.add(meme["url"])
        tries += 1
    return batch

async def send_batch_for_validation(ctx, subreddit=None):
    global last_reset_date
    # Reset daily cache if day changed
    if datetime.now().date() != last_reset_date:
        sent_memes_today.clear()
        last_reset_date = datetime.now().date()

    batch = await fetch_batch(subreddit)
    if not batch:
        await ctx.send("Sorry, no new memes available right now.")
        return

    # Send each meme as its own message with number
    sent_messages = []
    for i, meme in enumerate(batch, start=1):
        msg = await ctx.send(
            f"**{i}. {meme['title']}**\n(React ✅ to approve)\n{meme['url']}"
        )
        sent_messages.append((msg, meme))

        # Add ✅ reaction so you can just click it
        await msg.add_reaction("✅")

    await ctx.send("React with ✅ to the meme you want to publish, or reply `no` to get a new batch.")

    def check_reaction(reaction, user):
        return (
            user.id == OWNER_ID and
            reaction.message in [m[0] for m in sent_messages] and
            str(reaction.emoji) == "✅"
        )

    def check_message(message):
        return (
            message.author.id == OWNER_ID and
            message.channel == ctx.channel and
            message.content.lower() == "no"
        )

    try:
        done, pending = await asyncio.wait(
            [
                bot.wait_for("reaction_add", check=check_reaction, timeout=300),
                bot.wait_for("message", check=check_message, timeout=300)
            ],
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        for task in done:
            result = task.result()
            if isinstance(result, tuple):  # reaction_add returns (reaction, user)
                reaction, user = result
                # Find which meme was approved
                approved_msg = reaction.message
                approved_meme = None
                for msg, meme in sent_messages:
                    if msg.id == approved_msg.id:
                        approved_meme = meme
                        break
                if approved_meme:
                    channel = bot.get_channel(MEME_CHANNEL_ID)
                    # Post the meme nicely (embed with image + Ron Weasley text)
                    embed = discord.Embed(
                        title=approved_meme["title"],
                        url=approved_meme["post_link"],
                        description="*“It’s not really magic, it’s just a bit of wizardry!”* — Ron Weasley 🧙‍♂️"
                    )
                    embed.set_image(url=approved_meme["url"])
                    await channel.send(embed=embed)
                    await ctx.send("✅ Meme published to the channel!")
                else:
                    await ctx.send("Something went wrong finding the approved meme.")
            else:  # message 'no' received
                await ctx.send("Fetching a new batch for you...")
                await send_batch_for_validation(ctx, subreddit)
    except asyncio.TimeoutError:
        await ctx.send("⌛ Timeout, no meme approved.")

@bot.command()
async def fetchbatch(ctx, subreddit: str = None):
    if isinstance(ctx.channel, discord.DMChannel) and ctx.author.id == OWNER_ID:
        await ctx.send("Alright, fetching a batch of memes for you 🧙‍♂️...")
        await send_batch_for_validation(ctx, subreddit)
    else:
        await ctx.send("Sorry, this command can only be used by the owner in DMs.")

@bot.event
async def on_ready():
    print(f"⚡ Ron Weasley bot ready as {bot.user}!")
    daily_meme_fetcher.start()

@tasks.loop(minutes=1)
async def daily_meme_fetcher():
    tz = pytz.timezone('Europe/Paris')  # GMT+2 with daylight saving
    now = datetime.now(tz)
    target_time = dtime(hour=20, minute=0)  # 8 PM

    # If the current time is within the first minute of the target time
    if now.time().hour == target_time.hour and now.time().minute == target_time.minute:
        owner = await bot.fetch_user(OWNER_ID)
        await owner.send("⏰ It's 8 PM, fetching your daily meme for validation!")
        await send_batch_for_validation(owner)

bot.run(TOKEN)
