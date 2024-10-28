import os
import discord
from discord.ext import commands
import random
import csv
import chardet
import aiohttp
import asyncio
import pytz
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import calendar

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# タイムゾーンを東京に設定
JST = pytz.timezone('Asia/Tokyo')
scheduler = AsyncIOScheduler(timezone=JST)
reset_time = None

# 各ユーザーの使用回数と取得したカードNo.を追跡する辞書
user_uses = {}
user_cards = {}

# 画像キャッシュ
image_cache = {}

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

# 画像を非同期に取得する関数
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

# ガチャデータをキャッシュする関数
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
                    "rate": float(row["rate"]),
                    "no": row["No."],
                    "title": row["title"]  # titleを追加
                })
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

    async with aiohttp.ClientSession() as session:
        tasks = []
        for item in gacha_data:
            tasks.append(fetch_image(session, item["url"]))
        images = await asyncio.gather(*tasks)

        for item, image in zip(gacha_data, images):
            if image is not None:
                image_cache[item["url"]] = image

# ランダムなガチャ結果を取得する関数
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
                    "rate": float(row["rate"]),
                    "no": row["No."],
                    "title": row["title"]  # titleを追加
                })
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

    total_rate = sum(item["rate"] for item in gacha_data)
    random_value = random.uniform(0, total_rate)
    current_rate = 0

    for item in gacha_data:
        current_rate += item["rate"]
        if random_value <= current_rate:
            return item
    return gacha_data[-1]

# ガチャ結果をアニメーション風に表示する関数
async def animate_embed(interaction, url_info):
    embed = discord.Embed(title="ガチャ中…", color=discord.Color.default())
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    await asyncio.sleep(1)

    embed.title = "秋のハロウィンガチャ"
    await message.edit(embed=embed)
    await asyncio.sleep(1)

    embed.add_field(name="キャラ", value=url_info['chname'], inline=True)
    await message.edit(embed=embed)
    await asyncio.sleep(1)

    embed.add_field(name="レア度", value="...", inline=True)
    await message.edit(embed=embed)
    await asyncio.sleep(1)

    embed.set_field_at(1, name="レア度", value=url_info['rarity'], inline=True)
    embed.add_field(name="イラストNo.", value=f"No.{url_info['no']}", inline=True)
    embed.add_field(name="タイトル", value=f"{url_info['title']}", inline=True)  # タイトルを追加
    await message.edit(embed=embed)
    await asyncio.sleep(1)

    embed.add_field(name="URL", value=url_info['url'], inline=False)
    embed.set_image(url=url_info['url'])
    await message.edit(embed=embed)

    # 画像が正常に読み込まれたかチェック
    await asyncio.sleep(2)
    updated_message = await interaction.channel.fetch_message(message.id)
    if not updated_message.embeds[0].image.url:
        embed.set_image(url=url_info['url'])
        await message.edit(embed=embed)
        await asyncio.sleep(2)
        updated_message = await interaction.channel.fetch_message(message.id)
        if not updated_message.embeds[0].image.url:
            await interaction.followup.send("画像の読み込みに失敗しました。")

# ページネーション用のボタンビュー
class PaginatorView(discord.ui.View):
    def __init__(self, data, collected_cards, per_page=20):
        super().__init__(timeout=None)
        self.data = data  # 表示するデータ
        self.collected_cards = collected_cards  # ユーザーが取得したカード
        self.per_page = per_page  # 1ページあたりの行数
        self.current_page = 0  # 現在のページ
        self.total_pages = (len(data) + per_page - 1) // per_page  # 総ページ数

    def get_page_content(self):
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_content = []

        for item in self.data[start_idx:end_idx]:
            # カードが取得済みなら :ballot_box_with_check:、未取得なら :blue_square:
            card_no = item["No."]
            title = item["title"]
            if card_no in self.collected_cards:
                page_content.append(f"No.{card_no} {title} :ballot_box_with_check:")
            else:
                page_content.append(f"No.{card_no} {title} :blue_square:")

        return page_content

    async def update_message(self, interaction):
        page_content = "\n".join(self.get_page_content())
        embed = discord.Embed(title=f"{interaction.user.name}のリスト\nPage {self.current_page + 1}/{self.total_pages}", description=page_content)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="<<", style=discord.ButtonStyle.danger)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        await self.update_message(interaction)

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
        await self.update_message(interaction)

    @discord.ui.button(label=">", style=discord.ButtonStyle.success)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
        await self.update_message(interaction)

    @discord.ui.button(label=">>", style=discord.ButtonStyle.primary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self.total_pages - 1
        await self.update_message(interaction)


# ガチャボタンのコールバック
class GachaView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="ガチャを回す！", style=discord.ButtonStyle.primary)
    async def gacha_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        # 回数を優先してチェック
        if user_uses.get(user_id, 10) <= 0:
            await interaction.response.send_message("ガチャは10回までしか回せません。", ephemeral=True)
        else:
            # 残り回数を減らす
            user_uses[user_id] = user_uses.get(user_id, 10) - 1

            url_info = await get_random_url()
            if url_info is None:
                await interaction.response.send_message("ガチャデータの読み込みに失敗しました。", ephemeral=True)
                return

            # ユーザーがそのカードNo.を既に持っているか確認
            if url_info["no"] not in user_cards.get(user_id, []):
                user_cards.setdefault(user_id, []).append(url_info["no"])  # カードNo.を保存

            # 残り回数を表示
            remaining_uses = user_uses.get(user_id, 10)

            # embed を更新して残り回数を表示
            embed = discord.Embed(title="秋のハロウィンガチャ", description=f"下のボタンを押してガチャを回してください。\n残り回数: {remaining_uses} 回")
            await interaction.message.edit(embed=embed)

            # アニメーション風にガチャ結果を表示
            await animate_embed(interaction, url_info)


# ガチャコマンド
@bot.command()
async def gacha(ctx):
    if isinstance(ctx.channel, discord.Thread) and ctx.channel.name.startswith('gacha-thread-'):
        user_id = ctx.author.id  # ユーザーIDを取得
        view = GachaView(user_id)  # GachaViewにuser_idを渡す
        remaining_uses = user_uses.get(user_id, 10)  # 残り回数を取得
        embed = discord.Embed(title="秋のハロウィンガチャ", description=f"下のボタンを押してガチャを回してください。\n残り回数: {remaining_uses} 回")
        await ctx.send(embed=embed, view=view)
    else:
        await ctx.send("このコマンドは専用のガチャスレッド内でのみ使用できます。")


# スレッド作成コマンド
@bot.command()
async def creategachathread(ctx):
    if ctx.channel.name != "gacha-channel":
        await ctx.send("このコマンドは専用のガチャチャンネルでのみ使用できます。")
        return

    guild = ctx.guild
    category = ctx.channel.category
    existing_thread = discord.utils.get(ctx.channel.threads, name=f'gacha-thread-{ctx.author.name}')

    if existing_thread:
        await ctx.send("すでにあなたのためのgacha-threadが存在します。")
    else:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.author: discord.PermissionOverwrite(read_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }

        gacha_thread = await ctx.channel.create_thread(name=f'gacha-thread-{ctx.author.name}', type=discord.ChannelType.private_thread)
        await gacha_thread.add_user(ctx.author)
        await gacha_thread.edit(slowmode_delay=10)

        # メッセージを送信
        await gacha_thread.send(
            f"{ctx.author.mention}\nここはあなた専用のガチャスレッドです。このスレッドで/gachaとメッセージを送信することでボタンが出現します。それを押すことでイラストが表示されます。\n"
            "**注意：このスレッドからは退出しないでください。コマンドが使えなくなります。**\n\n"
            f"@{ctx.author.name}\nThis is your dedicated gacha thread. By sending the message /gacha in this thread, a button will appear. Pressing the button will display an illustration.\n"
            "**Note: Please do not leave this thread. The commands will no longer work if you do.**"
        )

# artlist コマンド
@bot.command()
async def artlist(ctx):
    # gacha-thread-以外のスレッドで実行できないように制限
    if isinstance(ctx.channel, discord.Thread) and ctx.channel.name.startswith('gacha-thread-'):
        user_id = ctx.author.id
        collected_cards = user_cards.get(user_id, [])  # ユーザーが取得したカードNo.

        gacha_data = []
        with open('gacha_data.csv', 'rb') as f:
            result = chardet.detect(f.read())
        encoding = result['encoding']

        with open('gacha_data.csv', newline='', encoding=encoding) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                gacha_data.append({"No.": row["No."], "title": row["title"]})  # No.とタイトルを保存

        if not gacha_data:
            await ctx.send("データが見つかりません。")
            return

        # 最初のページのデータを表示し、ボタン付きのビューを送信
        view = PaginatorView(gacha_data, collected_cards)
        
        # Embedのタイトルを修正して、ユーザーIDを表示する
        embed = discord.Embed(title=f"{ctx.author.name}のリスト\nPage 1", description="\n".join(view.get_page_content()))
        await ctx.send(embed=embed, view=view)
    else:
        # gacha-thread-以外では実行できない場合のエラーメッセージ
        await ctx.send("このコマンドは専用のガチャスレッド内でのみ使用できます。")


# 管理者によるガチャ回数リセットコマンド
@bot.command()
@commands.has_permissions(administrator=True)
async def gachareset(ctx, member: discord.Member = None):
    if member:
        user_id = member.id
        user_uses[user_id] = 10  # 10回にリセット
        await ctx.send(f"{member.mention} のガチャ回数制限がリセットされました。")
    else:
        user_id = ctx.author.id
        user_uses[user_id] = 10
        await ctx.send("あなたのガチャ回数制限がリセットされました。")

# 全てのユーザーのガチャ回数リセットコマンド（管理者専用）
@bot.command()
@commands.has_permissions(administrator=True)
async def gacharesetall(ctx):
    # 全てのユーザーの回数を10回にリセット
    for user_id in user_uses:
        user_uses[user_id] = 10
    await ctx.send("全てのユーザーのガチャ回数制限がリセットされました。")

# 指定したユーザーのリストを管理者が表示するコマンド
@bot.command()
@commands.has_permissions(administrator=True)  # 管理者のみが使えるコマンド
async def artlistuser(ctx, member: discord.Member):
    user_id = member.id
    collected_cards = user_cards.get(user_id, [])  # 指定したユーザーが取得したカードNo.

    gacha_data = []
    with open('gacha_data.csv', 'rb') as f:
        result = chardet.detect(f.read())
    encoding = result['encoding']

    with open('gacha_data.csv', newline='', encoding=encoding) as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            gacha_data.append({"No.": row["No."], "title": row["title"]})  # No.とタイトルを保存

    if not gacha_data:
        await ctx.send("データが見つかりません。")
        return

    # 最初のページのデータを表示し、ボタン付きのビューを送信
    view = PaginatorView(gacha_data, collected_cards)
    
    # Embedのタイトルを修正して、指定したユーザーの名前を表示する
    embed = discord.Embed(title=f"{member.name}のリスト\nPage 1", description="\n".join(view.get_page_content()))
    await ctx.send(embed=embed, view=view)


# /setresetdate コマンドを追加
@bot.command()
@commands.has_permissions(administrator=True)
async def setresetdate(ctx, day_of_week: str, time_str: str):
    global reset_time
    
    # 曜日と時間のパラメータを検証
    try:
        reset_time = f"{day_of_week} {time_str}"
        target_day = day_of_week.capitalize()  # 曜日を統一して扱う
        target_time = datetime.strptime(time_str, '%H:%M').time()
        
        # 現在の時間と設定するリセット時間を計算
        now = datetime.now(JST)
        days_ahead = (list(calendar.day_name).index(target_day) - now.weekday() + 7) % 7
        reset_datetime = (now + timedelta(days=days_ahead)).replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
        
        # スケジューリングをキャンセルして再セット
        scheduler.remove_all_jobs()  # 既存のジョブをリセット
        scheduler.add_job(reset_gacha_uses, 'date', run_date=reset_datetime)
        scheduler.start()  # スケジューリング開始
        
        await ctx.send(f"ガチャ回数のリセットは毎週 {target_day} の {time_str} に設定されました。")
    except ValueError:
        await ctx.send("曜日と時間の形式が正しくありません。例: `/setresetdate Saturday 00:00`")


# ガチャの回数をリセットする関数
def reset_gacha_uses():
    for user_id in user_uses:
        user_uses[user_id] = 10
    print("ガチャの回数がリセットされました。")


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')
    await cache_images()

TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable not set")
bot.run(TOKEN)
