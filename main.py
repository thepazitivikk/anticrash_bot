import discord
from discord.ext import commands, tasks
import sqlite3
import json
import logging
import config
import message
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = commands.Bot(command_prefix="!", intents=intents)

AUTHORIZED_USER_IDS = {773113930540908554, 532909407345049601}

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
            "channel_create": 5,
            "bot_add_limit": 3,
            "webhook_create": 3
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
        file.write(f"ROLE_WHITELIST = {config.ROLE_WHITELIST}\n")

async def check_user_limit(guild, user_id, action_type):
    if user_id in config.WHITELIST:
        logging.info(f"User {user_id} is whitelisted; skipping limit check.")
        return

    conn = sqlite3.connect('actions.db')
    c = conn.cursor()

    c.execute("SELECT * FROM user_actions WHERE user_id = ?", (user_id,))
    row = c.fetchone()

    if row:
        role_changes, channel_edits, channel_deletions, role_creations, channel_creations, bot_adds, webhook_creates = row[1:]
    else:
        c.execute("INSERT INTO user_actions (user_id) VALUES (?)", (user_id,))
        conn.commit()
        role_changes, channel_edits, channel_deletions, role_creations, channel_creations, bot_adds, webhook_creates = 0, 0, 0, 0, 0, 0, 0

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
    elif action_type == "bot_add":
        bot_adds += 1
        if bot_adds >= limits["bot_add_limit"] and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["bot_add_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding bot add limit")
    elif action_type == "webhook_create":
        webhook_creates += 1
        if webhook_creates >= limits["webhook_create"] and guild.me.guild_permissions.kick_members:
            await guild.kick(member, reason=message.KICK_MESSAGES["webhook_limit_exceeded"])
            logging.info(f"User {user_id} kicked for exceeding webhook creation limit")

    c.execute(
        '''UPDATE user_actions SET role_changes = ?, channel_edits = ?, channel_deletions = ?, role_creations = ?, channel_creations = ?, bot_adds = ?, webhook_creates = ? WHERE user_id = ?''',
        (role_changes, channel_edits, channel_deletions, role_creations, channel_creations, bot_adds, webhook_creates, user_id))
    conn.commit()
    conn.close()

def is_authorized_user():
    async def predicate(ctx):
        return ctx.author.id in AUTHORIZED_USER_IDS
    return commands.check(predicate)

@bot.command()
@is_authorized_user()
async def catalog(ctx):
    actions = "\n".join([f"{action}: {limit}" for action, limit in limits.items()])
    await ctx.send(f"`>` Список действий и текущие лимиты:\n```{actions}```\n\n"
                   f"Для изменения лимита введите: `!setlimit <действие> <новый_лимит>`")

@bot.command()
@is_authorized_user()
async def setlimit(ctx, action: str, new_limit: int):
    if action in limits:
        limits[action] = new_limit
        save_limits(limits)
        await ctx.send(f"`>` Лимит для действия '{action}' успешно изменен на {new_limit}.")
        logging.info(f"`>` Лимит для {action} установлен на {new_limit} администратором {ctx.author.id}")
    else:
        await ctx.send("`>` Указанное действие не существует. Проверьте команду `!catalog` для доступных действий.")

@bot.command()
@is_authorized_user()
async def whitelist(ctx, action: str = None, member: discord.Member = None):
    if action is None or member is None:
        whitelist_users = ", ".join([f"<@{user_id}>" for user_id in config.WHITELIST])
        await ctx.send(f"**Команды:**\n`!whitelist <add/remove> <пользователь>`\n\n**Текущий белый список пользователей:**\n{whitelist_users if whitelist_users else 'Список пуст'}")
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
        await ctx.send("Неверное действие. Используйте `add` для добавления или `remove` для удаления пользователя из белого списка.")

@bot.command()
@is_authorized_user()
async def rolelist(ctx, action: str = None, role: discord.Role = None):
    if action is None or role is None:
        whitelist_roles = ", ".join([f"<@&{role_id}>" for role_id in config.ROLE_WHITELIST])
        await ctx.send(f"**Команды:**\n`!rolelist <add/remove> <роль>`\n\n**Текущий белый список ролей:**\n{whitelist_roles if whitelist_roles else 'Список пуст'}")
        return

    role_id = role.id
    if action == "add":
        if role_id not in config.ROLE_WHITELIST:
            config.ROLE_WHITELIST.append(role_id)
            save_whitelist()
            await ctx.send(f"Роль {role.mention} добавлена в белый список.")
            logging.info(f"Role {role_id} added to whitelist by admin {ctx.author.id}")
        else:
            await ctx.send("Роль уже в белом списке.")
    elif action == "remove":
        if role_id in config.ROLE_WHITELIST:
            config.ROLE_WHITELIST.remove(role_id)
            save_whitelist()
            await ctx.send(f"Роль {role.mention} удалена из белого списка.")
            logging.info(f"Role {role_id} removed from whitelist by admin {ctx.author.id}")
        else:
            await ctx.send("Роли нет в белом списке.")
    else:
        await ctx.send("Неверное действие. Используйте `add` для добавления или `remove` для удаления роли из белого списка.")

@bot.event
async def on_member_join(member):
    if member.bot:
        added_by = None
        async for entry in member.guild.audit_logs(action=discord.AuditLogAction.bot_add):
            if entry.target.id == member.id:
                added_by = entry.user
                break
        if added_by and added_by.id not in config.WHITELIST:
            await member.guild.kick(added_by, reason=message.KICK_MESSAGES["bot_add_limit_exceeded"])
            await member.guild.kick(member, reason=message.KICK_MESSAGES["bot_add_limit_exceeded"])
            logging.info(f"User {added_by.id} and bot {member.id} were kicked for bot addition without whitelist access")

@bot.event
async def on_webhooks_update(channel):
    guild = channel.guild
    async for entry in guild.audit_logs(action=discord.AuditLogAction.webhook_create):
        user = entry.user
        if user.id not in config.WHITELIST:
            await check_user_limit(guild, user.id, "webhook_create")
            webhook = await channel.webhooks()
            if webhook:
                await webhook[0].delete()
                logging.info(f"Webhook created by {user.id} deleted; user kicked if limit exceeded")

@bot.event
async def on_ready():
    logging.info(f"Bot is ready and connected as {bot.user}")

bot.run(config.TOKEN)
