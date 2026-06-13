# Discord Bot — Système de Tickets

Bot Discord complet en Python avec système de tickets, modération et commandes générales.

## Installation

### 1. Prérequis
- Python 3.10 ou supérieur
- Un bot Discord créé sur [discord.com/developers](https://discord.com/developers/applications)

### 2. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 3. Configurer le bot

Ouvre `config.json` et remplis :

```json
{
    "token": "VOTRE_TOKEN_ICI",          ← ton token bot
    "prefix": "!",
    "guild_id": "123456789",             ← ID de ton serveur (pour sync rapide des commandes)
    ...
}
```

**Où trouver le token ?**
→ [Discord Developer Portal](https://discord.com/developers/applications) → ton app → Bot → Reset Token

### 4. Lancer le bot
```bash
python bot.py
```

---

## Configuration des tickets (après lancement)

1. **Crée une catégorie Discord** pour accueillir les tickets
2. **Crée un canal** #logs-tickets et #transcripts  
3. **Crée un rôle** @Staff  
4. Dans un canal Discord, tape :

```
/ticket config
  categorie → ta catégorie
  log_channel → #logs-tickets
  support_role → @Staff
  transcript_channel → #transcripts
  max_tickets → 1
```

5. Dans le canal support, tape :
```
/ticket setup
```
→ Le panel apparaît avec le menu déroulant !

---

## Commandes disponibles

### 📩 Tickets
| Commande | Description | Permission |
|---|---|---|
| `/ticket setup` | Crée le panel dans le canal actuel | Admin |
| `/ticket config` | Configure catégorie, logs, rôle staff… | Admin |
| `/ticket status` | Statut de la configuration | Manage Guild |
| `/ticket list` | Liste les tickets ouverts | Manage Guild |
| `/ticket add <membre>` | Ajoute un membre au ticket | Tous (dans un ticket) |
| `/ticket remove <membre>` | Retire un membre du ticket | Tous (dans un ticket) |
| `/ticket close [raison]` | Ferme le ticket + transcript | Tous (dans un ticket) |
| `/ticket delete` | Supprime le ticket | Manage Channels |

### 🔨 Modération
| Commande | Description | Permission |
|---|---|---|
| `/kick <membre> [raison]` | Expulse | Kick Members |
| `/ban <membre> [raison]` | Bannit | Ban Members |
| `/unban <user_id> [raison]` | Débannit | Ban Members |
| `/mute <membre> [durée] [raison]` | Timeout (minutes) | Moderate Members |
| `/unmute <membre>` | Retire le timeout | Moderate Members |
| `/clear <nombre> [membre]` | Supprime des messages | Manage Messages |
| `/warn <membre> <raison>` | Avertit | Kick Members |
| `/warnings <membre>` | Voir les warns | Kick Members |
| `/slowmode <secondes>` | Slowmode | Manage Channels |

### ℹ️ Général
| Commande | Description |
|---|---|
| `/ping` | Latence WebSocket + API |
| `/help` | Liste des commandes |
| `/avatar [membre]` | Avatar HD |
| `/userinfo [membre]` | Infos complètes sur un membre |
| `/serverinfo` | Infos sur le serveur |
| `/uptime` | Temps de fonctionnement |

---

## Logs de modération

Pour activer les logs de modération (kick, ban, warn…), ajoute dans `config.json` :
```json
"mod_log_channel_id": "ID_DU_CANAL"
```

---

## Structure du projet

```
discord_bot/
├── bot.py              ← Point d'entrée
├── config.json         ← Configuration (token, IDs…)
├── requirements.txt    ← Dépendances Python
├── data/               ← Données auto-générées
│   ├── tickets.json    ← Tickets ouverts/fermés
│   ├── counter.json    ← Compteur de tickets
│   └── warns.json      ← Avertissements
└── cogs/
    ├── tickets.py      ← Système de tickets complet
    ├── moderation.py   ← Commandes de modération
    └── general.py      ← Commandes générales
```

---

## Permissions bot requises

Sur le portail développeur → Bot → activer :
- **Privileged Gateway Intents** : Server Members Intent + Message Content Intent

Lors de l'invitation sur le serveur, accorde :
- `bot` + `applications.commands`
- Permissions : Administrator (ou au minimum Manage Channels, Kick Members, Ban Members, Moderate Members, Manage Messages)
