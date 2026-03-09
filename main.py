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
questions TEXT,
food INTEGER,
tools INTEGER,
alcohol INTEGER,
medical INTEGER,
building INTEGER
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

conn.commit()


# CATEGORY TOGGLE UI

class CategoryToggle(discord.ui.View):

    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    async def toggle(self, interaction, column):

        cursor.execute(f"SELECT {column} FROM config WHERE guild_id=?",
                       (self.guild_id,))
        value = cursor.fetchone()[0]

        new_value = 0 if value == 1 else 1

        cursor.execute(f"UPDATE config SET {column}=? WHERE guild_id=?",
                       (new_value, self.guild_id))
        conn.commit()

        status = "ENABLED" if new_value == 1 else "DISABLED"

        await interaction.response.send_message(
            f"{column.capitalize()} purchases now **{status}**",
            ephemeral=True
        )

    @discord.ui.button(label="Food", style=discord.ButtonStyle.green)
    async def food(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle(interaction, "food")

    @discord.ui.button(label="Tools", style=discord.ButtonStyle.gray)
    async def tools(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle(interaction, "tools")

    @discord.ui.button(label="Alcohol", style=discord.ButtonStyle.red)
    async def alcohol(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle(interaction, "alcohol")

    @discord.ui.button(label="Medical", style=discord.ButtonStyle.blurple)
    async def medical(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle(interaction, "medical")

    @discord.ui.button(label="Building", style=discord.ButtonStyle.gray)
    async def building(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle(interaction, "building")


# PLAYER APPLICATION

class ApplyEBT(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply for EBT", style=discord.ButtonStyle.green)
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):

        cursor.execute(
            "SELECT questions, player_review_channel FROM config WHERE guild_id=?",
            (interaction.guild.id,))
        data = cursor.fetchone()

        questions = data[0].split("|")
        review_channel = interaction.guild.get_channel(data[1])

        await interaction.response.send_message(
            "Check DMs for the application.",
            ephemeral=True
        )

        answers = []

        for q in questions:

            await interaction.user.send(q)

            def check(m):
                return m.author == interaction.user and isinstance(m.channel, discord.DMChannel)

            msg = await bot.wait_for("message", check=check)
            answers.append(msg.content)

        embed = discord.Embed(title="New EBT Application", color=0x2ecc71)

        embed.add_field(name="Applicant", value=interaction.user.mention)

        for i, q in enumerate(questions):
            embed.add_field(name=q, value=answers[i], inline=False)

        view = ReviewApplication(interaction.user.id)

        await review_channel.send(embed=embed, view=view)


# STAFF APPROVAL

class ReviewApplication(discord.ui.View):

    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.defer()

        cursor.execute(
            "SELECT starting_balance, recipient_role FROM config WHERE guild_id=?",
            (interaction.guild.id,))
        data = cursor.fetchone()

        member = interaction.guild.get_member(self.user_id)
        role = interaction.guild.get_role(data[1])

        cursor.execute(
            "INSERT INTO cards VALUES(?,?,?)",
            (self.user_id, interaction.guild.id, data[0]))
        conn.commit()

        await member.add_roles(role)

        await interaction.followup.send("EBT application approved.")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message("Application denied.")


# BUSINESS LICENSE

class ApplyBusiness(discord.ui.View):

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
            description=f"{interaction.user.mention} applied for EBT license"
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

        await interaction.response.defer()

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

        await interaction.followup.send("Business approved.")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):

        await interaction.response.send_message("Application denied.")


# SETUP COMMAND

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
        """INSERT OR REPLACE INTO config VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,1,0,1,1)""",
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
        "Apply for EBT below:",
        view=ApplyEBT()
    )

    await business_application_channel.send(
        "Apply for an EBT Business License:",
        view=ApplyBusiness()
    )

    await interaction.response.send_message("EBT system setup complete.")


# CATEGORY COMMAND

@bot.tree.command()
async def ebt_categories(interaction: discord.Interaction):

    view = CategoryToggle(interaction.guild.id)

    await interaction.response.send_message(
        "Toggle which item categories EBT can purchase:",
        view=view
    )


# BALANCE

@bot.tree.command()
async def balance(interaction: discord.Interaction):

    cursor.execute(
        "SELECT balance FROM cards WHERE user_id=? AND guild_id=?",
        (interaction.user.id, interaction.guild.id))
    data = cursor.fetchone()

    if not data:
        await interaction.response.send_message("You do not have an EBT card.")
        return

    await interaction.response.send_message(f"Balance: ${data[0]}")


# PAY

@bot.tree.command()
async def pay(
interaction: discord.Interaction,
business: discord.Member,
amount: int,
item: str,
category: str
):

    cursor.execute(
        f"SELECT {category.lower()} FROM config WHERE guild_id=?",
        (interaction.guild.id,))
    allowed = cursor.fetchone()[0]

    if allowed == 0:
        await interaction.response.send_message(
            "EBT cannot be used for that category."
        )
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

    receipt = discord.Embed(title="EBT Receipt", color=0x2ecc71)

    receipt.add_field(name="Buyer", value=interaction.user.mention)
    receipt.add_field(name="Business", value=business.mention)
    receipt.add_field(name="Item", value=item)
    receipt.add_field(name="Category", value=category)
    receipt.add_field(name="Amount", value=f"${amount}")
    receipt.add_field(name="Remaining Balance", value=f"${new_balance}")

    await interaction.response.send_message(embed=receipt)


# MONTHLY RELOAD

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


@bot.event
async def on_ready():
    await bot.tree.sync()
    print("Bot Ready")


bot.run(os.getenv("TOKEN"))
