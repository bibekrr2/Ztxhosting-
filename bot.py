import discord
from discord.ext import commands
import re
import logging

CONFIG = {
    "TOKEN": "MTM4MzUxNzA4ODUzMDAzODkxNQ.G7G3pD.HoTXBBhIBG4UIelCrPp7Zd96Nked6KZVeHmuiY",  # Replace with your actual bot token
    "GUILD_ID": 1380792281048678441,
    "TICKET_CATEGORY_ID": 1393886882668220486,
    "TICKET_PANEL_CHANNEL_ID": 1390962381546323998,
    "SUPPORT_ROLE_IDS": [1390962257491529738],
    "LOG_CHANNEL_ID": None,
    "DELETE_AFTER_CLOSE": True,
    "TICKET_PREFIX": "ticket",
    "CLOSED_PREFIX": "closed"
}

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("ticket_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

def sanitize_name(name: str) -> str:
    return re.sub(r'[^a-z0-9_-]', '', name.lower().replace(" ", "-"))

async def has_support_role(member: discord.Member) -> bool:
    return any(role.id in CONFIG["SUPPORT_ROLE_IDS"] for role in member.roles)

async def send_log(message: str, guild: discord.Guild):
    channel = guild.get_channel(CONFIG["LOG_CHANNEL_ID"])
    if channel:
        try:
            await channel.send(message)
        except Exception as e:
            logger.error(f"Failed to send log: {e}")

class TicketModal(discord.ui.Modal):
    def __init__(self, reason: str):
        super().__init__(title=f"{reason} Ticket")
        self.reason = reason

        self.add_item(discord.ui.TextInput(
            label="Your Discord Name",
            placeholder="How we should address you...",
            required=True
        ))

        if reason == "Private Support":
            self.add_item(discord.ui.TextInput(
                label="Describe your issue in detail",
                style=discord.TextStyle.paragraph,
                placeholder="Include all relevant information...",
                required=True
            ))
        elif reason == "Purchase Product":
            self.add_item(discord.ui.TextInput(
                label="Product you want to purchase",
                placeholder="Minecraft, Rust, etc.",
                required=True
            ))
            self.add_item(discord.ui.TextInput(
                label="Preferred Payment Method",
                placeholder="UPI, GPay, etc.",
                required=True
            ))

    async def on_submit(self, interaction: discord.Interaction):
        try:
            clean_name = sanitize_name(interaction.user.display_name)
            ticket_name = f"{CONFIG['TICKET_PREFIX']}-{clean_name}"

            existing_channel = discord.utils.get(
                interaction.guild.text_channels, name=ticket_name
            )
            if existing_channel:
                await interaction.response.send_message(
                    f"⚠️ You already have an open ticket: {existing_channel.mention}",
                    ephemeral=True
                )
                return

            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                ),
            }

            for role_id in CONFIG["SUPPORT_ROLE_IDS"]:
                role = interaction.guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, manage_messages=True
                    )

            category = interaction.guild.get_channel(CONFIG["TICKET_CATEGORY_ID"])
            if category is None:
                return await interaction.response.send_message("❌ Ticket category not found.", ephemeral=True)

            channel = await interaction.guild.create_text_channel(
                name=ticket_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket created by {interaction.user}"
            )

            embed = discord.Embed(
                title=f"🎫 {self.reason} Ticket",
                color=discord.Color.blue(),
                timestamp=interaction.created_at
            )
            embed.add_field(name="User", value=interaction.user.mention, inline=False)

            for item in self.children:
                embed.add_field(name=item.label, value=item.value or "Not provided", inline=False)

            await channel.send(
                content=f"{interaction.user.mention} " +
                " ".join(f"<@&{rid}>" for rid in CONFIG["SUPPORT_ROLE_IDS"]),
                embed=embed
            )
            await channel.send(view=TicketManagementView())

            await interaction.response.send_message(
                f"✅ Ticket created: {channel.mention}", ephemeral=True
            )

            await send_log(
                f"📥 Ticket created by {interaction.user} ({interaction.user.id}): {channel.mention}",
                interaction.guild
            )

        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            await interaction.response.send_message(
                "⚠️ An error occurred while creating your ticket.",
                ephemeral=True
            )

class TicketReasonSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Private Support",
                description="Get help with service-related issues",
                emoji="<:ztx_support:1382407838504058950>"
            ),
            discord.SelectOption(
                label="Purchase Product",
                description="Order products from our store",
                emoji="<:money:1393953880110403634>"
            )
        ]
        super().__init__(
            placeholder="Select a ticket category...",
            options=options,
            custom_id="ticket_reason"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(TicketModal(self.values[0]))
        except Exception as e:
            logger.error(f"Error opening ticket modal: {e}")
            await interaction.response.send_message("⚠️ Could not open the ticket form.", ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketReasonSelect())

class TicketManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await has_support_role(interaction.user):
            return await interaction.response.send_message(
                "❌ You don't have permission to close tickets.", ephemeral=True
            )

        channel = interaction.channel
        try:
            new_name = f"{CONFIG['CLOSED_PREFIX']}-{channel.name.split('-', 1)[1]}"
            overwrites = channel.overwrites
            for target in overwrites:
                if isinstance(target, discord.Member) and target != interaction.guild.me:
                    overwrites[target].send_messages = False

            await channel.edit(name=new_name, overwrites=overwrites)

            await channel.send(embed=discord.Embed(
                description=f"🔒 Ticket closed by {interaction.user.mention}",
                color=discord.Color.red()
            ))

            if CONFIG["DELETE_AFTER_CLOSE"]:
                await channel.delete()
            else:
                await interaction.response.send_message("✅ Ticket closed.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            await interaction.response.send_message("⚠️ Failed to close the ticket.", ephemeral=True)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="189 tickets"
    ))

    bot.add_view(TicketView())
    bot.add_view(TicketManagementView())

    try:
        guild = bot.get_guild(CONFIG["GUILD_ID"])
        channel = guild.get_channel(CONFIG["TICKET_PANEL_CHANNEL_ID"])

        if channel:
            embed = discord.Embed(
                title="ZTX Hosting",
                description=(
                    "**__Open a Ticket by Selecting the correct category below__**\n\n"
                    "- Do not open joke tickets\n"
                    "- Do not waste our support members' time\n\n"
                    "**Explain your issue with as much information as possible!**"
                ),
                color=0x3498db
            )
            embed.set_image(url="https://cdn.discordapp.com/attachments/1391812903748894862/1395401983036227616/Image.png?ex=687a50de&is=6878ff5e&hm=c85fd99eec4d9f3a9603275a1c17da9e64103f6f4dfb6ffdd701ee5ad190a5de&")

            await channel.purge(limit=5)
            await channel.send(embed=embed, view=TicketView())
        else:
            logger.warning("Ticket panel channel not found.")
    except Exception as e:
        logger.error(f"Failed to update ticket panel: {e}")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    await ctx.message.delete()
    await on_ready()

bot.run(CONFIG["TOKEN"])