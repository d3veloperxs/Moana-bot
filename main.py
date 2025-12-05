# main.py - Moana Scripts SuperBot (nextcord)
# REQUIREMENTS: nextcord
# Run: pip install -U nextcord
# Put your token into environment variable TOKEN (or edit below).

import os
import re
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional



# -----------------------
# CONFIG - paste token to env var 'TOKEN' in Replit / host
# -----------------------

TOKEN = os.getenv("TOKEN")  # recommended to use env var
if not TOKEN:
    print("ERROR: zet je bot token in environment variable TOKEN")
GUILD_ID = 1442599860128976948
WELCOME_CHANNEL = 1446155435819143382
TICKET_CATEGORY = 1446530882721808552
STAFF_ROLE_ID = 1446217175923953704
LOG_CHANNEL_ID = 1446227079824932975

# visual constants
BLUE = 0x3498db
FOOTER = "Moana Scripts - 2025"

# anti-spam/link settings
SPAM_LIMIT = 6          # messages
SPAM_WINDOW = 8         # seconds
SPAM_TIMEOUT = 60       # seconds timeout for spam
LINK_TIMEOUT_MINUTES = 5

# regex for urls
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

# directories
os.makedirs("logs", exist_ok=True)
os.makedirs("transcripts", exist_ok=True)

# logging
logger = logging.getLogger("moana_bot")
logger.setLevel(logging.INFO)
fh = logging.FileHandler("logs/bot.log", encoding="utf-8")
formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)

intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# in-memory spam tracker: user_id -> [timestamps]
spam_tracker = {}

# helper functions
def is_staff(member: nextcord.Member) -> bool:
    try:
        if STAFF_ROLE_ID and member.guild.get_role(STAFF_ROLE_ID) in member.roles:
            return True
    except Exception:
        pass
    return member.guild_permissions.manage_messages

async def save_transcript(channel: nextcord.TextChannel) -> Optional[str]:
    """Save last messages of a channel to transcripts folder and return path."""
    try:
        msgs = []
        async for m in channel.history(limit=2000, oldest_first=True):
            t = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
            author = f"{m.author} ({m.author.id})"
            content = m.content.replace("\n", " ")
            msgs.append(f"[{t}] {author}: {content}")
        filename = f"{channel.name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.txt"
        path = os.path.join("transcripts", filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(msgs))
        logger.info(f"Saved transcript {filename}")
        return path
    except Exception as e:
        logger.exception("save_transcript failed: %s", e)
        return None

async def try_timeout_member(member: nextcord.Member, minutes: int, reason: str):
    """Try to timeout (mute) a member. If API not supporting, ignore."""
    try:
        until = datetime.utcnow() + timedelta(minutes=minutes)
        # nextcord uses edit(timeout=...) in some versions; try both
        try:
            await member.timeout(until, reason=reason)
        except Exception:
            await member.edit(timeout=until)
        logger.info(f"Timed out {member} for {minutes} minutes: {reason}")
    except Exception as e:
        logger.exception("Failed to timeout member: %s", e)

# -----------------------
# EVENTS
# -----------------------
@bot.event
async def on_ready():
    logger.info(f"Bot online as {bot.user}")
    print(f"Bot online as {bot.user}")
    # attempt to sync guild commands
    try:
        await bot.tree.sync(guild=nextcord.Object(id=GUILD_ID))
        logger.info("Slash commands synced.")
    except Exception as e:
        logger.exception("Failed to sync commands: %s", e)

@bot.event
async def on_member_join(member: nextcord.Member):
    try:
        ch = bot.get_channel(WELCOME_CHANNEL)
        if not ch:
            logger.warning("Welcome channel not found.")
            return
        embed = nextcord.Embed(
            title=f"Welkom {member.mention} in **Moana Scripts!**",
            description=f"Wij zijn blij u hier te vinden!\n\n> Wij hebben op het moment **{member.guild.member_count}** Discord leden!",
            color=BLUE
        )
        embed.set_footer(text=FOOTER)
        await ch.send(embed=embed)
        logger.info(f"Sent welcome for {member}")
    except Exception as e:
        logger.exception("on_member_join error: %s", e)

@bot.event
async def on_message(message: nextcord.Message):
    # ignore bots
    if message.author.bot:
        return

    # LINK detection -> if not staff, timeout LINK_TIMEOUT_MINUTES
    if URL_RE.search(message.content):
        try:
            if not is_staff(message.author):
                await try_timeout_member(message.author, LINK_TIMEOUT_MINUTES, "Posting links restricted")
                await message.channel.send(f"{message.author.mention} is tijdelijk gemute voor {LINK_TIMEOUT_MINUTES} minuten (links zijn niet toegestaan).")
                logger.info(f"Link-post timeout applied to {message.author}")
                return
        except Exception as e:
            logger.exception("Link handling error: %s", e)

    # Spam tracking
    now = datetime.utcnow().timestamp()
    lst = spam_tracker.get(message.author.id, [])
    lst = [t for t in lst if now - t < SPAM_WINDOW]
    lst.append(now)
    spam_tracker[message.author.id] = lst
    if len(lst) > SPAM_LIMIT and not is_staff(message.author):
        try:
            await try_timeout_member(message.author, SPAM_TIMEOUT/60 if SPAM_TIMEOUT>60 else 1, "Automated spam timeout")
            await message.channel.send(f"{message.author.mention} is tijdelijk gemute voor spam.")
            logger.info(f"Spam timeout for {message.author}")
            spam_tracker[message.author.id] = []
            return
        except Exception as e:
            logger.exception("Spam timeout failed: %s", e)

    await bot.process_commands(message)

# -----------------------
# TICKET UI (Views / Buttons / Modals)
# -----------------------
class TicketCloseConfirm(View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.author_id = author_id

    @nextcord.ui.button(label="Bevestig sluiten", style=nextcord.ButtonStyle.danger)
    async def confirm(self, button: Button, interaction: Interaction):
        # only staff or author
        if not (is_staff(interaction.user) or interaction.user.id == self.author_id):
            return await interaction.response.send_message("Je mag dit niet doen.", ephemeral=True)
        await interaction.response.send_message("Ticket wordt gesloten... Transcript wordt opgeslagen.", ephemeral=True)
        logger.info(f"{interaction.user} closing ticket {interaction.channel.name}")
        await save_transcript(interaction.channel)
        try:
            await interaction.channel.delete(reason=f"Closed by {interaction.user}")
        except Exception as e:
            logger.exception("Could not delete ticket channel: %s", e)

    @nextcord.ui.button(label="Annuleer", style=nextcord.ButtonStyle.secondary)
    async def cancel(self, button: Button, interaction: Interaction):
        await interaction.response.send_message("Sluiten geannuleerd.", ephemeral=True)

class TicketView(View):
    def __init__(self, author_id: int):
        super().__init__(timeout=None)
        self.author_id = author_id

    @nextcord.ui.button(label="Claim Ticket", style=nextcord.ButtonStyle.success)
    async def claim(self, button: Button, interaction: Interaction):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Je hebt geen permissie om te claimen.", ephemeral=True)
        await interaction.channel.send(f"**{interaction.user}** heeft deze ticket geclaimed. Het is de bedoeling dat {interaction.user.mention} nu het aanspreekpunt is.")
        await interaction.response.send_message("Ticket geclaimed.", ephemeral=True)
        logger.info(f"{interaction.user} claimed ticket in {interaction.channel.name}")

    @nextcord.ui.button(label="Sluit Ticket", style=nextcord.ButtonStyle.danger)
    async def close(self, button: Button, interaction: Interaction):
        view = TicketCloseConfirm(author_id=self.author_id)
        await interaction.response.send_message("Weet je het zeker? Bevestig hieronder:", view=view, ephemeral=True)

class OpenTicketView(View):
    @nextcord.ui.button(label="📩 Open Ticket", style=nextcord.ButtonStyle.primary)
    async def open_ticket(self, button: Button, interaction: Interaction):
        guild = interaction.guild
        member = interaction.user
        # builds overwrites
        overwrites = {
            guild.default_role: nextcord.PermissionOverwrite(view_channel=False),
            member: nextcord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        staff_role = guild.get_role(STAFF_ROLE_ID)
        if staff_role:
            overwrites[staff_role] = nextcord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        category = bot.get_channel(TICKET_CATEGORY)
        name = f"ticket-{member.name}".lower()[:90]
        channel = await guild.create_text_channel(name=name, overwrites=overwrites, category=category)
        intro = ("Hallo {mention}, welkom in uw support ticket. Bedankt dat u contact met ons opneemt. "
                 "In dit kanaal zal ons staff-team u zo snel mogelijk assisteren. Om ons te helpen: beschrijf duidelijk "
                 "het probleem, voeg relevante informatie toe en eventuele screenshots of links. Ons team controleert de ticket "
                 "en reageert zo snel mogelijk. Als u wilt dat specifieke staff reageert, tag die persoon. We doen ons best om u "
                 "vriendelijk en efficiënt te helpen. Bedankt voor uw geduld.").format(mention=member.mention)
        embed = nextcord.Embed(title=f"Ticket voor {member}", description=intro, color=BLUE)
        embed.add_field(name="Gebruiker", value=member.mention, inline=True)
        embed.add_field(name="Status", value="Open", inline=True)
        embed.set_footer(text=FOOTER)
        await channel.send(content=(f"<@&{STAFF_ROLE_ID}>" if STAFF_ROLE_ID else None), embed=embed, view=TicketView(author_id=member.id))
        await interaction.response.send_message(f"Ticket aangemaakt: {channel.mention}", ephemeral=True)
        logger.info(f"Ticket created {channel.name} for {member}")

class TicketPanelView(View):
    @nextcord.ui.button(label="Maak Ticket Panel", style=nextcord.ButtonStyle.primary)
    async def create_panel(self, button: Button, interaction: Interaction):
        embed = nextcord.Embed(title="🎫 Ticket Panel", description="Klik op de knop hieronder om een ticket te openen.\nOnze staff helpt je zo snel mogelijk!", color=BLUE)
        embed.set_footer(text=FOOTER)
        await interaction.channel.send(embed=embed, view=OpenTicketView())
        await interaction.response.send_message("Ticket panel geplaatst!", ephemeral=True)
        logger.info(f"Ticket panel created by {interaction.user} in {interaction.channel.name}")

# ticketpanel slash command
@bot.slash_command(name="ticketpanel", description="Maak een ticket panel.", guild_ids=[GUILD_ID])
async def ticketpanel(interaction: Interaction):
    embed = nextcord.Embed(title="🎫 Ticket Panel Creator", description="Druk op Maak Ticket Panel om het ticket panel te plaatsen. Alleen jij ziet dit.", color=BLUE)
    embed.set_footer(text=FOOTER)
    view = TicketPanelView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# -----------------------
# MODALS for Embed / Review / Suggest
# -----------------------
class EmbedModal(Modal):
    def __init__(self):
        super().__init__("Maak een Embed")
        self.author = TextInput(label="Author naam (opt)", required=False, max_length=100)
        self.title = TextInput(label="Titel", required=True, max_length=256)
        self.description = TextInput(label="Beschrijving", style=nextcord.TextInputStyle.paragraph, required=True, max_length=4000)
        self.image = TextInput(label="Afbeelding URL (opt)", required=False, max_length=1000)
        self.add_item(self.author)
        self.add_item(self.title)
        self.add_item(self.description)
        self.add_item(self.image)

    async def callback(self, interaction: Interaction):
        embed = nextcord.Embed(title=self.title.value, description=self.description.value, color=BLUE)
        if self.author.value:
            embed.set_author(name=self.author.value)
        if self.image.value:
            embed.set_image(url=self.image.value)
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed)

@bot.slash_command(name="embed", description="Maak een custom embed.", guild_ids=[GUILD_ID])
async def embed_cmd(interaction: Interaction):
    await interaction.response.send_modal(EmbedModal())

class ReviewModal(Modal):
    def __init__(self):
        super().__init__("Laat een review achter")
        self.product = TextInput(label="Welk product?", required=True)
        self.stars = TextInput(label="Aantal sterren (1-5)", required=True, max_length=2)
        self.service = TextInput(label="Service sterren (1-5)", required=True, max_length=2)
        self.message = TextInput(label="Review bericht", style=nextcord.TextInputStyle.paragraph, required=False)
        self.add_item(self.product)
        self.add_item(self.stars)
        self.add_item(self.service)
        self.add_item(self.message)

    async def callback(self, interaction: Interaction):
        embed = nextcord.Embed(title="⭐ Nieuwe Review", color=BLUE)
        embed.add_field(name="Product", value=self.product.value, inline=False)
        embed.add_field(name="Product Sterren", value=self.stars.value, inline=True)
        embed.add_field(name="Service Sterren", value=self.service.value, inline=True)
        embed.add_field(name="Reviewer", value=interaction.user.mention, inline=False)
        embed.add_field(name="Opmerking", value=self.message.value or "Geen extra opmerking.", inline=False)
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed)
        logger.info(f"Review by {interaction.user}")

@bot.slash_command(name="review", description="Laat een review achter.", guild_ids=[GUILD_ID])
async def review_cmd(interaction: Interaction):
    await interaction.response.send_modal(ReviewModal())

class SuggestModal(Modal):
    def __init__(self):
        super().__init__("Nieuwe suggestie")
        self.naam = TextInput(label="Naam", required=True)
        self.tijd = TextInput(label="Tijd", required=False)
        self.datum = TextInput(label="Datum", required=False)
        self.suggestie = TextInput(label="Suggestie", style=nextcord.TextInputStyle.paragraph, required=True)
        self.extra = TextInput(label="Extra", style=nextcord.TextInputStyle.paragraph, required=False)
        self.add_item(self.naam)
        self.add_item(self.tijd)
        self.add_item(self.datum)
        self.add_item(self.suggestie)
        self.add_item(self.extra)

    async def callback(self, interaction: Interaction):
        embed = nextcord.Embed(title="💡 Suggestie", color=BLUE)
        embed.add_field(name="Naam", value=self.naam.value, inline=True)
        embed.add_field(name="Tijd", value=self.tijd.value or "Onbekend", inline=True)
        embed.add_field(name="Datum", value=self.datum.value or "Onbekend", inline=True)
        embed.add_field(name="Suggestie", value=self.suggestie.value, inline=False)
        embed.add_field(name="Extra", value=self.extra.value or "Geen extra info", inline=False)
        embed.set_footer(text=FOOTER)
        await interaction.response.send_message(embed=embed)
        logger.info(f"Suggestion by {interaction.user}")

@bot.slash_command(name="suggesties", description="Nieuwe suggestie", guild_ids=[GUILD_ID])
async def suggest_cmd(interaction: Interaction):
    await interaction.response.send_modal(SuggestModal())

# -----------------------
# Moderation commands
# -----------------------
@bot.slash_command(name="purge", description="Verwijder aantal berichten", guild_ids=[GUILD_ID])
async def purge(interaction: Interaction, amount: int = SlashOption(required=True, description="Aantal berichten (max 100)")):
    if not interaction.user.guild_permissions.manage_messages:
        return await interaction.response.send_message("Geen permissie.", ephemeral=True)
    amount = max(1, min(100, amount))
    deleted = await interaction.channel.purge(limit=amount)
    embed = nextcord.Embed(title="Purge", description=f"Verwijderde berichten: {len(deleted)}", color=BLUE)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    logger.info(f"{interaction.user} purged {len(deleted)} messages in {interaction.channel}")

@bot.slash_command(name="kick", description="Kick een gebruiker", guild_ids=[GUILD_ID])
async def kick(interaction: Interaction, member: nextcord.Member = SlashOption(required=True), reason: str = SlashOption(required=False)):
    if not interaction.user.guild_permissions.kick_members:
        return await interaction.response.send_message("Geen permissie.", ephemeral=True)
    await member.kick(reason=reason)
    embed = nextcord.Embed(title="Kick", description=f"{member} is gekickt.\nReden: {reason or 'Geen reden opgegeven'}", color=BLUE)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    logger.info(f"{interaction.user} kicked {member}")

@bot.slash_command(name="ban", description="Ban een gebruiker", guild_ids=[GUILD_ID])
async def ban(interaction: Interaction, member: nextcord.Member = SlashOption(required=True), reason: str = SlashOption(required=False)):
    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("Geen permissie.", ephemeral=True)
    await member.ban(reason=reason)
    embed = nextcord.Embed(title="Ban", description=f"{member} is verbannen.\nReden: {reason or 'Geen reden opgegeven'}", color=BLUE)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    logger.info(f"{interaction.user} banned {member}")

@bot.slash_command(name="timeout", description="Time-out een gebruiker (minuten)", guild_ids=[GUILD_ID])
async def timeout_cmd(interaction: Interaction, member: nextcord.Member = SlashOption(required=True), minutes: int = SlashOption(required=True, description="Duur in minuten")):
    if not interaction.user.guild_permissions.moderate_members:
        return await interaction.response.send_message("Geen permissie.", ephemeral=True)
    await try_timeout_member(member, minutes, f"Timed out by {interaction.user}")
    embed = nextcord.Embed(title="Time-out", description=f"{member} heeft een timeout van {minutes} minuten.", color=BLUE)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    logger.info(f"{interaction.user} timed out {member} for {minutes} minutes")

@bot.slash_command(name="giverol", description="Geef een rol aan iemand", guild_ids=[GUILD_ID])
async def giverol_cmd(interaction: Interaction, member: nextcord.Member = SlashOption(required=True), role: nextcord.Role = SlashOption(required=True)):
    if not interaction.user.guild_permissions.manage_roles:
        return await interaction.response.send_message("Geen permissie.", ephemeral=True)
    await member.add_roles(role)
    embed = nextcord.Embed(title="Rol gegeven", description=f"{member.mention} heeft de rol {role.mention} gekregen.", color=BLUE)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed, ephemeral=True)
    logger.info(f"{interaction.user} gave role {role} to {member}")

# -----------------------
# Extra helpful commands (10+)
# -----------------------
@bot.slash_command(name="ping", description="Check bot latency", guild_ids=[GUILD_ID])
async def ping(interaction: Interaction):
    embed = nextcord.Embed(title="Pong!", description=f"{round(bot.latency*1000)}ms", color=BLUE)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="userinfo", description="Get user info", guild_ids=[GUILD_ID])
async def userinfo(interaction: Interaction, member: nextcord.Member = SlashOption(required=False)):
    member = member or interaction.user
    embed = nextcord.Embed(title=f"Info - {member}", color=BLUE)
    embed.add_field(name="ID", value=str(member.id), inline=True)
    embed.add_field(name="Account aangemaakt", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Joined server", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "Onbekend", inline=True)
    embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="serverinfo", description="Server info", guild_ids=[GUILD_ID])
async def serverinfo(interaction: Interaction):
    g = interaction.guild
    embed = nextcord.Embed(title=f"{g.name} - Info", color=BLUE)
    embed.add_field(name="Server ID", value=str(g.id), inline=True)
    embed.add_field(name="Members", value=str(g.member_count), inline=True)
    embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="roleinfo", description="Info over een rol", guild_ids=[GUILD_ID])
async def roleinfo(interaction: Interaction, role: nextcord.Role = SlashOption(required=True)):
    embed = nextcord.Embed(title=f"Rol info - {role.name}", color=BLUE)
    embed.add_field(name="ID", value=str(role.id), inline=True)
    embed.add_field(name="Members", value=str(len(role.members)), inline=True)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="avatar", description="Bekijk avatar", guild_ids=[GUILD_ID])
async def avatar(interaction: Interaction, member: nextcord.Member = SlashOption(required=False)):
    member = member or interaction.user
    embed = nextcord.Embed(title=f"{member}'s avatar", color=BLUE)
    embed.set_image(url=member.avatar.url if member.avatar else None)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="say", description="Laat de bot iets zeggen (embed)", guild_ids=[GUILD_ID])
async def say_cmd(interaction: Interaction, tekst: str = SlashOption(required=True)):
    embed = nextcord.Embed(description=tekst, color=BLUE)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="lock", description="Lock het huidige kanaal", guild_ids=[GUILD_ID])
async def lock_cmd(interaction: Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message("Geen permissie.", ephemeral=True)
    overwrites = interaction.channel.overwrites
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message("Kanaal gelocked.", ephemeral=True)

@bot.slash_command(name="unlock", description="Unlock het huidige kanaal", guild_ids=[GUILD_ID])
async def unlock_cmd(interaction: Interaction):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message("Geen permissie.", ephemeral=True)
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)
    await interaction.response.send_message("Kanaal unlocked.", ephemeral=True)

@bot.slash_command(name="slowmode", description="Zet slowmode in seconden", guild_ids=[GUILD_ID])
async def slowmode_cmd(interaction: Interaction, seconds: int = SlashOption(required=True)):
    if not interaction.user.guild_permissions.manage_channels:
        return await interaction.response.send_message("Geen permissie.", ephemeral=True)
    await interaction.channel.edit(slowmode_delay=max(0, seconds))
    await interaction.response.send_message(f"Slowmode ingesteld op {seconds} sec.", ephemeral=True)

@bot.slash_command(name="announce", description="Maak een grote announcement embed", guild_ids=[GUILD_ID])
async def announce_cmd(interaction: Interaction, titel: str = SlashOption(required=True), bericht: str = SlashOption(required=True), kanaal: nextcord.TextChannel = SlashOption(required=False)):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("Geen permissie.", ephemeral=True)
    channel = kanaal or interaction.channel
    embed = nextcord.Embed(title=titel, description=bericht, color=BLUE)
    embed.set_footer(text=FOOTER)
    await channel.send(embed=embed)
    await interaction.response.send_message("Announcement gestuurd.", ephemeral=True)

# -----------------------
# Logging helper command (optional)
# -----------------------
@bot.slash_command(name="logtest", description="Stuur een test log naar logs kanaal", guild_ids=[GUILD_ID])
async def logtest(interaction: Interaction):
    logch = bot.get_channel(LOG_CHANNEL_ID)
    if logch:
        await logch.send(f"Log test by {interaction.user}")
    await interaction.response.send_message("Log test gestuurd.", ephemeral=True)

# -----------------------
# Start bot
# -----------------------
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.exception("Bot failed to start: %s", e)
        print("Bot failed to start. Check TOKEN and dependencies.")