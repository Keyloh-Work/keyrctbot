import os
import discord
from discord.ext import commands, tasks
import random
import csv
import chardet
import aiohttp
import asyncio
from datetime import datetime, timedelta
import pytz

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

user_uses = {}
image_cache = {}
reset_time = {"day": "Saturday", "time": "00:00"}
tz = pytz.timezone('Asia/Tokyo')  # ここでタイムゾーンを指定

def add_emoji_to_rarity(rarity):
    if rarity == "N":
        return "🌈 N"
    elif rarity == "R":
        return "💫 R 💫"
    elif rarity == "SR":
        return "✨ 🌟 SR 🌟 ✨"
    elif rarity == "SSR":
        return "🎉✨✨👑 SSR 👑✨✨🎉"
    return rarity

async def fetch_image(session, url, retries=3, delay=2):
    for attempt in range(retries):
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.read()
        except aiohttp.ClientError:
            pass
        await asyncio.sleep(delay)
    return None

async def cache_images():
    with open('gacha_data.csv', 'rb') as f:
        result = chardet.detect(f.read())
    encoding = result['encoding']
    
    gacha_data = []
    try:
        with open('gacha_data.csv', newline='', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                gacha_data.append({
                    "url": row["url"],
                    "chname": row["chname"],
                    "rarity": row["rarity"],
                    "rate": float(row["rate"])
                })
    except Exception:
        return None
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for item in gacha_data:
            tasks.append(fetch_image(session, item["url"]))
        images = await asyncio.gather(*tasks)
        
        for item, image in zip(gacha_data, images):
            if image is not None:
                image_cache[item["url"]] = image

async def get_random_url():
    gacha_data = []
    with open('gacha_data.csv', 'rb') as f:
        result = chardet.detect(f.read())
    encoding = result['encoding']
    
    try:
        with open('gacha_data.csv', newline='', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                gacha_data.append({
                    "url": row["url"],
                    "chname": row["chname"],
                    "rarity": add_emoji_to_rarity(row["rarity"]),
                    "rate": float(row["rate"])
                })
    except Exception:
        return None
    
    total_rate = sum(item["rate"] for item in gacha_data)
    random_value = random.uniform(0, total_rate)
    current_rate = 0
    
    for item in gacha_data:
        current_rate += item["rate"]
        if random_value <= current_rate:
            return item
    return gacha_data[-1]

async def animate_embed(ctx, url_info):
    embed = discord.Embed(title="ガチャ中…", color=discord.Color.default())
    message = await ctx.send(embed=embed)
    await asyncio.sleep(1)
    
    embed.title = "Renact夏休みガチャ"
    await message.edit(embed=embed)
    await asyncio.sleep(1)
    
    embed.add_field(name="キャラ", value=url_info['chname'], inline=True)
    await message.edit(embed=embed)
    await asyncio.sleep(1)
    
    embed.add_field(name="レア度", value="...", inline=True)
    await message.edit(embed=embed)
    await asyncio.sleep(1)
    
    embed.set_field_at(1, name="レア度", value=url_info['rarity'], inline=True)
    await message.edit(embed=embed)
    await asyncio.sleep(1)
    
    embed.add_field(name="URL", value=url_info['url'], inline=False)
    embed.set_image(url=url_info['url'])
    await message.edit(embed=embed)

    await asyncio.sleep(2)
    updated_message = await ctx.fetch_message(message.id)
    if not updated_message.embeds[0].image.url:
        embed.set_image(url=url_info['url'])
        await message.edit(embed=embed)
        await asyncio.sleep(2)
        updated_message = await ctx.fetch_message(message.id)
        if not updated_message.embeds[0].image.url:
            await ctx.send("画像の読み込みに失敗しました。", ephemeral=True)

@bot.command()
async def gacha(ctx):
    if isinstance(ctx.channel, discord.Thread) and ctx.channel.name.startswith('gacha-thread-'):
        user_id = ctx.author.id
        if user_id not in user_uses:
            user_uses[user_id] = 0
        
        if user_uses[user_id] >= 10:
            await ctx.send("ガチャは10回までしか回せません。", ephemeral=True)
        else:
            url_info = await get_random_url()
            if url_info is None:
                await ctx.send("ガチャデータの読み込みに失敗しました。", ephemeral=True)
                return
            
            await animate_embed(ctx, url_info)
            
            user_uses[user_id] += 1
    else:
        await ctx.send("このコマンドは専用のガチャスレッド内でのみ使用できます。")

@bot.command()
async def creategachathread(ctx):
    if ctx.channel.name != "gacha-channel":
        await ctx.send("このコマンドは専用のガチャチャンネルでのみ使用できます。", ephemeral=True)
        return

    guild = ctx.guild
    category = ctx.channel.category
    
    existing_thread = discord.utils.get(ctx.channel.threads, name=f'gacha-thread-{ctx.author.id}')
    
    if existing_thread:
        await ctx.send("すでにあなたのためのgacha-threadが存在します。", ephemeral=True)
    else:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.author: discord.PermissionOverwrite(read_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        
        gacha_thread = await ctx.channel.create_thread(name=f'gacha-thread-{ctx.author.id}', type=discord.ChannelType.private_thread)
        await gacha_thread.add_user(ctx.author)
        await gacha_thread.edit(slowmode_delay=10)
        
        await gacha_thread.send(
            f"{ctx.author.mention}\nここはあなた専用のガチャスレッドです。このスレッドで/gachaとメッセージを送信することでランダムなイラストが表示されます。\n"
            "**注意：このスレッドからは退出しないでください。コマンドが使えなくなります。**\n\n"
            f"@{ctx.author.name}\nThis is your dedicated gacha thread. By sending the message /gacha in this thread, a random illustration will be displayed.\n"
            "**Note: Please do not leave this thread. The commands will no longer work if you do.**"
        )

@bot.command()
@commands.has_permissions(administrator=True)
async def gachareset(ctx, member: discord.Member = None):
    if member:
        user_id = member.id
        user_uses[user_id] = 0
        await ctx.send(f"{member.mention}のガチャ回数制限がリセットされました。", ephemeral=True)
    else:
        user_id = ctx.author.id
        user_uses[user_id] = 0
        await ctx.send("あなたのガチャ回数制限がリセットされました。", ephemeral=True)

@bot.command()
@commands.has_permissions(administrator=True)
async def resetall(ctx):
    global user_uses
    user_uses = {}
    await ctx.send("全ユーザーのガチャ回数制限をリセットしました。")

@bot.command()
@commands.has_permissions(administrator=True)
async def setreset(ctx, day: str, time: str):
    global reset_time
    reset_time = {"day": day, "time": time}
    await ctx.send(f"ガチャ回数制限のリセットが{day}の{time}に設定されました。")

@tasks.loop(minutes=1)
async def scheduled_reset():
    now = datetime.now(tz)
    day_of_week = now.strftime("%A")
    current_time = now.strftime("%H:%M")

    if day_of_week == reset_time["day"] and current_time == reset_time["time"]:
        user_uses.clear()
        channel = discord.utils.get(bot.get_all_channels(), name="general")
        if channel:
            await channel.send("ガチャ回数制限がリセットされました。")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')
    await cache_images()
    scheduled_reset.start()

TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable not set")
bot.run(TOKEN)
