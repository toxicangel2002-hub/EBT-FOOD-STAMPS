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
CREATE TABLE IF NOT EXISTS license_config(
guild_id TEXT PRIMARY KEY,
apply_channel TEXT,
staff_channel TEXT,
staff_role TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS licensed_businesses(
guild_id TEXT,
owner_id TEXT,
business_name TEXT,
items TEXT,
status TEXT
)
""")

conn.commit()

pay_cooldowns = {}

# ---------------- UI CLASSES ---------------- #

class CloseTicket(discord.ui.View):

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.grey)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()


class LicenseApproval(discord.ui.View):

    def __init__(self, ticket_channel_id, owner_id, business_name, items):
        super().__init__()
        self.ticket_channel_id = ticket_channel_id
        self.owner_id = owner_id
        self.business_name = business_name
        self.items = items

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):

        cursor.execute(
            "INSERT INTO licensed_businesses VALUES(?,?,?,?,?)",
            (interaction.guild.id, self.owner_id, self.business_name, self.items, "active")
        )

        conn.commit()

        ticket = interaction.guild.get_channel(self.ticket_channel_id)

        await ticket.send(
            f"<@{self.owner_id}> License approved. You may now accept EBT.",
            view=CloseTicket()
        )

        await interaction.response.send_message("License approved.", ephemeral=True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):

        ticket = interaction.guild.get_channel(self.ticket_channel_id)

        await ticket.send(
            "License denied. Please review EBT rules.",
            view=CloseTicket()
        )

        await interaction.response.send_message("License denied.", ephemeral=True)


class ApplicationModal(discord.ui.Modal, title="EBT Business Application"):

    business = discord.ui.TextInput(label="Business Name")
    owner = discord.ui.TextInput(label="Business Owner")
    items = discord.ui.TextInput(label="Items Sold (comma separated)")
    fairs = discord.ui.TextInput(label="Do you host fairs or festivals?")
    events = discord.ui.TextInput(label="Do you host regular events?")

    async def on_submit(self, interaction: discord.Interaction):

        items = self.items.value.lower().split(",")

        cursor.execute(
            "SELECT item FROM blocked_items WHERE guild_id=?",
            (interaction.guild.id,)
        )

        blocked = [x[0] for x in cursor.fetchall()]

        allowed = []
        blocked_found = []

        for item in items:
            item = item.strip()

            if item in blocked:
                blocked_found.append(item)
            else:
                allowed.append(item)

        embed = discord.Embed(
            title="Item Compliance Check",
            color=discord.Color.orange()
        )

        embed.add_field(
            name="Allowed Items",
            value=", ".join(allowed) if allowed else "None"
        )

        embed.add_field(
            name="Blocked Items",
            value=", ".join(blocked_found) if blocked_found else "None"
        )

        await interaction.channel.send(embed=embed)

        cursor.execute(
            "SELECT staff_channel, staff_role FROM license_config WHERE guild_id=?",
            (interaction.guild.id,)
        )

        config = cursor.fetchone()

        staff_channel = interaction.guild.get_channel(int(config[0]))
        staff_role = interaction.guild.get_role(int(config[1]))

        approval_embed = discord.Embed(
            title="New EBT License Application",
            color=discord.Color.blue()
        )

        approval_embed.add_field(name="Business", value=self.business.value)
        approval_embed.add_field(name="Applicant", value=interaction.user.mention)
        approval_embed.add_field(name="Owner Listed", value=self.owner.value)
        approval_embed.add_field(name="Allowed Items", value=", ".join(allowed))
        approval_embed.add_field(name="Hosts Fairs", value=self.fairs.value)
        approval_embed.add_field(name="Regular Events", value=self.events.value)

        await staff_channel.send(
            f"{staff_role.mention}",
            embed=approval_embed,
            view=LicenseApproval(interaction.channel.id, interaction.user.id, self.business.value, ",".join(allowed))
        )


class ApplyButton(discord.ui.View):

    @discord.ui.button(label="Apply for EBT License", style=discord.ButtonStyle.green)
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):

        guild = interaction.guild

        cursor.execute(
            "SELECT staff_role FROM license_config WHERE guild_id=?",
            (guild.id,)
        )

        role_id = cursor.fetchone()[0]
        role = guild.get_role(int(role_id))

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True),
            role: discord.PermissionOverwrite(view_channel=True),
            guild.me: discord.PermissionOverwrite(view_channel=True)
        }

        channel = await guild.create_text_channel(
            f"ebt-app-{interaction.user.name}",
            overwrites=overwrites
        )

        await channel.send(f"{interaction.user.mention} welcome to your EBT license application.")

        await interaction.response.send_modal(ApplicationModal())


# ---------------- EVENTS ---------------- #

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not monthly_reload.is_running():
        monthly_reload.start()
    print("EBT BOT ONLINE")

# ---------------- COMMANDS ---------------- #

@bot.tree.command(name="issuecard")
@commands.has_permissions(administrator=True)
async def issuecard(interaction: discord.Interaction, user: discord.Member):

    cursor.execute(
        "INSERT OR IGNORE INTO cards VALUES(?,?,?,?)",
        (user.id, interaction.guild.id, 500, "active")
    )

    conn.commit()

    await interaction.response.send_message(f"EBT card issued to {user.mention}")


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


@bot.tree.command(name="blockitem")
@commands.has_permissions(administrator=True)
async def blockitem(interaction: discord.Interaction, item: str):

    cursor.execute(
        "INSERT INTO blocked_items VALUES(?,?)",
        (interaction.guild.id, item.lower())
    )

    conn.commit()

    await interaction.response.send_message(f"{item} blocked from EBT purchases.")


@bot.tree.command(name="setup_ebt_licensing")
@commands.has_permissions(administrator=True)
async def setup_ebt_licensing(
interaction: discord.Interaction,
apply_channel: discord.TextChannel,
staff_channel: discord.TextChannel,
staff_role: discord.Role
):

    cursor.execute(
        "INSERT OR REPLACE INTO license_config VALUES(?,?,?,?)",
        (interaction.guild.id, apply_channel.id, staff_channel.id, staff_role.id)
    )

    conn.commit()

    embed = discord.Embed(
        title="EBT Business License Applications",
        description="Click below to apply for EBT acceptance.",
        color=discord.Color.green()
    )

    view = ApplyButton()

    await apply_channel.send(embed=embed, view=view)

    await interaction.response.send_message("EBT licensing system setup.", ephemeral=True)


@bot.tree.command(name="pay")
async def pay(interaction: discord.Interaction, user: discord.Member, amount: int, item: str):

    cursor.execute(
        "SELECT * FROM licensed_businesses WHERE guild_id=? AND owner_id=? AND status='active'",
        (interaction.guild.id, user.id)
    )

    business = cursor.fetchone()

    if not business:
        await interaction.response.send_message(
            "This user is not a registered EBT business.",
            ephemeral=True
        )
        return

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

    new_balance = balance - amount

    cursor.execute(
        "UPDATE cards SET balance=? WHERE user_id=? AND guild_id=?",
        (new_balance, interaction.user.id, interaction.guild.id)
    )

    conn.commit()

    embed = discord.Embed(
        title="EBT Purchase Receipt",
        color=discord.Color.green()
    )

    embed.add_field(name="Customer", value=interaction.user.mention)
    embed.add_field(name="Store Clerk", value=user.mention)
    embed.add_field(name="Item", value=item)
    embed.add_field(name="Cost", value=amount)
    embed.add_field(name="Remaining EBT Balance", value=new_balance)

    embed.add_field(
        name="Cash To Issue",
        value=f"!cash add {user.mention} {amount}"
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="end_license")
@commands.has_permissions(administrator=True)
async def end_license(interaction: discord.Interaction, user: discord.Member):

    cursor.execute(
        "DELETE FROM licensed_businesses WHERE guild_id=? AND owner_id=?",
        (interaction.guild.id, user.id)
    )

    conn.commit()

    await interaction.response.send_message("EBT license removed.")


# ---------------- MONTHLY RELOAD ---------------- #

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
