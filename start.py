import os
import discord
import datetime
import asyncio
import threading
import random
from discord import Embed
from flask import Flask
from discord.ui import Button, View
from discord.ext import commands
from dotenv import load_dotenv

app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running!'

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

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
captcha_attempts = {}
MAX_ATTEMPTS = 3

def generate_captcha():
    """Génère un code captcha simple en minuscules"""
    import random
    import string
    
    # Uniquement lettres minuscules et chiffres
    chars = string.ascii_lowercase + string.digits
    # Code de 6 caractères pour faciliter la copie
    return ''.join(random.choices(chars, k=6))

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
    # Start the Flask server in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()

@bot.tree.command(name="setcaptcha", description="Définir le salon pour les captchas")
@commands.has_permissions(administrator=True)
async def setcaptcha(interaction: discord.Interaction, salon: discord.TextChannel):
    global captcha_channel
    captcha_channel = salon
    await interaction.response.send_message(f"Salon de captcha défini sur {salon.mention}")

@bot.tree.command(name="setlogs", description="Définir le salon des logs")
@commands.has_permissions(administrator=True)
async def setlogs(interaction: discord.Interaction, salon: discord.TextChannel):
    try:
        await interaction.response.defer(ephemeral=True)
        global log_channel
        log_channel = salon

        # Message de confirmation dans le salon des logs
        embed = discord.Embed(title="✅ Salon des logs configuré", color=discord.Color.green())
        embed.description = "Les logs seront désormais envoyés dans ce salon"
        embed.add_field(name="Configuré par", value=f"{interaction.user.mention}")
        embed.set_footer(text=f"ID de l'action: {interaction.id}")
        await salon.send(embed=embed)

        await interaction.followup.send(f"Salon des logs défini sur {salon.mention}")
    except Exception as e:
        await interaction.followup.send(f"Une erreur est survenue: {str(e)}", ephemeral=True)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel == captcha_channel and message.author.id in captcha_codes:
        await message.delete()
        if message.content == captcha_codes[message.author.id]:
            verified_role = discord.utils.get(message.guild.roles, name="Vérifié")
            visitor_role = message.guild.get_role(1332456121511710790)
            unverified_role = discord.utils.get(message.guild.roles, name="Non vérifié")

            if not verified_role:
                verified_role = await message.guild.create_role(name="Vérifié")

            await message.author.add_roles(verified_role, visitor_role)
            if unverified_role:
                await message.author.remove_roles(unverified_role)

            await message.channel.purge(limit=100, check=lambda m: m.author == bot.user or m.author == message.author)

            if log_channel:
                embed = discord.Embed(title="✅ Vérification Réussie", color=discord.Color.green())
                embed.add_field(name="Utilisateur", value=f"{message.author.mention} ({message.author.id})")
                embed.add_field(name="Compte créé le", value=message.author.created_at.strftime("%d/%m/%Y %H:%M"))
                embed.add_field(name="Rejoint le", value=message.author.joined_at.strftime("%d/%m/%Y %H:%M"))
                embed.set_thumbnail(url=message.author.display_avatar.url)
                await log_channel.send(embed=embed)

            del captcha_codes[message.author.id]

async def check_timeout(member_id, channel):
    await asyncio.sleep(120)
    if member_id in captcha_codes:
        member = channel.guild.get_member(member_id)
        if member:
            await channel.purge(limit=100, check=lambda m: m.author == bot.user)
            await member.kick(reason="N'a pas complété la vérification dans les 2 minutes")

            if log_channel:
                embed = discord.Embed(title="⏰ Timeout de vérification", color=discord.Color.red())
                embed.add_field(name="Utilisateur", value=f"{member.mention} ({member.id})")
                embed.add_field(name="Compte créé le", value=member.created_at.strftime("%d/%m/%Y %H:%M"))
                embed.add_field(name="Rejoint le", value=member.joined_at.strftime("%d/%m/%Y %H:%M"))
                embed.set_thumbnail(url=member.display_avatar.url)
                await log_channel.send(embed=embed)

            del captcha_codes[member_id]

@bot.event
async def on_member_join(member):
    if not captcha_channel:
        return

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    captcha_codes[member.id] = code

    unverified_role = discord.utils.get(member.guild.roles, name="Non vérifié")
    if not unverified_role:
        unverified_role = await member.guild.create_role(name="Non vérifié")
    await member.add_roles(unverified_role)

    embed = discord.Embed(title="Vérification Requise", color=discord.Color.blue())
    embed.description = f"Bienvenue {member.mention}!\nVeuillez entrer le code suivant pour accéder au serveur:\n```{code}```"
    await captcha_channel.send(embed=embed)

    if log_channel:
        embed = discord.Embed(title="👋 Nouveau Membre", color=discord.Color.blue())
        embed.add_field(name="Utilisateur", value=f"{member.mention} ({member.id})")
        embed.add_field(name="Compte créé le", value=member.created_at.strftime("%d/%m/%Y %H:%M"))
        embed.add_field(name="Code Captcha", value=f"```{code}```")
        embed.set_thumbnail(url=member.display_avatar.url)
        await log_channel.send(embed=embed)

    asyncio.create_task(check_timeout(member.id, captcha_channel))

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
            embed = discord.Embed(title="🤖 Captcha Envoyé", color=discord.Color.green())
            embed.add_field(name="Utilisateur", value=f"{member.mention} ({member.id})")
            embed.add_field(name="Code", value=f"```{code}```")
            embed.add_field(name="Compte créé le", value=member.created_at.strftime("%d/%m/%Y %H:%M"))
            embed.add_field(name="Rejoint le", value=member.joined_at.strftime("%d/%m/%Y %H:%M"))
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Action effectuée par {bot.user.name}", icon_url=bot.user.display_avatar.url)
            await log_channel.send(embed=embed)

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
        # Suppression automatique du message de l'utilisateur
        await message.delete()
        
        try:
            # Gestion des tentatives
            if message.author.id not in captcha_attempts:
                captcha_attempts[message.author.id] = 0
            captcha_attempts[message.author.id] += 1
            
            # Envoi d'un message privé avec le nombre de tentatives restantes
            remaining_attempts = MAX_ATTEMPTS - captcha_attempts[message.author.id]
            try:
                await message.author.send(f"Il vous reste {remaining_attempts} tentatives. Code entré: `{message.content}`")
            except:
                pass
                
            # Vérification du nombre de tentatives
            if captcha_attempts[message.author.id] > MAX_ATTEMPTS:
                try:
                    await message.author.send("Vous avez dépassé le nombre maximum de tentatives.")
                except:
                    pass
                await message.author.kick(reason="Trop de tentatives de captcha incorrectes")
                del captcha_codes[message.author.id]
                del captcha_attempts[message.author.id]
                if log_channel:
                    await log_channel.send(f"🚫 {message.author.mention} a été expulsé pour trop de tentatives de captcha incorrectes")
                return
                
            # Vérification du code
            if message.content == captcha_codes[message.author.id]:
                # Récupération des rôles
                verified_role = discord.utils.get(message.guild.roles, name="Vérifié")
                visitor_role = message.guild.get_role(1332456121511710790)
                unverified_role = discord.utils.get(message.guild.roles, name="Non vérifié")

                # Suppression de tous les messages du salon
                await captcha_channel.purge()

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
                    embed = discord.Embed(title="✅ Vérification Réussie", color=discord.Color.green())
                    embed.add_field(name="Utilisateur", value=f"{message.author.mention} ({message.author.id})")
                    embed.add_field(name="Compte créé le", value=message.author.created_at.strftime("%d/%m/%Y %H:%M"))
                    embed.add_field(name="Rejoint le", value=message.author.joined_at.strftime("%d/%m/%Y %H:%M"))
                    embed.set_thumbnail(url=message.author.display_avatar.url)
                    embed.set_footer(text=f"Action effectuée par {bot.user.name}", icon_url=bot.user.display_avatar.url)
                    await log_channel.send(embed=embed)

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
                    embed = discord.Embed(title="❌ Vérification Incorrecte", color=discord.Color.red())
                    embed.add_field(name="Utilisateur", value=f"{message.author.mention} ({message.author.id})")
                    embed.add_field(name="Tentative", value=f"```{message.content}```")
                    embed.add_field(name="Compte créé le", value=message.author.created_at.strftime("%d/%m/%Y %H:%M"))
                    embed.add_field(name="Rejoint le", value=message.author.joined_at.strftime("%d/%m/%Y %H:%M"))
                    embed.set_thumbnail(url=message.author.display_avatar.url)
                    embed.set_footer(text=f"Action effectuée par {bot.user.name}", icon_url=bot.user.display_avatar.url)
                    await log_channel.send(embed=embed)
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
                embed = discord.Embed(title="🔇 Mute pour mentions abusives", color=discord.Color.orange())
                embed.add_field(name="Utilisateur", value=f"{message.author.mention} ({message.author.id})")
                embed.add_field(name="Raison", value="Trop de mentions d'utilisateurs protégés")
                embed.add_field(name="Durée", value="1 heure")
                embed.set_footer(text=f"Action effectuée par {bot.user.name}", icon_url=bot.user.display_avatar.url)
                await log_channel.send(embed=embed)
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
            if log_channel:
                embed = discord.Embed(title="🔇 Mute pour spam", color=discord.Color.orange())
                embed.add_field(name="Utilisateur", value=f"{message.author.mention} ({message.author.id})")
                embed.add_field(name="Raison", value="Spam excessif")
                embed.add_field(name="Durée", value="1 heure")
                embed.set_footer(text=f"Action effectuée par {bot.user.name}", icon_url=bot.user.display_avatar.url)
                await log_channel.send(embed=embed)
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
    messages_ban = [
        f"🔨 Paf! {membre.name} vient de gagner un aller simple vers BanLand!",
        f"👋 {membre.name} a décidé de prendre des vacances permanentes!",
        f"💥 {membre.name} s'est fait bannir plus vite que son ombre!"
    ]
    await interaction.response.send_message(random.choice(messages_ban))
    if log_channel:
        embed = discord.Embed(title="🔨 Bannissement", color=discord.Color.red())
        embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
        embed.add_field(name="Utilisateur", value=f"{membre.mention} ({membre.id})")
        embed.add_field(name="Raison", value=raison or "Aucune raison spécifiée")
        embed.add_field(name="Compte créé le", value=membre.created_at.strftime("%d/%m/%Y %H:%M"))
        embed.add_field(name="Rejoint le", value=membre.joined_at.strftime("%d/%m/%Y %H:%M"))
        embed.set_thumbnail(url=membre.display_avatar.url)
        embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
        await log_channel.send(embed=embed)


@bot.tree.command(name="kick", description="Expulser un utilisateur")
@commands.has_permissions(kick_members=True)
@commands.check(role_check)
async def kick(interaction: discord.Interaction,
               membre: discord.Member,
               raison: str = None):
    await membre.kick(reason=raison)
    messages_kick = [
        f"🦵 {membre.name} vient d'apprendre à voler... hors du serveur!",
        f"🚀 {membre.name} a été promu au rang d'astronaute... Bon voyage!",
        f"🎭 Et le prix de la sortie dramatique revient à... {membre.name}!"
    ]
    await interaction.response.send_message(random.choice(messages_kick))
    if log_channel:
        embed = discord.Embed(title="👢 Expulsion", color=discord.Color.orange())
        embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
        embed.add_field(name="Utilisateur", value=f"{membre.mention} ({membre.id})")
        embed.add_field(name="Raison", value=raison or "Aucune raison spécifiée")
        embed.add_field(name="Compte créé le", value=membre.created_at.strftime("%d/%m/%Y %H:%M"))
        embed.add_field(name="Rejoint le", value=membre.joined_at.strftime("%d/%m/%Y %H:%M"))
        embed.set_thumbnail(url=membre.display_avatar.url)
        embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
        await log_channel.send(embed=embed)


@bot.tree.command(name="mute", description="Muter un utilisateur")
@commands.has_permissions(moderate_members=True)
@commands.check(role_check)
async def mute(interaction: discord.Interaction,
               membre: discord.Member,
               duree: int,
               raison: str = None):
    await membre.timeout(datetime.timedelta(minutes=duree), reason=raison)
    messages_mute = [
        f"🤐 {membre.name} joue maintenant à 'Mime Simulator' pendant {duree} minutes!",
        f"📢 {membre.name} prend une pause vocale forcée de {duree} minutes!",
        f"🤫 Chut! {membre.name} fait une sieste de {duree} minutes!"
    ]
    await interaction.response.send_message(random.choice(messages_mute))
    if log_channel:
        embed = discord.Embed(title="🔇 Mute", color=discord.Color.orange())
        embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
        embed.add_field(name="Utilisateur", value=f"{membre.mention} ({membre.id})")
        embed.add_field(name="Raison", value=raison or "Aucune raison spécifiée")
        embed.add_field(name="Durée", value=f"{duree} minutes")
        embed.add_field(name="Compte créé le", value=membre.created_at.strftime("%d/%m/%Y %H:%M"))
        embed.add_field(name="Rejoint le", value=membre.joined_at.strftime("%d/%m/%Y %H:%M"))
        embed.set_thumbnail(url=membre.display_avatar.url)
        embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
        await log_channel.send(embed=embed)


@bot.tree.command(name="unmute", description="Démuter un utilisateur")
@commands.has_permissions(moderate_members=True)
@commands.check(role_check)
async def unmute(interaction: discord.Interaction, membre: discord.Member):
    await membre.timeout(None)
    await interaction.response.send_message(f"{membre} a été démuté.")
    if log_channel:
        embed = discord.Embed(title="🔊 Unmute", color=discord.Color.green())
        embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
        embed.add_field(name="Utilisateur", value=f"{membre.mention} ({membre.id})")
        embed.add_field(name="Compte créé le", value=membre.created_at.strftime("%d/%m/%Y %H:%M"))
        embed.add_field(name="Rejoint le", value=membre.joined_at.strftime("%d/%m/%Y %H:%M"))
        embed.set_thumbnail(url=membre.display_avatar.url)
        embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
        await log_channel.send(embed=embed)


@bot.tree.command(name="warn", description="Avertir un utilisateur")
@commands.has_permissions(moderate_members=True)
@commands.check(role_check)
async def warn(interaction: discord.Interaction, membre: discord.Member,
               raison: str):
    if membre.id not in user_warnings:
        user_warnings[membre.id] = []
    user_warnings[membre.id].append(raison)
    nb_warns = len(user_warnings[membre.id])
    messages_warn = [
        f"⚠️ {membre.name} collectionne les avertissements comme des Pokémon! ({nb_warns}/5)",
        f"📝 {membre.name} vient d'ajouter une note à son carnet de bêtises! ({nb_warns}/5)",
        f"🎯 Bingo! {membre.name} décroche son {nb_warns}ème avertissement!"
    ]
    await interaction.response.send_message(random.choice(messages_warn))
    if nb_warns >= 5:
        await membre.kick(reason="5 avertissements atteints")
        user_warnings[membre.id] = []  # Réinitialiser les avertissements
        await interaction.channel.send(
            f"{membre} a été expulsé pour avoir atteint 5 avertissements.")
        if log_channel:
            embed = discord.Embed(title="👢 Expulsion pour 5 avertissements", color=discord.Color.red())
            embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
            embed.add_field(name="Utilisateur", value=f"{membre.mention} ({membre.id})")
            embed.add_field(name="Raison", value="5 avertissements atteints")
            embed.add_field(name="Compte créé le", value=membre.created_at.strftime("%d/%m/%Y %H:%M"))
            embed.add_field(name="Rejoint le", value=membre.joined_at.strftime("%d/%m/%Y %H:%M"))
            embed.set_thumbnail(url=membre.display_avatar.url)
            embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
            await log_channel.send(embed=embed)
    elif log_channel:
        embed = discord.Embed(title="⚠️ Avertissement", color=discord.Color.orange())
        embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
        embed.add_field(name="Utilisateur", value=f"{membre.mention} ({membre.id})")
        embed.add_field(name="Raison", value=raison)
        embed.add_field(name="Nombre d'avertissements", value=f"{nb_warns}/5")
        embed.add_field(name="Compte créé le", value=membre.created_at.strftime("%d/%m/%Y %H:%M"))
        embed.add_field(name="Rejoint le", value=membre.joined_at.strftime("%d/%m/%Y %H:%M"))
        embed.set_thumbnail(url=membre.display_avatar.url)
        embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
        await log_channel.send(embed=embed)


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
        embed = discord.Embed(title="🗑️ Messages Supprimés", color=discord.Color.purple())
        embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
        embed.add_field(name="Salon", value=f"{interaction.channel.mention}")
        embed.add_field(name="Nombre de messages", value=str(nombre))
        embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
        await log_channel.send(embed=embed)


@bot.tree.command(name="slowmode", description="Définir le mode lent")
@commands.has_permissions(manage_channels=True)
@commands.check(role_check)
async def slowmode(interaction: discord.Interaction, duree: int):
    await interaction.channel.edit(slowmode_delay=duree)
    await interaction.response.send_message(
        f"Mode lent défini à {duree} secondes")
    if log_channel:
        embed = discord.Embed(title="🐌 Slowmode Activé", color=discord.Color.blue())
        embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
        embed.add_field(name="Salon", value=f"{interaction.channel.mention}")
        embed.add_field(name="Durée", value=f"{duree} secondes")
        embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
        await log_channel.send(embed=embed)


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
        embed = discord.Embed(title="🔒 Salon Verrouillé", color=discord.Color.red())
        embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
        embed.add_field(name="Salon", value=f"{interaction.channel.mention}")
        embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
        await log_channel.send(embed=embed)


@bot.tree.command(name="purge", description="Purge et recrée le salon")
@commands.has_permissions(manage_channels=True)
@commands.check(role_check)
async def purge(interaction: discord.Interaction):
    if not await check_command_permissions(interaction, "purge"):
        return

    try:
        # Sauvegarder les infos du salon
        old_channel = interaction.channel
        channel_position = old_channel.position
        channel_name = old_channel.name
        channel_category = old_channel.category
        channel_permissions = old_channel.overwrites

        # Supprimer l'ancien salon
        await old_channel.delete()

        # Créer le nouveau salon
        new_channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=channel_category,
            position=channel_position,
            overwrites=channel_permissions
        )

        # Messages drôles sur le thème du ménage
        messages = [
            "🧹 Je viens de faire le grand ménage de printemps !",
            "🧼 Plus propre que ça, tu meurs !",
            "🗑️ Les messages d'avant ? Quels messages ?",
            "✨ Tadaaa ! C'est tout beau tout neuf !",
            "🧽 J'ai tout récuré, même sous les emojis !"
        ]

        await new_channel.send(random.choice(messages))

        if log_channel:
            embed = discord.Embed(title="🔄 Salon Purgé", color=discord.Color.blue())
            embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
            embed.add_field(name="Salon", value=f"#{channel_name}")
            embed.set_footer(text=f"Action effectuée par {bot.user.name}", icon_url=bot.user.display_avatar.url)
            await log_channel.send(embed=embed)

    except Exception as e:
        if log_channel:
            await log_channel.send(f"❌ Erreur lors de la purge du salon : {e}")

@bot.tree.command(name="test", description="Tester le système de captcha")
async def test(interaction: discord.Interaction):
    code = generate_captcha()
    embed = discord.Embed(title="Test Captcha", color=discord.Color.blue())
    embed.description = f"Voici un code captcha de test:\n```{code}```\nVous pouvez l'essayer, mais il n'aura aucun effet."
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="unlock", description="Déverrouiller le salon")
@commands.has_permissions(manage_channels=True)
@commands.check(role_check)
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
            embed = discord.Embed(title="🔓 Salon Déverrouillé", color=discord.Color.green())
            embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
            embed.add_field(name="Salon", value=f"{interaction.channel.mention}")
            embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
            await log_channel.send(embed=embed)
    except:
        await interaction.response.send_message("Une erreur est survenue lors du déverrouillage du salon.", ephemeral=True)
        if log_channel:
            embed = discord.Embed(title="❌ Erreur lors du déverrouillage", color=discord.Color.red())
            embed.add_field(name="Modérateur", value=f"{interaction.user.mention} ({interaction.user.id})")
            embed.add_field(name="Salon", value=f"{interaction.channel.mention}")
            embed.set_footer(text=f"ID de l'action: {interaction.id}", icon_url=interaction.user.display_avatar.url)
            await log_channel.send(embed=embed)




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

    if not captcha_channel:
        return

    embed = discord.Embed(title="Vérification requise", color=discord.Color.blue())
    embed.description = f"Bienvenue {member.mention}!\nPour accéder au serveur, envoyez le code suivant dans ce salon dans les 2 minutes:\n```{code}```"
    await captcha_channel.send(embed=embed)
    if log_channel:
            embed = discord.Embed(title="🤖 Captcha Envoyé", color=discord.Color.green())
            embed.add_field(name="Utilisateur", value=f"{member.mention} ({member.id})")
            embed.add_field(name="Code", value=f"```{code}```")
            embed.add_field(name="Compte créé le", value=member.created_at.strftime("%d/%m/%Y %H:%M"))
            embed.add_field(name="Rejoint le", value=member.joined_at.strftime("%d/%m/%Y %H:%M"))
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Action effectuée par {bot.user.name}", icon_url=bot.user.display_avatar.url)
            await log_channel.send(embed=embed)

    try:
        await asyncio.wait_for(captcha_timeouts[member.id], timeout=120)
        if member.id in captcha_codes:
            await member.kick(reason="Timeout captcha")
            del captcha_codes[member.id]
            del captcha_timeouts[member.id]
            if log_channel:
                await log_channel.send(f"{member} a été expulsé pour timeout captcha")

    except asyncio.TimeoutError:
        pass
    except Exception as e:
        if log_channel:
            await log_channel.send(f"Erreur lors de la gestion du timeout captcha pour {member}: {e}")

bot.run(token)
