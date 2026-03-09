import discord
from discord.ext import commands, tasks
import sqlite3
import datetime
import os

from keep_alive import keep_alive

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print("EBT BOT ONLINE")
    monthly_reload.start()

# DATABASE
conn = sqlite3.connect("ebt.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS cards(
user_id TEXT,
guild_id TEXT,
balance INTEGER,
status TEXT,
PRIMARY KEY(user_id, guild_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS servers(
guild_id TEXT PRIMARY KEY,
monthly_amount INTEGER,
log_channel TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS blocked_items(
guild_id TEXT,
item TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS cases(
case_id INTEGER PRIMARY KEY AUTOINCREMENT,
user_id TEXT,
guild_id TEXT,
reason TEXT,
status TEXT
)
""")

conn.commit()

pay_cooldowns = {}

@bot.event
async def on_ready():
    await bot.tree.sync()
    monthly_reload.start()
    print("EBT BOT ONLINE")

# ISSUE CARD
@bot.tree.command(name="issuecard")
async def issuecard(interaction: discord.Interaction, user: discord.Member):

    cursor.execute(
        "INSERT OR IGNORE INTO cards VALUES(?,?,?,?)",
        (user.id, interaction.guild.id, 500, "active")
    )

    conn.commit()

    await interaction.response.send_message(f"EBT card issued to {user.mention}")

# BALANCE
@bot.tree.command(name="balance")
async def balance(interaction: discord.Interaction):

    cursor.execute(
        "SELECT balance FROM cards WHERE user_id=? AND guild_id=?",
        (interaction.user.id, interaction.guild.id)
    )

    result = cursor.fetchone()

    if not result:
        await interaction.response.send_message("No EBT card found.", ephemeral=True)
        return

    await interaction.response.send_message(f"Balance: {result[0]}")

# PAY
@bot.tree.command(name="pay")
async def pay(interaction: discord.Interaction, user: discord.Member, amount: int, item: str):

    now = datetime.datetime.now()

    if interaction.user.id in pay_cooldowns:
        delta = (now - pay_cooldowns[interaction.user.id]).total_seconds()
        if delta < 300:
            await interaction.response.send_message("Wait 5 minutes before using /pay again.", ephemeral=True)
            return

    pay_cooldowns[interaction.user.id] = now

    cursor.execute(
        "SELECT balance FROM cards WHERE user_id=? AND guild_id=?",
        (interaction.user.id, interaction.guild.id)
    )

    result = cursor.fetchone()

    if not result:
        await interaction.response.send_message("No EBT card.", ephemeral=True)
        return

    balance = result[0]

    if balance < amount:
        await interaction.response.send_message("Insufficient funds.", ephemeral=True)
        return

    # blocked items check
    cursor.execute(
        "SELECT item FROM blocked_items WHERE guild_id=?",
        (interaction.guild.id,)
    )

    blocked = [x[0] for x in cursor.fetchall()]

    for word in blocked:
        if word in item.lower():

            cursor.execute(
                "SELECT log_channel FROM servers WHERE guild_id=?",
                (interaction.guild.id,)
            )

            log = cursor.fetchone()

            if log and log[0]:

                channel = interaction.guild.get_channel(int(log[0]))

                if channel:

                    await channel.send(
                        f"⚠ Fraud Attempt\nUser: {interaction.user.mention}\nItem: {item}"
                    )

            await interaction.response.send_message(
                "Illegal item detected. Admins notified.",
                ephemeral=True
            )

            return

    new_balance = balance - amount

    cursor.execute(
        "UPDATE cards SET balance=? WHERE user_id=? AND guild_id=?",
        (new_balance, interaction.user.id, interaction.guild.id)
    )

    conn.commit()

    await interaction.response.send_message(
        f"{interaction.user.mention} paid {user.mention} {amount} for {item}\nRemaining balance: {new_balance}"
    )

# SET MONTHLY AMOUNT
@bot.tree.command(name="setamount")
async def setamount(interaction: discord.Interaction, amount: int):

    cursor.execute(
        "INSERT OR REPLACE INTO servers VALUES(?,?,?)",
        (interaction.guild.id, amount, None)
    )

    conn.commit()

    await interaction.response.send_message(f"Monthly EBT amount set to {amount}")

# SET FRAUD LOG CHANNEL
@bot.tree.command(name="setlogchannel")
async def setlogchannel(interaction: discord.Interaction, channel: discord.TextChannel):

    cursor.execute(
        "INSERT OR REPLACE INTO servers VALUES(?,?,?)",
        (interaction.guild.id, 500, channel.id)
    )

    conn.commit()

    await interaction.response.send_message("Fraud log channel set.")

# BLOCK ITEM
@bot.tree.command(name="blockitem")
async def blockitem(interaction: discord.Interaction, item: str):

    cursor.execute(
        "INSERT INTO blocked_items VALUES(?,?)",
        (interaction.guild.id, item.lower())
    )

    conn.commit()

    await interaction.response.send_message(f"{item} blocked from EBT purchases.")

# OPEN CASE
@bot.tree.command(name="open_case")
async def open_case(interaction: discord.Interaction, user: discord.Member, reason: str):

    cursor.execute(
        "INSERT INTO cases VALUES(NULL,?,?,?,?)",
        (user.id, interaction.guild.id, reason, "open")
    )

    conn.commit()

    await interaction.response.send_message("Investigation case opened.")

# CLOSE CASE
@bot.tree.command(name="close_case")
async def close_case(interaction: discord.Interaction, case_id: int):

    cursor.execute(
        "UPDATE cases SET status='closed' WHERE case_id=?",
        (case_id,)
    )

    conn.commit()

    await interaction.response.send_message(f"Case {case_id} closed.")

# MONTHLY RELOAD
@tasks.loop(hours=720)
async def monthly_reload():

    cursor.execute("SELECT guild_id, monthly_amount FROM servers")

    for guild_id, amount in cursor.fetchall():

        cursor.execute(
            "UPDATE cards SET balance = balance + ? WHERE guild_id=?",
            (amount, guild_id)
        )

    conn.commit()

keep_alive()
bot.run(TOKEN)
