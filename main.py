import discord
from discord import guild
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
            data = file.read()
            if not data:
                raise ValueError("Файл пуст")
            return json.loads(data)
    except (FileNotFoundError, ValueError):
        default_limits = {
            "role_change": 7,
            "channel_edit": 10,
            "channel_delete": 5,
            "role_create": 5,
            "channel_create": 5
        }
        save_limits(default_limits)
        return default_limits

def save_limits(limits):
    with open("limits.json", "w") as file:
        json.dump(limits, file)

limits = load_limits()

def save_whitelist():
    with open("config.py", "w") as file:
        file.write(f"TOKEN = '{config.TOKEN}'\n")
        file.write(f"WHITELIST = {config.WHITELIST}\n")

async def check_user_limit(guild, user_id, action_type):
    if user_id in config.WHITELIST:
        logging.info(f"User {user_id} is whitelisted; skipping limit check.")
        return

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
        if role_changes >= limits["role_change"] and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["role_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding role change limit")
    elif action_type == "channel_edit":
        channel_edits += 1
        if channel_edits >= limits["channel_edit"] and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["channel_edit_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding channel edit limit")
    elif action_type == "channel_delete":
        channel_deletions += 1
        if channel_deletions >= limits["channel_delete"] and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["channel_delete_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding channel deletion limit")
    elif action_type == "role_create":
        role_creations += 1
        if role_creations >= limits["role_create"] and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["role_create_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding role creation limit")
    elif action_type == "channel_create":
        channel_creations += 1
        if channel_creations >= limits["channel_create"] and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["channel_create_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding channel creation limit")

    c.execute(
        '''UPDATE user_actions SET role_changes = ?, channel_edits = ?, channel_deletions = ?, role_creations = ?, channel_creations = ? WHERE user_id = ?''',
        (role_changes, channel_edits, channel_deletions, role_creations, channel_creations, user_id))
    conn.commit()
    conn.close()

@bot.command()
@commands.has_permissions(administrator=True)
async def catalog(ctx):
    actions = "\n".join([f"{action}: {limit}" for action, limit in limits.items()])
    await ctx.send(f"`>` Список действий и текущие лимиты:\n```{actions}```\n\n"
                   f"Для изменения лимита введите: `!setlimit <действие> <новый_лимит>`")

@bot.command()
@commands.has_permissions(administrator=True)
async def setlimit(ctx, action: str, new_limit: int):
    if action in limits:
        limits[action] = new_limit
        save_limits(limits)
        await ctx.send(f"`>` Лимит для действия '{action}' успешно изменен на {new_limit}.")
        logging.info(f"`>` Лимит для {action} установлен на {new_limit} администратором {ctx.author.id}")
    else:
        await ctx.send("`>` Указанное действие не существует. Проверьте команду `!catalog` для доступных действий.")

@bot.command()
@commands.has_permissions(administrator=True)
async def whitelist(ctx, action: str = None, member: discord.Member = None):
    if action is None or member is None:
        await ctx.send(
            "Используйте команду так:\n"
            "`!whitelist <add/remove> <@пользователь>`\n\n"
            "**Примеры использования:**\n"
            "`!whitelist add @Пользователь` — добавить пользователя в белый список.\n"
            "`!whitelist remove @Пользователь` — удалить пользователя из белого списка."
        )
        return

    user_id = member.id
    if action == "add":
        if user_id not in config.WHITELIST:
            config.WHITELIST.append(user_id)
            save_whitelist()
            await ctx.send(f"Пользователь {member.mention} добавлен в белый список.")
            logging.info(f"User {user_id} added to whitelist by admin {ctx.author.id}")
        else:
            await ctx.send("Пользователь уже в белом списке.")
    elif action == "remove":
        if user_id in config.WHITELIST:
            config.WHITELIST.remove(user_id)
            save_whitelist()
            await ctx.send(f"Пользователь {member.mention} удален из белого списка.")
            logging.info(f"User {user_id} removed from whitelist by admin {ctx.author.id}")
        else:
            await ctx.send("Пользователя нет в белом списке.")
    else:
        await ctx.send(
            "Неверное действие. Используйте `add` для добавления или `remove` для удаления пользователя из белого списка."
        )


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
