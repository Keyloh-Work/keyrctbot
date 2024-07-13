import discord
from discord.ext import commands
import random
import logging
import os
import csv
from datetime import datetime

# ログ設定
logging.basicConfig(filename='gacha_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# 各ユーザーの使用回数を追跡する辞書
user_uses = {}

class GachaView(discord.ui.View):
    def __init__(self):
        super().__init__()

    @discord.ui.button(label="Gacha!", style=discord.ButtonStyle.primary)
    async def gacha_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id not in user_uses:
            user_uses[user_id] = 0
        
        if user_uses[user_id] >= 10:
            if not interaction.response.is_done():
                await interaction.response.send_message("ガチャは10回までしか回せません。", ephemeral=True)
        else:
            # ガチャの結果を送信する
            url_info = get_random_url()
            embed = discord.Embed(title="テストガチャ")
            embed.set_image(url=url_info['url'])
            embed.add_field(name="Character Name", value=url_info['chname'], inline=False)
            embed.add_field(name="Rarity", value=url_info['rarity'], inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # ログに保存
            user = interaction.user
            log_message = f"{user.name}#{user.discriminator} (ID: {user.id}) got URL: {url_info['url']} with character: {url_info['chname']}, rarity: {url_info['rarity']}"
            logging.info(log_message)
            
            user_uses[user_id] += 1  # ユーザーごとのカウンターを更新

def get_random_url():
    # CSVからガチャデータを読み込む
    gacha_data = []
    with open('gacha_data.csv', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            gacha_data.append({
                "url": row["url"],
                "chname": row["chname"],
                "rarity": row["rarity"],
                "rate": float(row["rate"])
            })
    
    total_rate = sum(item["rate"] for item in gacha_data)
    random_value = random.uniform(0, total_rate)
    current_rate = 0
    
    for item in gacha_data:
        current_rate += item["rate"]
        if random_value <= current_rate:
            return item
    return gacha_data[-1]

@bot.command()
async def gacha(ctx):
    view = GachaView()
    embed = discord.Embed(title="テストガチャ", description="ボタンを押してガチャを回してください。")
    await ctx.send(embed=embed, view=view)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}!')

# 環境変数からトークンを取得してボットを起動する
TOKEN = os.getenv('DISCORD_TOKEN')
bot.run(TOKEN)