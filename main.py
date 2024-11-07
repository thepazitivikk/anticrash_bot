import discord
from discord import guild
from discord.ext import commands
import sqlite3
import logging
import config
import message

intents = discord.Intents.default()
intents.members = True
intents.guilds = True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = commands.Bot(command_prefix="!", intents=intents)


async def check_user_limit(guild, user_id, action_type):
    conn = sqlite3.connect('actions.db')
    c = conn.cursor()

    c.execute("SELECT * FROM user_actions WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if row:
        role_changes, channel_edits, channel_deletions, role_creations, channel_creations = row[1:]
    else:
        c.execute("INSERT INTO user_actions (user_id) VALUES (?)", (user_id,))
        conn.commit()
        role_changes, channel_edits, channel_deletions, role_creations, channel_creations = 0, 0, 0, 0, 0

    member = guild.get_member(user_id)

    if action_type == "role_change":
        role_changes += 1
        if role_changes >= 7 and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["role_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding role change limit")
    elif action_type == "channel_edit":
        channel_edits += 1
        if channel_edits >= 10 and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["channel_edit_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding channel edit limit")
    elif action_type == "channel_delete":
        channel_deletions += 1
        if channel_deletions >= 5 and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["channel_delete_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding channel deletion limit")
    elif action_type == "role_create":
        role_creations += 1
        if role_creations >= 5 and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["role_create_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding role creation limit")
    elif action_type == "channel_create":
        channel_creations += 1
        if channel_creations >= 5 and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["channel_create_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding channel creation limit")

    c.execute(
        '''UPDATE user_actions SET role_changes = ?, channel_edits = ?, channel_deletions = ?, role_creations = ?, channel_creations = ? WHERE user_id = ?''',
        (role_changes, channel_edits, channel_deletions, role_creations, channel_creations, user_id))
    conn.commit()
    conn.close()


@bot.event
async def on_guild_channel_create(channel):
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
        creator = entry.user
        logging.info(f"Channel {channel.id} created by user {creator.id}")
        await check_user_limit(channel.guild, creator.id, "channel_create")


@bot.event
async def on_guild_channel_delete(channel):
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        deleter = entry.user
        logging.info(f"Channel {channel.id} deleted by user {deleter.id}")
        await check_user_limit(channel.guild, deleter.id, "channel_delete")


@bot.event
async def on_guild_role_create(role):
    async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
        creator = entry.user
        logging.info(f"Role {role.id} created by user {creator.id}")
        await check_user_limit(role.guild, creator.id, "role_create")


@bot.event
async def on_member_join(member):
    if member.bot:
        inviter = member.guild.get_member(member.id)
        if inviter and guild.me.guild_permissions.kick_members:
            await member.guild.kick(member)
            await inviter.kick()
            await inviter.send(message.KICK_MESSAGES["bot_and_user_kicked"])


@bot.event
async def on_webhooks_update(channel):
    webhooks = await channel.webhooks()
    for webhook in webhooks:
        await webhook.delete()
    await channel.guild.owner.send(message.KICK_MESSAGES["webhook_deleted"])


bot.run(config.TOKEN)
