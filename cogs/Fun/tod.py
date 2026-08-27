import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import random
from typing import Optional

BASE_TOD_API = "https://api.truthordarebot.xyz/v1"

FALLBACK_PROMPTS = {
    "truth": [
        {"question": "What is the biggest secret you've kept from your best friend?", "rating": "PG13"},
        {"question": "What is your biggest regret in life?", "rating": "PG"},
        {"question": "Have you ever lied to get out of trouble?", "rating": "PG"},
        {"question": "What is the most embarrassing thing in your search history?", "rating": "PG13"},
        {"question": "Who is your secret crush right now?", "rating": "PG13"},
        {"question": "What is the worst date you've ever been on?", "rating": "PG13"},
        {"question": "If you could change one thing about yourself, what would it be?", "rating": "PG"},
        {"question": "What's the most childish thing you still do?", "rating": "PG"}
    ],
    "dare": [
        {"question": "Send the 5th photo in your camera roll to this channel.", "rating": "PG"},
        {"question": "Do an impression of another person in this server until someone guesses who it is.", "rating": "PG"},
        {"question": "Let another player type anything they want in your status for 10 minutes.", "rating": "PG13"},
        {"question": "Sing the chorus of your favorite song in a voice channel or send a voice message.", "rating": "PG"},
        {"question": "Text your best friend telling them you just won the lottery.", "rating": "PG"},
        {"question": "Speak in rhyme for the next 3 rounds of the game.", "rating": "PG"}
    ],
    "nhie": [
        {"question": "Never have I ever ghosted someone.", "rating": "PG13"},
        {"question": "Never have I ever pretended to be sick to skip school or work.", "rating": "PG"},
        {"question": "Never have I ever accidentally sent a text about someone to that exact person.", "rating": "PG13"},
        {"question": "Never have I ever stayed awake for more than 24 hours.", "rating": "PG"},
        {"question": "Never have I ever stalked an ex on social media.", "rating": "PG13"},
        {"question": "Never have I ever lied about my age online.", "rating": "PG"}
    ],
    "wyr": [
        {"question": "Would you rather have the ability to fly or be invisible?", "rating": "PG"},
        {"question": "Would you rather know the date of your death or the cause of your death?", "rating": "PG13"},
        {"question": "Would you rather lose all your old memories or never be able to make new ones?", "rating": "PG"},
        {"question": "Would you rather be rich and lonely or broke with lots of great friends?", "rating": "PG"}
    ],
    "paranoia": [
        {"question": "Who in this server is most likely to survive a zombie apocalypse?", "rating": "PG"},
        {"question": "Who is most likely to accidentally become famous?", "rating": "PG"},
        {"question": "Who is most likely to go to sleep during a movie?", "rating": "PG"},
        {"question": "Who here is most likely to spend all their money on something completely useless?", "rating": "PG"}
    ]
}

async def fetch_tod_prompt(bot: commands.Bot, category: str, rating: str = "pg13") -> dict:
    session = getattr(bot, 'session', None)
    close_session = False
    if session is None or session.closed:
        session = aiohttp.ClientSession()
        close_session = True

    url = f"{BASE_TOD_API}/{category}?rating={rating.lower()}"

    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if isinstance(data, dict) and "question" in data:
                    return data
    except Exception:
        pass
    finally:
        if close_session and session and not session.closed:
            await session.close()

    pool = FALLBACK_PROMPTS.get(category, FALLBACK_PROMPTS.get("truth", []))
    chosen = random.choice(pool)
    return {
        "type": category.upper(),
        "rating": chosen.get("rating", rating.upper()),
        "question": chosen["question"]
    }

class TODView(discord.ui.View):
    def __init__(self, bot: commands.Bot, current_rating: str = "pg13", timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.rating = current_rating

    async def _handle_click(self, interaction: discord.Interaction, category: str, title: str, color: discord.Color):
        await interaction.response.defer()
        data = await fetch_tod_prompt(self.bot, category, self.rating)
        question = data.get("question", "No question received.")
        q_rating = data.get("rating", self.rating).upper()

        embed = discord.Embed(
            title=title,
            description=f"### {question}",
            color=color
        )
        embed.set_footer(text=f"Rating: {q_rating} • Truth or Dare")
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Truth", emoji="❓", style=discord.ButtonStyle.success)
    async def truth_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_click(interaction, "truth", "🤔 Truth", discord.Color.green())

    @discord.ui.button(label="Dare", emoji="🔥", style=discord.ButtonStyle.danger)
    async def dare_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_click(interaction, "dare", "⚡ Dare", discord.Color.red())

    @discord.ui.button(label="Never Have I Ever", emoji="🙈", style=discord.ButtonStyle.primary)
    async def nhie_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_click(interaction, "nhie", "🤫 Never Have I Ever", discord.Color.purple())

    @discord.ui.button(label="Would You Rather", emoji="⚖️", style=discord.ButtonStyle.secondary)
    async def wyr_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_click(interaction, "wyr", "⚖️ Would You Rather", discord.Color.gold())

    @discord.ui.button(label="Random", emoji="🎲", style=discord.ButtonStyle.secondary)
    async def random_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        categories = ["truth", "dare", "nhie", "wyr"]
        chosen = random.choice(categories)
        mapping = {
            "truth": ("🤔 Truth", discord.Color.green()),
            "dare": ("⚡ Dare", discord.Color.red()),
            "nhie": ("🤫 Never Have I Ever", discord.Color.purple()),
            "wyr": ("⚖️ Would You Rather", discord.Color.gold())
        }
        title, color = mapping[chosen]
        await self._handle_click(interaction, chosen, title, color)

class TruthOrDare(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="truth", description="Get a random Truth question.")
    @app_commands.describe(rating="Rating filter for the question")
    @app_commands.choices(rating=[
        app_commands.Choice(name="PG (Family friendly)", value="pg"),
        app_commands.Choice(name="PG-13 (Standard)", value="pg13"),
    ])
    async def truth(self, ctx: commands.Context, rating: Optional[str] = "pg13"):
        await ctx.defer()
        selected_rating = rating.lower() if rating else "pg13"

        data = await fetch_tod_prompt(self.bot, "truth", selected_rating)
        question = data.get("question", "No question received.")
        q_rating = data.get("rating", selected_rating).upper()

        embed = discord.Embed(
            title="🤔 Truth",
            description=f"### {question}",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Rating: {q_rating}")
        view = TODView(self.bot, current_rating=selected_rating)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="dare", description="Get a random Dare challenge.")
    @app_commands.describe(rating="Rating filter for the dare")
    @app_commands.choices(rating=[
        app_commands.Choice(name="PG (Family friendly)", value="pg"),
        app_commands.Choice(name="PG-13 (Standard)", value="pg13"),
    ])
    async def dare(self, ctx: commands.Context, rating: Optional[str] = "pg13"):
        await ctx.defer()
        selected_rating = rating.lower() if rating else "pg13"

        data = await fetch_tod_prompt(self.bot, "dare", selected_rating)
        question = data.get("question", "No question received.")
        q_rating = data.get("rating", selected_rating).upper()

        embed = discord.Embed(
            title="⚡ Dare",
            description=f"### {question}",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Rating: {q_rating}")
        view = TODView(self.bot, current_rating=selected_rating)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="nhie", description="Get a random 'Never Have I Ever' statement.")
    @app_commands.describe(rating="Rating filter for the prompt")
    @app_commands.choices(rating=[
        app_commands.Choice(name="PG (Family friendly)", value="pg"),
        app_commands.Choice(name="PG-13 (Standard)", value="pg13"),
    ])
    async def nhie(self, ctx: commands.Context, rating: Optional[str] = "pg13"):
        await ctx.defer()
        selected_rating = rating.lower() if rating else "pg13"

        data = await fetch_tod_prompt(self.bot, "nhie", selected_rating)
        question = data.get("question", "No prompt received.")
        q_rating = data.get("rating", selected_rating).upper()

        embed = discord.Embed(
            title="🤫 Never Have I Ever",
            description=f"### {question}",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Rating: {q_rating}")
        view = TODView(self.bot, current_rating=selected_rating)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="wyr", description="Get a random 'Would You Rather' question.")
    @app_commands.describe(rating="Rating filter for the question")
    @app_commands.choices(rating=[
        app_commands.Choice(name="PG (Family friendly)", value="pg"),
        app_commands.Choice(name="PG-13 (Standard)", value="pg13"),
    ])
    async def wyr(self, ctx: commands.Context, rating: Optional[str] = "pg13"):
        await ctx.defer()
        selected_rating = rating.lower() if rating else "pg13"

        data = await fetch_tod_prompt(self.bot, "wyr", selected_rating)
        question = data.get("question", "No question received.")
        q_rating = data.get("rating", selected_rating).upper()

        embed = discord.Embed(
            title="⚖️ Would You Rather",
            description=f"### {question}",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Rating: {q_rating}")
        view = TODView(self.bot, current_rating=selected_rating)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="paranoia", description="Get a random Paranoia question.")
    @app_commands.describe(rating="Rating filter for the question")
    @app_commands.choices(rating=[
        app_commands.Choice(name="PG (Family friendly)", value="pg"),
        app_commands.Choice(name="PG-13 (Standard)", value="pg13"),
    ])
    async def paranoia(self, ctx: commands.Context, rating: Optional[str] = "pg13"):
        await ctx.defer()
        selected_rating = rating.lower() if rating else "pg13"

        data = await fetch_tod_prompt(self.bot, "paranoia", selected_rating)
        question = data.get("question", "No question received.")
        q_rating = data.get("rating", selected_rating).upper()

        embed = discord.Embed(
            title="👀 Paranoia Question",
            description=f"### {question}",
            color=discord.Color.dark_teal()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name} • Rating: {q_rating}")
        view = TODView(self.bot, current_rating=selected_rating)
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(TruthOrDare(bot))
