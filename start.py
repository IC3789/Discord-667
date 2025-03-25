import os
import discord
import datetime
import asyncio
import threading
from flask import Flask
from discord.ui import Button, View
from discord.ext import commands
from dotenv import load_dotenv

app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!'

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# Charger les variables d'environnement
load_dotenv('token.env')
token = os.getenv('DISCORD_TOKEN')

# Configuration du bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Configuration
spam_cooldown = commands.CooldownMapping.from_cooldown(
    3, 10, commands.BucketType.user)
user_warnings = {}
user_spam_count = {}
whitelist = set()
antiraid_enabled = False
log_channel = None
captcha_codes = {}
ticket_category_id = 1332456333391433739
staff_role_id = 1332456095393906752
captcha_channel = None
captcha_timeouts = {}


def generate_captcha():
    """Génère un code captcha aléatoire"""
    import random
    import string
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


class TicketView(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fermer le ticket",
                       style=discord.ButtonStyle.danger,
                       emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        if interaction.channel.name.startswith("ticket-"):
            embed = discord.Embed(
                title="Confirmation de fermeture",
                description="Êtes-vous sûr de vouloir fermer ce ticket ?",
                color=discord.Color.red())
            await interaction.response.send_message(embed=embed,
                                                    ephemeral=True,
                                                    delete_after=60)

            try:
                await interaction.channel.send(
                    "🔒 Ce ticket sera fermé dans 5 secondes...")
                await asyncio.sleep(5)
                await interaction.channel.delete()
                if log_channel:
                    await log_channel.send(
                        f"🎫 Ticket fermé par {interaction.user.mention}")
            except:
                await interaction.followup.send(
                    "Une erreur est survenue lors de la fermeture du ticket.",
                    ephemeral=True)


@bot.tree.command(name="ticket", description="Ouvrir un nouveau ticket")
async def ticket(interaction: discord.Interaction, sujet: str):
    # Vérifier le nombre de tickets existants
    user_tickets = [
        channel for channel in interaction.guild.text_channels
        if channel.name.startswith(f"ticket-{interaction.user.name.lower()}")
    ]
    if len(user_tickets) >= 2:
        await interaction.response.send_message(
            "Vous avez déjà atteint la limite de 2 tickets.", ephemeral=True)
        return

    support_category = interaction.guild.get_channel(ticket_category_id)
    if not support_category:
        await interaction.response.send_message(
            "La catégorie de support n'existe pas.", ephemeral=True)
        return

    staff_role = interaction.guild.get_role(staff_role_id)
    overwrites = {
        interaction.guild.default_role:
        discord.PermissionOverwrite(read_messages=False),
        interaction.user:
        discord.PermissionOverwrite(read_messages=True, send_messages=True),
        staff_role:
        discord.PermissionOverwrite(read_messages=True, send_messages=True)
        if staff_role else None
    }

    ticket_channel = await interaction.guild.create_text_channel(
        name=f"ticket-{interaction.user.name.lower()}",
        category=support_category,
        overwrites=overwrites,
        topic=f"Ticket de {interaction.user.name} - {sujet}")

    embed = discord.Embed(
        title="🎫 Nouveau Ticket",
        description=
        f"Bienvenue {interaction.user.mention} !\n\nUn membre du staff vous assistera dès que possible.\nSujet: {sujet}",
        color=discord.Color.blue())

    view = TicketView()
    await ticket_channel.send(embed=embed, view=view)
    await interaction.response.send_message(
        f"Votre ticket a été créé : {ticket_channel.mention}", ephemeral=True)

    if log_channel:
        await log_channel.send(
            f"🎫 Nouveau ticket créé par {interaction.user.mention} - Sujet: {sujet}"
        )


@bot.tree.command(name="panel_ticket",
                  description="Afficher le panel de ticket")
@commands.has_permissions(administrator=True)
async def panel_ticket(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📮 Centre d'Assistance",
        description="Sélectionnez le type de ticket que vous souhaitez créer :",
        color=discord.Color.blue())
    embed.set_footer(text="L'équipe vous répondra dans les plus brefs délais.")

    class TicketView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Question générale", style=discord.ButtonStyle.primary, emoji="❓")
        async def question_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            await ticket(button_interaction, "Question générale")

        @discord.ui.button(label="Signalement", style=discord.ButtonStyle.danger, emoji="🚨")
        async def report_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            await ticket(button_interaction, "Signalement")

        @discord.ui.button(label="Partenariat", style=discord.ButtonStyle.success, emoji="🤝")
        async def partner_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            await ticket(button_interaction, "Partenariat")

        @discord.ui.button(label="Autre", style=discord.ButtonStyle.secondary, emoji="📝")
        async def other_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
            await ticket(button_interaction, "Autre demande")

    await interaction.response.send_message(embed=embed, view=TicketView())


@bot.event
async def on_ready():
    print(f'Bot connecté en tant que {bot.user}')
    await bot.tree.sync()


    async def delete_after_timeout(msg, member_id, timeout):
        await asyncio.sleep(timeout)
        if member_id in captcha_codes:
            try:
                # Supprimer l'embed de vérification
                await msg.delete()

                # Trouver le membre
                member = msg.guild.get_member(member_id)
                if member:
                    # Enlever le rôle Non vérifié et kick si non vérifié
                    unverified_role = discord.utils.get(member.guild.roles, name="Non vérifié")
                    if unverified_role:
                        await member.remove_roles(unverified_role)

                    # Log de l'expiration du captcha
                    if log_channel:
                        await log_channel.send(f"⏰ Délai de vérification expiré pour {member.mention}")

                    # Kick si le membre n'est pas vérifié
                    await member.kick(reason="Vérification captcha non complétée")

                # Nettoyer les données
                del captcha_codes[member_id]
                del captcha_timeouts[member_id]

            except discord.HTTPException as e:
                if log_channel:
                    await log_channel.send(f"❌ Erreur lors de la gestion du captcha: {e}")

    @bot.event
    async def on_member_join(member):
        if not captcha_channel:
            return

        try:
            # Création du rôle Non vérifié
            unverified_role = discord.utils.get(member.guild.roles, name="Non vérifié")
            if not unverified_role:
                unverified_role = await member.guild.create_role(name="Non vérifié")

            # Ajout du rôle Non vérifié
            await member.add_roles(unverified_role)

            # Génération du code captcha
            code = generate_captcha()
            captcha_codes[member.id] = code

            # Création de l'embed de vérification
            embed = discord.Embed(title="Vérification requise", color=discord.Color.blue())
            embed.description = f"Bienvenue {member.mention}!\nPour accéder au serveur, envoyez le code ci-dessous dans ce salon dans les 2 minutes:\n```{code}```"

            # Envoi de l'embed
            msg = await captcha_channel.send(embed=embed)

            # Log de l'envoi du captcha
            if log_channel:
                await log_channel.send(f"🤖 Captcha envoyé pour {member.mention} (Code: {code})")

            # Mise en place du timeout
            captcha_timeouts[member.id] = asyncio.create_task(delete_after_timeout(msg, member.id, 120))

        except Exception as e:
            if log_channel:
                await log_channel.send(f"❌ Erreur lors de la gestion de l'arrivée de {member.mention}: {e}")

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return

        if message.channel == captcha_channel and message.author.id in captcha_codes:
            try:
                # Vérification du code
                if message.content == captcha_codes[message.author.id]:
                    # Récupération des rôles
                    verified_role = discord.utils.get(message.guild.roles, name="Vérifié")
                    visitor_role = message.guild.get_role(1332456121511710790)
                    unverified_role = discord.utils.get(message.guild.roles, name="Non vérifié")

                    # Création du rôle Vérifié si nécessaire
                    if not verified_role:
                        verified_role = await message.guild.create_role(name="Vérifié")

                    # Ajout des rôles
                    await message.author.add_roles(verified_role, visitor_role)
                    if unverified_role:
                        await message.author.remove_roles(unverified_role)

                    # Suppression du message de vérification
                    await message.delete()

                    # Annulation du timeout
                    if message.author.id in captcha_timeouts:
                        captcha_timeouts[message.author.id].cancel()

                    # Suppression des données de captcha
                    del captcha_codes[message.author.id]
                    del captcha_timeouts[message.author.id]

                    # Log de la vérification réussie
                    if log_channel:
                        await log_channel.send(f"✅ {message.author.mention} a été vérifié avec succès")

                    # Message temporaire de confirmation
                    success_msg = await message.channel.send(f"✅ {message.author.mention} a été vérifié avec succès!")
                    await asyncio.sleep(5)
                    await success_msg.delete()
                    return
                else:
                    # Suppression du message incorrect
                    await message.delete()

                    # Log de la tentative incorrecte
                    if log_channel:
                        await log_channel.send(f"❌ Tentative de vérification incorrecte pour {message.author.mention}")
                    return

            except Exception as e:
                if log_channel:
                    await log_channel.send(f"❌ Erreur lors de la vérification de {message.author.mention}: {e}")

    # Vérification des permissions
    if message.author.guild_permissions.administrator:
        return

    # Liste des IDs protégés contre le ping
    protected_ids = [
        1026103239227211826, 413445610302078977, 1308157577560985630
    ]

    # Compteur de pings par utilisateur
    if not hasattr(bot, 'ping_counts'):
        bot.ping_counts = {}

    # Vérification des pings non autorisés
    ping_count = sum(1 for id in protected_ids if f"<@{id}>" in message.content)
    if ping_count > 0:
        if message.author.id not in bot.ping_counts:
            bot.ping_counts[message.author.id] = 0
        bot.ping_counts[message.author.id] += ping_count

        if bot.ping_counts[message.author.id] >= 5:
            await message.author.timeout(datetime.timedelta(hours=1), reason="Trop de mentions d'utilisateurs protégés")
            await message.channel.send(f"{message.author.mention} a été muté pendant 1 heure pour avoir trop mentionné des utilisateurs protégés.")
            bot.ping_counts[message.author.id] = 0
            if log_channel:
                await log_channel.send(f"🔇 {message.author} a été muté pour avoir mentionné des utilisateurs protégés trop de fois")
            return

    bucket = spam_cooldown.get_bucket(message)
    retry_after = bucket.update_rate_limit()
    if retry_after:
        await message.delete()
        user_id = message.author.id
        user_spam_count[user_id] = user_spam_count.get(user_id, 0) + 1
        if user_spam_count[user_id] >= 5:
            await message.author.timeout(datetime.timedelta(hours=1),
                                         reason="Spam excessif")
            await message.channel.send(
                f"{message.author.mention} a été exclu pendant 1 heure pour spam."
            )
            user_spam_count[user_id] = 0
        else:
            await message.channel.send(
                f"{message.author.mention}, merci de ne pas spammer! Avertissement {user_spam_count[user_id]}/5"
            )
        return
    await bot.process_commands(message)


# Commandes de sanctions
def role_check(ctx):
    return any(role.id == staff_role_id for role in ctx.author.roles)


async def check_command_permissions(interaction: discord.Interaction,
                                    command_name: str) -> bool:
    # Seules ces commandes sont accessibles aux membres normaux
    allowed_commands = ["userinfo", "serverinfo", "ticket"]
    if command_name in allowed_commands:
        return True
    # Vérifie si l'utilisateur a le rôle avec l'ID spécifié
    allowed_role_id = 1332456096492683364
    if any(role.id == allowed_role_id for role in interaction.user.roles):
        return True
    await interaction.response.send_message(
        "❌ Vous n'avez pas la permission d'utiliser cette commande.",
        ephemeral=True)
    return False


@bot.tree.command(name="ban", description="Bannir un utilisateur")
@commands.has_permissions(ban_members=True)
@commands.check(role_check)
async def ban(interaction: discord.Interaction,
              membre: discord.Member,
              raison: str = None):
    if not await check_command_permissions(interaction, "ban"):
        return
    await membre.ban(reason=raison)
    await interaction.response.send_message(
        f"{membre} a été banni. Raison: {raison}")
    if log_channel:
        await log_channel.send(
            f"🔨 {interaction.user} a banni {membre}. Raison: {raison}")


@bot.tree.command(name="kick", description="Expulser un utilisateur")
@commands.has_permissions(kick_members=True)
@commands.check(role_check)
async def kick(interaction: discord.Interaction,
               membre: discord.Member,
               raison: str = None):
    await membre.kick(reason=raison)
    await interaction.response.send_message(
        f"{membre} a été expulsé. Raison: {raison}")
    if log_channel:
        await log_channel.send(
            f"👢 {interaction.user} a expulsé {membre}. Raison: {raison}")


@bot.tree.command(name="mute", description="Muter un utilisateur")
@commands.has_permissions(moderate_members=True)
@commands.check(role_check)
async def mute(interaction: discord.Interaction,
               membre: discord.Member,
               duree: int,
               raison: str = None):
    await membre.timeout(datetime.timedelta(minutes=duree), reason=raison)
    await interaction.response.send_message(
        f"{membre} a été muté pour {duree} minutes. Raison: {raison}")
    if log_channel:
        await log_channel.send(
            f"🔇 {interaction.user} a muté {membre} pour {duree} minutes. Raison: {raison}"
        )


@bot.tree.command(name="unmute", description="Démuter un utilisateur")
@commands.has_permissions(moderate_members=True)
@commands.check(role_check)
async def unmute(interaction: discord.Interaction, membre: discord.Member):
    await membre.timeout(None)
    await interaction.response.send_message(f"{membre} a été démuté.")
    if log_channel:
        await log_channel.send(f"🔊 {interaction.user} a démuté {membre}")


@bot.tree.command(name="warn", description="Avertir un utilisateur")
@commands.has_permissions(moderate_members=True)
@commands.check(role_check)
async def warn(interaction: discord.Interaction, membre: discord.Member,
               raison: str):
    if membre.id not in user_warnings:
        user_warnings[membre.id] = []
    user_warnings[membre.id].append(raison)
    nb_warns = len(user_warnings[membre.id])
    await interaction.response.send_message(
        f"{membre} a reçu un avertissement ({nb_warns}/5). Raison: {raison}")
    if nb_warns >= 5:
        await membre.kick(reason="5 avertissements atteints")
        user_warnings[membre.id] = []  # Réinitialiser les avertissements
        await interaction.channel.send(
            f"{membre} a été expulsé pour avoir atteint 5 avertissements.")
        if log_channel:
            await log_channel.send(
                f"👢 {membre} a été expulsé après 5 avertissements")
    elif log_channel:
        await log_channel.send(
            f"⚠️ {interaction.user} a averti {membre} ({nb_warns}/5). Raison: {raison}"
        )


@bot.tree.command(name="warnings",
                  description="Voir les avertissements d'un utilisateur")
@commands.has_permissions(moderate_members=True)
@commands.check(role_check)
async def warnings(interaction: discord.Interaction, membre: discord.Member):
    if membre.id not in user_warnings or not user_warnings[membre.id]:
        await interaction.response.send_message(
            f"{membre} n'a aucun avertissement.")
        return
    warnings_list = "\n".join([f"- {w}" for w in user_warnings[membre.id]])
    await interaction.response.send_message(
        f"Avertissements de {membre}:\n{warnings_list}")


@bot.tree.command(name="clear", description="Supprimer des messages")
@commands.has_permissions(manage_messages=True)
@commands.check(role_check)
async def clear(interaction: discord.Interaction, nombre: int):
    await interaction.response.defer()
    await interaction.channel.purge(limit=nombre)
    await interaction.followup.send(
        f"{nombre} messages ont été supprimés", ephemeral=True)
    if log_channel:
        await log_channel.send(
            f"🗑️ {interaction.user} a supprimé {nombre} messages dans {interaction.channel.mention}"
        )


@bot.tree.command(name="slowmode", description="Définir le mode lent")
@commands.has_permissions(manage_channels=True)
@commands.check(role_check)
async def slowmode(interaction: discord.Interaction, duree: int):
    await interaction.channel.edit(slowmode_delay=duree)
    await interaction.response.send_message(
        f"Mode lent défini à {duree} secondes")


@bot.tree.command(name="lock", description="Verrouiller le salon")
@commands.has_permissions(manage_channels=True)
@commands.check(role_check)
async def lock(interaction: discord.Interaction):
    if isinstance(interaction.channel, discord.VoiceChannel):
        await interaction.channel.set_permissions(interaction.guild.default_role,
                                                connect=False,
                                                speak=False)
    else:
        await interaction.channel.set_permissions(interaction.guild.default_role,
                                                send_messages=False,
                                                add_reactions=False)
    await interaction.response.send_message("🔒 Salon verrouillé")
    if log_channel:
        await log_channel.send(
            f"🔒 {interaction.user} a verrouillé {interaction.channel.mention}")


@bot.tree.command(name="unlock", description="Déverrouiller le salon")
async def unlock(interaction: discord.Interaction):
    if not await check_command_permissions(interaction, "unlock"):
        return
    try:
        if isinstance(interaction.channel, discord.VoiceChannel):
            await interaction.channel.set_permissions(interaction.guild.default_role,
                                                    connect=True,
                                                    speak=True)
        else:
            await interaction.channel.set_permissions(interaction.guild.default_role,
                                                    send_messages=True,
                                                    add_reactions=True)
        await interaction.response.send_message("🔓 Salon déverrouillé")
        if log_channel:
            await log_channel.send(
                f"🔓 {interaction.user} a déverrouillé {interaction.channel.mention}")
    except discord.Forbidden:
        await interaction.response.send_message("Je n'ai pas la permission de déverrouiller ce salon.", ephemeral=True)


# Commandes d'information
@bot.tree.command(name="userinfo",
                  description="Informations sur un utilisateur")
async def userinfo(interaction: discord.Interaction, membre: discord.Member):
    embed = discord.Embed(title=f"Informations sur {membre}")
    embed.add_field(name="ID", value=membre.id)
    embed.add_field(name="Rejoint le",
                    value=membre.joined_at.strftime("%d/%m/%Y"))
    embed.add_field(name="Compte créé le",
                    value=membre.created_at.strftime("%d/%m/%Y"))
    embed.add_field(name="Rôles",
                    value=", ".join([r.name for r in membre.roles[1:]]))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="serverinfo", description="Informations sur le serveur")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"Informations sur {guild.name}")
    embed.add_field(name="Membres", value=guild.member_count)
    embed.add_field(name="Créé le",
                    value=guild.created_at.strftime("%d/%m/%Y"))
    embed.add_field(name="Nombre de rôles", value=len(guild.roles))
    await interaction.response.send_message(embed=embed)


# Commandes de gestion des rôles
@bot.tree.command(name="addrole", description="Ajouter un rôle")
@commands.has_permissions(manage_roles=True)
@commands.check(role_check)
async def addrole(interaction: discord.Interaction, membre: discord.Member,
                  role: discord.Role):
    await membre.add_roles(role)
    await interaction.response.send_message(
        f"Le rôle {role.name} a été ajouté à {membre}")
    if log_channel:
        await log_channel.send(
            f"➕ {interaction.user} a ajouté le rôle {role.name} à {membre}")


@bot.tree.command(name="removerole", description="Retirer un rôle")
@commands.has_permissions(manage_roles=True)
@commands.check(role_check)
async def removerole(interaction: discord.Interaction, membre: discord.Member,
                     role: discord.Role):
    await membre.remove_roles(role)
    await interaction.response.send_message(
        f"Le rôle {role.name} a été retiré à {membre}")
    if log_channel:
        await log_channel.send(
            f"➖ {interaction.user} a retiré le rôle {role.name} à {membre}")


# Commandes Anti-Raid
@bot.tree.command(name="antiraid",
                  description="Activer/désactiver l'anti-raid")
@commands.has_permissions(administrator=True)
async def antiraid(interaction: discord.Interaction, etat: bool):
    global antiraid_enabled
    antiraid_enabled = etat
    await interaction.response.send_message(
        f"Anti-raid {'activé' if etat else 'désactivé'}")
    if log_channel:
        await log_channel.send(
            f"🛡️ {interaction.user} a {'activé' if etat else 'désactivé'} l'anti-raid"
        )


@bot.tree.command(name="whitelist", description="Gérer la whitelist")
@commands.has_permissions(administrator=True)
async def whitelist_cmd(interaction: discord.Interaction, action: str,
                        membre: discord.Member):
    if action == "add":
        whitelist.add(membre.id)
        await interaction.response.send_message(
            f"{membre} a été ajouté à la whitelist")
    elif action == "remove":
        whitelist.remove(membre.id)
        await interaction.response.send_message(
            f"{membre} a été retiré de la whitelist")


# Configuration des logs
@bot.tree.command(name="channelscaptcha", description="Définir le salon pour les captchas")
@commands.has_permissions(administrator=True)
async def set_captcha_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    global captcha_channel
    captcha_channel = channel
    await interaction.response.send_message(f"Salon des captchas défini sur {channel.mention}")

@bot.tree.command(name="logchannel", description="Définir le salon des logs")
@commands.has_permissions(administrator=True)
async def set_log_channel(interaction: discord.Interaction,
                          channel: discord.TextChannel):
    global log_channel
    log_channel = channel
    await interaction.response.send_message(
        f"Salon des logs défini sur {channel.mention}")


@bot.tree.command(name="nouveau_code",
                  description="Recevoir un nouveau code de vérification")
async def nouveau_code(interaction: discord.Interaction):
    code = generate_captcha()
    captcha_codes[interaction.user.id] = code
    embed = discord.Embed(title="Nouveau code de vérification",
                          color=discord.Color.blue())
    embed.description = f"Voici votre nouveau code de vérification. Utilisez la commande `/verify` avec le code ci-dessous:"
    embed.add_field(name="Votre nouveau code", value=f"```{code}```")
    embed.set_footer(text="Utilisez /verify <code> pour vous vérifier")
    try:
        await interaction.user.send(embed=embed)
        await interaction.response.send_message(
            "Un nouveau code vous a été envoyé en message privé.",
            ephemeral=True)
        if log_channel:
            await log_channel.send(
                f"🔄 Un nouveau code captcha a été envoyé à {interaction.user.mention}"
            )
    except:
        await interaction.response.send_message(
            "Impossible de vous envoyer un message privé. Veuillez activer vos DMs.",
            ephemeral=True)
        if log_channel:
            await log_channel.send(
                f"❌ Impossible d'envoyer le nouveau captcha à {interaction.user.mention} (DMs fermés)"
            )


@bot.event
async def on_member_join(member):
    if not captcha_channel:
        return

    unverified_role = discord.utils.get(member.guild.roles, name="Non vérifié")
    if not unverified_role:
        unverified_role = await member.guild.create_role(name="Non vérifié")
    await member.add_roles(unverified_role)

    code = generate_captcha()
    captcha_codes[member.id] = code
    captcha_timeouts[member.id] = asyncio.create_task(asyncio.sleep(120))

    embed = discord.Embed(title="Vérification requise", color=discord.Color.blue())
    embed.description = f"Bienvenue {member.mention}!\nPour accéder au serveur, envoyez le code ci-dessous dans ce salon dans les 2 minutes:\n```{code}```"

    msg = await captcha_channel.send(embed=embed)
    captcha_timeouts[member.id] = asyncio.create_task(delete_after_timeout(msg, member.id, 120))


async def delete_after_timeout(msg, member_id, timeout):
    await asyncio.sleep(timeout)
    if member_id in captcha_codes:
        try:
            await msg.delete()
            await captcha_channel.send(f"{msg.author.mention} Votre temps de vérification a expiré.")
            await member_kick(msg.author)
            del captcha_codes[member_id]
            del captcha_timeouts[member_id]

        except discord.HTTPException:
            pass


async def member_kick(member):
    try:
        await member.kick(reason="Captcha non résolu dans le délai imparti.")
    except discord.HTTPException as e:
        print(f"Erreur lors de l'expulsion de {member}: {e}")


# Démarrer Flask dans un thread séparé
flask_thread = threading.Thread(target=run_flask)
flask_thread.start()

# Lancer le bot
bot.run(token)
