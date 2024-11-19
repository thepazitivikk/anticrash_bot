# mmsss

import discord
from discord.ext import commands
import sqlite3
import json
import logging
import config
import message

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = commands.Bot(command_prefix="!", intents=intents)


def load_limits():
    try:
        with open("limits.json", "r") as file:
            return json.load(file)
    except (FileNotFoundError, ValueError):
        default_limits = {
            "role_change": 7,
            "channel_edit": 10,
            "channel_delete": 5,
            "role_create": 5,
            "channel_create": 5,
            "bot_add_limit": 3,
            "webhook_create": 2
        }
        save_limits(default_limits)
        return default_limits


def save_limits(limits):
    with open("limits.json", "w") as file:
        json.dump(limits, file)


limits = load_limits()


def initialize_database():
    conn = sqlite3.connect('actions.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_actions (
            user_id INTEGER PRIMARY KEY,
            role_changes INTEGER DEFAULT 0,
            channel_edits INTEGER DEFAULT 0,
            channel_deletions INTEGER DEFAULT 0,
            role_creations INTEGER DEFAULT 0,
            channel_creations INTEGER DEFAULT 0,
            bot_adds INTEGER DEFAULT 0,
            webhook_creates INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


initialize_database()


async def check_user_limit(guild, user_id, action_type):
    if user_id in config.WHITELIST:
        logging.info(f"User {user_id} is whitelisted; skipping limit check.")
        return False

    member = guild.get_member(user_id)
    if member and any(role.id in config.ROLE_WHITELIST for role in member.roles):
        logging.info(f"User {user_id} has a whitelisted role; skipping limit check.")
        return False

    conn = sqlite3.connect('actions.db')
    c = conn.cursor()
    c.execute("SELECT * FROM user_actions WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if row:
        role_changes, channel_edits, channel_deletions, role_creations, channel_creations, bot_adds, webhook_creates = row[
                                                                                                                       1:]
    else:
        c.execute("INSERT INTO user_actions (user_id) VALUES (?)", (user_id,))
        conn.commit()
        role_changes, channel_edits, channel_deletions, role_creations, channel_creations, bot_adds, webhook_creates = 0, 0, 0, 0, 0, 0, 0

    action_counts = {
        "role_change": role_changes,
        "channel_edit": channel_edits,
        "channel_delete": channel_deletions,
        "role_create": role_creations,
        "channel_create": channel_creations,
        "bot_add": bot_adds,
        "webhook_create": webhook_creates,
    }

    if action_counts[action_type] >= limits[action_type]:
        if member and guild.me.guild_permissions.kick_members:
            reason = message.KICK_MESSAGES.get(f"{action_type}_limit_exceeded", "Exceeded action limit.")
            await guild.kick(member, reason=reason)
            logging.info(f"User {user_id} kicked for exceeding {action_type} limit.")
            conn.close()
            return True
    else:
        action_counts[action_type] += 1
        c.execute(
            '''UPDATE user_actions SET role_changes = ?, channel_edits = ?, channel_deletions = ?, 
               role_creations = ?, channel_creations = ?, bot_adds = ?, webhook_creates = ? 
               WHERE user_id = ?''',
            (action_counts["role_change"], action_counts["channel_edit"], action_counts["channel_delete"],
             action_counts["role_create"], action_counts["channel_create"], action_counts["bot_add"],
             action_counts["webhook_create"], user_id)
        )
        conn.commit()

    conn.close()
    return False


@bot.event
async def on_guild_channel_create(channel):
    guild = channel.guild
    async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
        user_id = entry.user.id
        if await check_user_limit(guild, user_id, "channel_create"):
            return


@bot.event
async def on_guild_channel_delete(channel):
    guild = channel.guild
    async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
        user_id = entry.user.id
        if await check_user_limit(guild, user_id, "channel_delete"):
            return


@bot.event
async def on_webhook_create(webhook):
    guild = webhook.guild
    logging.info(f"Webhook {webhook.id} created in guild {guild.name}.")

    async for entry in guild.audit_logs(action=discord.AuditLogAction.webhook_create, limit=1):
        user_id = entry.user.id
        logging.info(f"User {entry.user} (ID: {user_id}) created webhook in guild {guild.name}.")

        if await check_user_limit(guild, user_id, "webhook_create"):
            member = guild.get_member(user_id)
            if member:
                await guild.kick(member, reason="Exceeded webhook creation limit.")
                logging.info(f"User {user_id} kicked for exceeding webhook creation limit.")

            await webhook.delete(reason="Exceeded webhook creation limit.")
            logging.info(f"Webhook {webhook.id} deleted.")
            return


@bot.event
async def on_guild_role_update(before, after):
    guild = before.guild
    user_id = after.created_by.id
    if await check_user_limit(guild, user_id, "role_change"):
        return


@bot.event
async def on_guild_role_create(role):
    guild = role.guild
    user_id = role.created_by.id
    if await check_user_limit(guild, user_id, "role_create"):
        return


@bot.event
async def on_member_join(member):
    if member.bot:
        user_id = member.id
        guild = member.guild
        if await check_user_limit(guild, user_id, "bot_add_limit"):
            return


@bot.event
async def on_guild_channel_update(before, after):
    guild = before.guild
    user_id = after.created_by.id
    if await check_user_limit(guild, user_id, "channel_edit"):
        return


@bot.command(name="catalog")
async def catalog(ctx):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    limits_info = "\n".join([f"**{action.capitalize()}**: {limit}" for action, limit in limits.items()])
    embed = discord.Embed(title="Action Limits", description="Current limits for actions: ", color=discord.Color.blue())
    embed.add_field(name="Limits", value=limits_info, inline=False)
    await ctx.send(embed=embed)


@bot.command(name="setlimit")
async def setlimit(ctx, action: str, new_limit: int):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    if action not in limits:
        await ctx.send(
            "Invalid action. Available actions: role_change, channel_edit, channel_delete, role_create, channel_create, bot_add_limit, webhook_create.")
        return

    limits[action] = new_limit
    save_limits(limits)
    await ctx.send(f"Limit for `{action}` has been updated to **{new_limit}**.")


@bot.command(name="whitelist")
async def whitelist(ctx):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    whitelist_info = "\n".join([f"<@{user_id}>" for user_id in config.WHITELIST])
    embed = discord.Embed(title="User Whitelist", description="These users are exempt from limits:",
                          color=discord.Color.green())
    embed.add_field(name="User Whitelist", value=whitelist_info if whitelist_info else "No whitelisted users.",
                    inline=False)
    await ctx.send(embed=embed)


@bot.command(name="rolelist")
async def rolelist(ctx):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    role_whitelist_info = "\n".join([f"<@&{role_id}>" for role_id in config.ROLE_WHITELIST])
    embed = discord.Embed(title="Role Whitelist", description="These roles are exempt from limits:",
                          color=discord.Color.green())
    embed.add_field(name="Role Whitelist",
                    value=role_whitelist_info if role_whitelist_info else "No whitelisted roles.", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="add_whitelist")
async def add_whitelist(ctx, user: discord.User):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    if user.id in config.WHITELIST.append(user.id):
        await ctx.send(f"User {user} has been added to the whitelist.")
        with open("config.json", "w") as file:
            json.dump({"WHITELIST": config.WHITELIST, "ROLE_WHITELIST": config.ROLE_WHITELIST}, file)

@bot.command(name="remove_whitelist")
async def remove_whitelist(ctx, user: discord.User):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    if user.id not in config.WHITELIST:
        await ctx.send(f"User {user} is not in the whitelist.")
    else:
        config.WHITELIST.remove(user.id)
        await ctx.send(f"User {user} has been removed from the whitelist.")
        with open("config.json", "w") as file:
            json.dump({"WHITELIST": config.WHITELIST, "ROLE_WHITELIST": config.ROLE_WHITELIST}, file)

@bot.command(name="add_role_whitelist")
async def add_role_whitelist(ctx, role: discord.Role):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    if role.id in config.ROLE_WHITELIST:
        await ctx.send(f"Role {role.name} is already in the role whitelist.")
    else:
        config.ROLE_WHITELIST.append(role.id)
        await ctx.send(f"Role {role.name} has been added to the role whitelist.")
        with open("config.json", "w") as file:
            json.dump({"WHITELIST": config.WHITELIST, "ROLE_WHITELIST": config.ROLE_WHITELIST}, file)

@bot.command(name="remove_role_whitelist")
async def remove_role_whitelist(ctx, role: discord.Role):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    if role.id not in config.ROLE_WHITELIST:
        await ctx.send(f"Role {role.name} is not in the role whitelist.")
    else:
        config.ROLE_WHITELIST.remove(role.id)
        await ctx.send(f"Role {role.name} has been removed from the role whitelist.")
        with open("config.json", "w") as file:
            json.dump({"WHITELIST": config.WHITELIST, "ROLE_WHITELIST": config.ROLE_WHITELIST}, file)

@bot.command(name="clear_limits")
async def clear_limits(ctx):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    conn = sqlite3.connect('actions.db')
    c = conn.cursor()
    c.execute("UPDATE user_actions SET role_changes = 0, channel_edits = 0, channel_deletions = 0, "
              "role_creations = 0, channel_creations = 0, bot_adds = 0, webhook_creates = 0")
    conn.commit()
    conn.close()

    await ctx.send("Action limits for all users have been reset.")

@bot.command(name="reset_user_limits")
async def reset_user_limits(ctx, user: discord.User):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    conn = sqlite3.connect('actions.db')
    c = conn.cursor()
    c.execute("UPDATE user_actions SET role_changes = 0, channel_edits = 0, channel_deletions = 0, "
              "role_creations = 0, channel_creations = 0, bot_adds = 0, webhook_creates = 0 "
              "WHERE user_id = ?", (user.id,))
    conn.commit()
    conn.close()

    await ctx.send(f"Action limits for user {user} have been reset.")

@bot.command(name="view_user_limits")
async def view_user_limits(ctx, user: discord.User):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    conn = sqlite3.connect('actions.db')
    c = conn.cursor()
    c.execute("SELECT * FROM user_actions WHERE user_id = ?", (user.id,))
    row = c.fetchone()
    conn.close()

    if row:
        action_counts = {
            "role_changes": row[1],
            "channel_edits": row[2],
            "channel_deletions": row[3],
            "role_creations": row[4],
            "channel_creations": row[5],
            "bot_adds": row[6],
            "webhook_creates": row[7],
        }

        embed = discord.Embed(title=f"Action Counts for {user}", color=discord.Color.blue())
        for action, count in action_counts.items():
            embed.add_field(name=action.replace('_', ' ').capitalize(), value=str(count), inline=False)

        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No action data found for user {user}.")

@bot.command(name="set_limits_reset")
async def set_limits_reset(ctx):
    if ctx.author.id not in config.ALLOWED_IDS:
        await ctx.send("You do not have permission to use this command.")
        return

    default_limits = {
        "role_change": 7,
        "channel_edit": 10,
        "channel_delete": 5,
        "role_create": 5,
        "channel_create": 5,
        "bot_add_limit": 3,
        "webhook_create": 2
    }

    save_limits(default_limits)
    global limits
    limits = default_limits

    await ctx.send("Limits have been reset to default values.")

bot.run(config.TOKEN)


