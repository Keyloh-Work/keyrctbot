import os
import discord
from discord.ext import commands, tasks
import random
import csv
import chardet
import aiohttp
import asyncio

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# 各ユーザーの使用回数を追跡する辞書
user_uses = {}
image_cache = {}  # 画像のキャッシュ

# レア度に応じた絵文字を追加する関数
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

    # Check if the image is successfully loaded
    await asyncio.sleep(2)  # Wait a moment for the image to load
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
        await gacha_thread.send(f"{ctx.author.mention}, this is your private gacha thread!")

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

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')
    await cache_images()

TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable not set")
bot.run(TOKEN)
