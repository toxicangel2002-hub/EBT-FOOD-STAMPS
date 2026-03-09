import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

conn = sqlite3.connect("ebt.db")
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS config(
guild_id INTEGER PRIMARY KEY,
monthly_amount INTEGER,
starting_balance INTEGER,
cooldown INTEGER,
player_app_channel INTEGER,
player_review_channel INTEGER,
recipient_role INTEGER,
business_app_channel INTEGER,
business_review_channel INTEGER,
licensed_role INTEGER,
fraud_channel INTEGER,
questions TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS cards(
user_id INTEGER,
guild_id INTEGER,
balance INTEGER
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS licenses(
user_id INTEGER,
guild_id INTEGER
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS blocked_items(
guild_id INTEGER,
item TEXT
)""")

conn.commit()


class ApplyEBTButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply for EBT", style=discord.ButtonStyle.green)
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):

        cursor.execute(
            "SELECT questions, player_review_channel FROM config WHERE guild_id=?",
            (interaction.guild.id,))
        data = cursor.fetchone()

        if not data:
            await interaction.response.send_message("EBT system not configured.", ephemeral=True)
            return

        questions = data[0].split("|")
        review_channel = interaction.guild.get_channel(data[1])

        await interaction.response.send_message(
            "Check your DMs to complete the EBT application.",
            ephemeral=True
        )

        answers = []

        try:
            for q in questions:
                await interaction.user.send(q)

                def check(m):
                    return m.author == interaction.user and isinstance(m.channel, discord.DMChannel)

                msg = await bot.wait_for("message", check=check, timeout=300)
                answers.append(msg.content)

        except:
            await interaction.user.send("Application timed out.")
            return

        embed = discord.Embed(title="New EBT Application", color=0x00ff00)
        embed.add_field(name="Applicant", value=interaction.user.mention)

        for i, q in enumerate(questions):
            embed.add_field(name=q, value=answers[i], inline=False)

        view = ReviewApplication(interaction.user.id)

        await review_channel.send(embed=embed, view=view)


class ReviewApplication(discord.ui.View):

    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        cursor.execute(
            "SELECT starting_balance, recipient_role FROM config WHERE guild_id=?",
            (interaction.guild.id,))
        data = cursor.fetchone()

        balance = data[0]
        role = interaction.guild.get_role(data[1])
        member = interaction.guild.get_member(self.user_id)

        cursor.execute(
            "INSERT INTO cards VALUES(?,?,?)",
            (self.user_id, interaction.guild.id, balance))
        conn.commit()

        await member.add_roles(role)

        await interaction.response.send_message("Application approved.")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Application denied.")


class ApplyBusinessButton(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply for EBT Business License", style=discord.ButtonStyle.blurple)
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):

        cursor.execute(
            "SELECT business_review_channel FROM config WHERE guild_id=?",
            (interaction.guild.id,))
        data = cursor.fetchone()

        review_channel = interaction.guild.get_channel(data[0])

        embed = discord.Embed(
            title="Business License Application",
            description=f"{interaction.user.mention} applied for an EBT license",
            color=0x3498db
        )

        view = BusinessReview(interaction.user.id)

        await review_channel.send(embed=embed, view=view)

        await interaction.response.send_message("Application submitted.", ephemeral=True)


class BusinessReview(discord.ui.View):

    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        cursor.execute(
            "SELECT licensed_role FROM config WHERE guild_id=?",
            (interaction.guild.id,))
        role_id = cursor.fetchone()[0]

        role = interaction.guild.get_role(role_id)
        member = interaction.guild.get_member(self.user_id)

        await member.add_roles(role)

        cursor.execute(
            "INSERT INTO licenses VALUES(?,?)",
            (self.user_id, interaction.guild.id))
        conn.commit()

        await interaction.response.send_message("Business approved.")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Application denied.")


@bot.tree.command()
async def setup_ebt(
interaction: discord.Interaction,
monthly_amount: int,
starting_balance: int,
cooldown: int,
player_application_channel: discord.TextChannel,
player_review_channel: discord.TextChannel,
recipient_role: discord.Role,
business_application_channel: discord.TextChannel,
business_review_channel: discord.TextChannel,
licensed_business_role: discord.Role,
fraud_log_channel: discord.TextChannel,
questions: str
):

    cursor.execute(
        "INSERT OR REPLACE INTO config VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            interaction.guild.id,
            monthly_amount,
            starting_balance,
            cooldown,
            player_application_channel.id,
            player_review_channel.id,
            recipient_role.id,
            business_application_channel.id,
            business_review_channel.id,
            licensed_business_role.id,
            fraud_log_channel.id,
            questions
        )
    )

    conn.commit()

    await player_application_channel.send(
        "Click below to apply for EBT",
        view=ApplyEBTButton()
    )

    await business_application_channel.send(
        "Click below to apply for an EBT business license",
        view=ApplyBusinessButton()
    )

    await interaction.response.send_message("EBT system configured.")


@bot.tree.command()
async def balance(interaction: discord.Interaction):

    cursor.execute(
        "SELECT balance FROM cards WHERE user_id=? AND guild_id=?",
        (interaction.user.id, interaction.guild.id))
    data = cursor.fetchone()

    if not data:
        await interaction.response.send_message("You do not have an EBT card.")
        return

    await interaction.response.send_message(f"Your balance is ${data[0]}")


@bot.tree.command()
async def pay(
interaction: discord.Interaction,
business: discord.Member,
amount: int,
item: str
):

    cursor.execute(
        "SELECT item FROM blocked_items WHERE guild_id=?",
        (interaction.guild.id,))
    blocked = [x[0].lower() for x in cursor.fetchall()]

    if item.lower() in blocked:

        cursor.execute(
            "SELECT fraud_channel FROM config WHERE guild_id=?",
            (interaction.guild.id,))
        channel_id = cursor.fetchone()[0]

        channel = interaction.guild.get_channel(channel_id)

        await channel.send(
            f"EBT FRAUD ATTEMPT\nUser: {interaction.user.mention}\nItem: {item}"
        )

        await interaction.response.send_message("This item is not allowed.")
        return

    cursor.execute(
        "SELECT balance FROM cards WHERE user_id=? AND guild_id=?",
        (interaction.user.id, interaction.guild.id))
    data = cursor.fetchone()

    if not data or data[0] < amount:
        await interaction.response.send_message("Insufficient balance.")
        return

    new_balance = data[0] - amount

    cursor.execute(
        "UPDATE cards SET balance=? WHERE user_id=? AND guild_id=?",
        (new_balance, interaction.user.id, interaction.guild.id))
    conn.commit()

    receipt = discord.Embed(
        title="EBT Transaction Receipt",
        color=0x2ecc71
    )

    receipt.add_field(name="Buyer", value=interaction.user.mention)
    receipt.add_field(name="Business", value=business.mention)
    receipt.add_field(name="Item", value=item)
    receipt.add_field(name="Amount", value=f"${amount}")
    receipt.add_field(name="Remaining Balance", value=f"${new_balance}")

    await interaction.response.send_message(embed=receipt)


@bot.tree.command()
async def blockitem(interaction: discord.Interaction, item: str):

    cursor.execute(
        "INSERT INTO blocked_items VALUES(?,?)",
        (interaction.guild.id, item.lower()))
    conn.commit()

    await interaction.response.send_message(f"{item} blocked from EBT.")


@bot.tree.command()
async def reload_ebt(interaction: discord.Interaction):

    cursor.execute(
        "SELECT monthly_amount FROM config WHERE guild_id=?",
        (interaction.guild.id,))
    amount = cursor.fetchone()[0]

    cursor.execute(
        "SELECT user_id,balance FROM cards WHERE guild_id=?",
        (interaction.guild.id,))
    cards = cursor.fetchall()

    for user_id, bal in cards:
        cursor.execute(
            "UPDATE cards SET balance=? WHERE user_id=? AND guild_id=?",
            (bal + amount, user_id, interaction.guild.id)
        )

    conn.commit()

    await interaction.response.send_message("All EBT balances reloaded.")


@bot.tree.command()
async def end_license(interaction: discord.Interaction, business: discord.Member):

    cursor.execute(
        "DELETE FROM licenses WHERE user_id=? AND guild_id=?",
        (business.id, interaction.guild.id))
    conn.commit()

    await interaction.response.send_message("Business license removed.")


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


bot.run(os.getenv("TOKEN"))
