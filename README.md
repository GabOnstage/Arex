# Arexium

A feature-rich Discord bot designed with moderation, Roblox player lookup, and entertainment capabilities using `discord.py` v2.

![Made with Discord.py](https://img.shields.io/badge/Made%20with%20Discord.py-0388cb?style=flat&logo=discord&logoColor=white)
![Supports Slash commands](https://img.shields.io/badge/Supports%20Slash%20commands-00b3b3?style=flat&logo=slashdot&logoColor=white)
![Supports Environment variables](https://img.shields.io/badge/Supports%20Environment%20variables-.ENV-black?labelColor=4d4dff&style=flat&logo=dotenv&logoColor=white)

---

## Features

- **Roblox Intelligence**: Look up complete player statistics, avatar thumbnails, ban status, followers, and badges (`/find`, `/badge`).
- **Formula 1 Standings**: Real-time latest race classification, lap counts, and fastest laps powered by the OpenF1 API (`/f1`).
- **Interactive Mini-Games & Fun**: Rock Paper Scissors (`/rockpaperscissors`), Pokemon guessing game (`/guesspokemon`), Magic 8-Ball (`/ball`), Jokes (`/joke`), Astronomy Picture of the Day (`/apod`), and Memes (`/meme`).
- **Moderation & Utilities**: IP/Domain Geolocation (`/locate`), User profile inspection (`/userinfo`), Temporary auto-expiring channels (`/tempchannel`), and Color analysis (`/color`).
- **Social Media Embeds**: X/Twitter, TikTok, Instagram, Reddit, and Threads links are rendered as native bot embeds with author details, post text, images/videos, stats, a "View post" link, and an author/moderator delete button. Instagram metadata is pulled from vxinstagram, which provides captions, author/avatar details, likes/comments and full albums. X profile links are rendered as profile cards (`/xinfo`). If a platform API is unavailable, the bot logs the error to the console and falls back to the embed-proxy link behavior (`!embed`).
- **Hybrid Slash Commands**: Works seamlessly with both slash commands (`/command`) and text prefix commands (`!command`).
- **App Context Menus**: Right-click a message for **Forward Message** / **Fix Embed**, or right-click a user for **User Info** / **Insult User**.
- **Interactive Help Menu**: Categorized, paginated help browser powered by `reactionmenu` (`/testhelp` and `/help`).

---

## Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ITron-Legends/Remy.git
   cd Arex-main
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   Inline video/GIF cards use Discord Components V2, which requires
   **discord.py 2.6 or newer**. If you already have an older version installed,
   force the upgrade with `pip install -U "discord.py>=2.6"`.

3. **Configure Environment Variables:**
   Copy `.env.example` to `.env` and fill in your Discord credentials:
   ```bash
   cp .env.example .env
   ```

4. **Run the bot:**
   ```bash
   python main.py
   ```

5. **Sync Slash Commands:**
   As the bot owner, run `!sync` in a server to synchronize slash commands with Discord.

### Required Bot Permissions

For the social media embed fixer, give the bot these channel permissions:

- **Send Messages** and **Embed Links** — post the generated card.
- **Attach Files** — upload TikTok/Instagram/Reddit/X videos as playable attachments when discord.py 2.6+ Components V2 cards are unavailable. Without it (or when a video exceeds the upload limit), the bot posts the direct MP4 link as a separate message.
- **Read Message History** — look up the original message when the delete button is used.
- **Manage Messages** — hide the original link preview (`SUPPRESS_EMBEDS`). Without it, the bot still replies with its own embed, but the author's preview stays visible.

Native cards use the following public data sources, in order, and log any
failures to the console before falling back to the proxy link:

| Platform | Primary | Fallbacks |
| :--- | :--- | :--- |
| X/Twitter | FxTwitter API | domain-swap proxy (`fixupx.com` / `twitterez.com`) |
| TikTok | tikwm API | TikTok oEmbed, OpenGraph page scrape, proxy (`tnktok.com` / `tiktokez.com`) |
| Instagram | Instagram oEmbed + embed page | OpenGraph page scrape, proxy (`axinstagram.com` / `instagramez.com`) |
| Reddit | Reddit public JSON (`old.reddit.com` / `api.reddit.com`) | alternate JSON hosts, proxy (`vxreddit.com` / `redditez.com`) |
| Threads | OpenGraph page scrape (Meta/Google crawler user agents) | proxy (`vxthreads.net` / `threadsez.net`) |

---

## Environment Variables

| Variable | Description | Required |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | Your Discord Bot Token from Developer Portal | **Yes** |
| `APPLICATION_ID` | Your Discord Bot Application ID | **Yes** |
| `OWNERS` | Comma-separated list of Bot Owner Discord User IDs | **Yes** |
| `COMMAND` | Command prefix (e.g. `!`) | Optional (Default: `!`) |
| `ALLOWED_USER_IDS` | Comma-separated list of Admin Discord User IDs for `/al` | Optional |
| `NASA_API_KEY` | NASA API Key for `/apod` | Optional (Default: `DEMO_KEY`) |
| `jeyy_api` | Jeyy API Token for `/avatar` filters | Optional |

---

## License

Arexium is licensed under Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0).
