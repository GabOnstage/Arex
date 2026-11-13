from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from utils.userapps import user_app

log = logging.getLogger("arex.translate")

DEFAULT_TARGET = "en"
MAX_INPUT_CHARS = 5000
MAX_CHUNK_CHARS = 1800
MAX_EMBED_DESCRIPTION = 4096
MAX_ORIGINAL_PREVIEW = 900

TRANSLATE_ENDPOINTS = (
    "https://translate.googleapis.com/translate_a/single",
    "https://translate.google.com/translate_a/single",
)
USER_AGENT = "Mozilla/5.0 (compatible; Arexium/1.0; +https://discord.com)"

# Kept at 25 entries so the whole list fits in one Discord select menu.
LANGUAGES = [
    ("English", "en"),
    ("Spanish", "es"),
    ("French", "fr"),
    ("German", "de"),
    ("Portuguese", "pt"),
    ("Italian", "it"),
    ("Russian", "ru"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Chinese (Simplified)", "zh-cn"),
    ("Chinese (Traditional)", "zh-tw"),
    ("Arabic", "ar"),
    ("Hindi", "hi"),
    ("Turkish", "tr"),
    ("Dutch", "nl"),
    ("Polish", "pl"),
    ("Swedish", "sv"),
    ("Norwegian", "no"),
    ("Danish", "da"),
    ("Finnish", "fi"),
    ("Greek", "el"),
    ("Hebrew", "he"),
    ("Thai", "th"),
    ("Vietnamese", "vi"),
    ("Indonesian", "id"),
]

LANGUAGE_NAMES = {code: label for label, code in LANGUAGES}

# Codes Google Translate may return that are not in the menu above, plus
# normalisation for codes that changed over time (iw -> he, in -> id, ...).
EXTRA_LANGUAGE_NAMES = {
    "af": "Afrikaans",
    "am": "Amharic",
    "az": "Azerbaijani",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "bs": "Bosnian",
    "ca": "Catalan",
    "cs": "Czech",
    "cy": "Welsh",
    "eo": "Esperanto",
    "et": "Estonian",
    "eu": "Basque",
    "fa": "Persian",
    "fil": "Filipino",
    "ga": "Irish",
    "gl": "Galician",
    "gu": "Gujarati",
    "hr": "Croatian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "is": "Icelandic",
    "jv": "Javanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ky": "Kyrgyz",
    "la": "Latin",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "mr": "Marathi",
    "ms": "Malay",
    "my": "Burmese",
    "ne": "Nepali",
    "pa": "Punjabi",
    "ro": "Romanian",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sq": "Albanian",
    "sr": "Serbian",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "zu": "Zulu",
}

LANGUAGE_ALIASES = {
    "zh": "zh-cn",
    "zh-hans": "zh-cn",
    "zh-hant": "zh-tw",
    "pt-br": "pt",
    "pt-pt": "pt",
    "nb": "no",
    "nn": "no",
    "iw": "he",
    "in": "id",
    "tl": "fil",
    "jw": "jv",
}

# Only used for the prefix-command "to:<language>" directive.
_TO_DIRECTIVE_RE = re.compile(r"^to(?:[: ]+)([A-Za-z][\w-]*)\s*(.*)$", re.IGNORECASE | re.DOTALL)


class TranslationError(Exception):
    """Raised when the translation service cannot return a result."""


def _normalize_code(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    code = code.strip().lower().replace("_", "-")
    return LANGUAGE_ALIASES.get(code, code)


def _language_name(code: Optional[str]) -> str:
    normalized = _normalize_code(code)
    if not normalized:
        return "Unknown"
    return (
        LANGUAGE_NAMES.get(normalized)
        or EXTRA_LANGUAGE_NAMES.get(normalized)
        or normalized.upper()
    )


def _language_label(code: Optional[str]) -> str:
    normalized = _normalize_code(code)
    if not normalized:
        return "Unknown"
    return f"{_language_name(normalized)} (`{normalized}`)"


def _resolve_language(value: Optional[str]) -> Optional[str]:
    """Turn a code or human-readable language name into a menu code."""
    if not value:
        return None

    value = value.strip().lower()
    normalized = _normalize_code(value)
    if normalized in LANGUAGE_NAMES:
        return normalized

    lookup = {}
    for label, code in LANGUAGES:
        lookup[code] = code
        lookup[label.lower()] = code
        lookup[label.lower().replace(" (", " ").replace(")", "")] = code

    return lookup.get(value)


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _split_chunks(text: str, limit: int = MAX_CHUNK_CHARS):
    """Split text into API-sized chunks, preferring line/word boundaries."""
    if len(text) <= limit:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            split_at = text.rfind("\n", start, end)
            if split_at <= start:
                split_at = text.rfind(" ", start, end)
            if split_at > start:
                end = split_at + 1
        chunks.append(text[start:end])
        start = end
    return chunks


def _parse_primary_response(data):
    """Parse translate.googleapis.com's ``[[[translated, ...]], ...]`` shape."""
    if not isinstance(data, list) or not data:
        return None, None

    segments = data[0]
    if not isinstance(segments, list):
        return None, None

    pieces = [
        segment[0]
        for segment in segments
        if isinstance(segment, list)
        and segment
        and isinstance(segment[0], str)
    ]
    if not pieces:
        return None, None

    detected = data[2] if len(data) > 2 and isinstance(data[2], str) else None
    return "".join(pieces).strip(), detected


def _parse_fallback_response(data):
    """Parse the smaller ``[[translated, source]]`` shape some hosts return."""
    if isinstance(data, list):
        if data and isinstance(data[0], list) and data[0] and isinstance(data[0][0], str):
            first = data[0]
            detected = first[1] if len(first) > 1 and isinstance(first[1], str) else None
            return first[0].strip(), detected
        if data and isinstance(data[0], str):
            detected = data[1] if len(data) > 1 and isinstance(data[1], str) else None
            return data[0].strip(), detected
    return None, None


class TranslationLanguageSelect(discord.ui.Select):
    def __init__(self, view: "TranslationView"):
        options = [
            discord.SelectOption(
                label=label,
                value=code,
                default=(code == view.target),
            )
            for label, code in LANGUAGES
        ]
        super().__init__(
            placeholder="🌐 Translate into another language…",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        await self.view_ref.change_language(interaction, self.values[0])


class TranslationView(discord.ui.View):
    """Language picker attached to a translation result."""

    def __init__(
        self,
        cog: "Translate",
        author_id: int,
        original: str,
        source_lang: Optional[str],
        target: str,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.original = original
        self.source_lang = source_lang
        self.target = target
        self.message: Optional[discord.Message] = None
        self.add_item(TranslationLanguageSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the person who ran the command can switch languages.",
                ephemeral=True,
            )
            return False
        return True

    async def change_language(self, interaction: discord.Interaction, target: str):
        target = _resolve_language(target) or DEFAULT_TARGET
        if target == self.target:
            await interaction.response.defer()
            return

        await interaction.response.defer()
        try:
            translated, source = await self.cog.translate_text(self.original, target)
        except TranslationError as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
            return

        self.target = target
        self.source_lang = source or self.source_lang

        embed = self.cog.build_embed(self.original, translated, self.source_lang, target)
        new_view = TranslationView(
            self.cog,
            self.author_id,
            self.original,
            self.source_lang,
            target,
        )

        try:
            message = await interaction.message.edit(embed=embed, view=new_view)
        except discord.HTTPException as exc:
            log.warning("Could not edit translation message: %s", exc)
            return

        new_view.message = message
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Translate(commands.Cog):
    """Translate text or messages using Google Translate's public endpoint."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_menu = app_commands.ContextMenu(
            name="Translate Message",
            callback=self.translate_message_context,
            allowed_contexts=app_commands.AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            ),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
        )
        self.bot.tree.add_command(self.message_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.message_menu.name, type=self.message_menu.type)

    # -- Translation helpers -------------------------------------------------

    def _get_session(self):
        session = getattr(self.bot, "session", None)
        if session is not None and not session.closed:
            return session, False
        return aiohttp.ClientSession(), True

    async def _translate_chunk(self, session: aiohttp.ClientSession, text: str, target: str):
        payload = {
            "client": "gtx",
            "sl": "auto",
            "tl": target,
            "dt": "t",
            "q": text,
        }
        headers = {"User-Agent": USER_AGENT}
        timeout = aiohttp.ClientTimeout(total=20)
        last_error = "no response"

        for endpoint in TRANSLATE_ENDPOINTS:
            try:
                async with session.post(
                    endpoint,
                    data=payload,
                    headers=headers,
                    timeout=timeout,
                ) as response:
                    if response.status != 200:
                        last_error = f"HTTP {response.status}"
                        log.warning(
                            "Translate endpoint %s returned HTTP %s",
                            endpoint,
                            response.status,
                        )
                        continue
                    data = await response.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                last_error = str(exc)
                log.warning("Translate request to %s failed: %s", endpoint, exc)
                continue

            translated, detected = _parse_primary_response(data)
            if not translated:
                translated, fallback_detected = _parse_fallback_response(data)
                detected = detected or fallback_detected
            if translated:
                return translated, detected
            last_error = "empty translation response"

        log.error("All translation endpoints failed: %s", last_error)
        raise TranslationError(
            "The translation service is unavailable right now. Please try again in a moment."
        )

    async def translate_text(self, text: str, target: str = DEFAULT_TARGET):
        """Translate *text* and return ``(translated_text, detected_language)``."""
        text = (text or "").strip()
        if not text:
            raise TranslationError("There is no text to translate.")
        if len(text) > MAX_INPUT_CHARS:
            raise TranslationError(
                f"That text is too long (max {MAX_INPUT_CHARS} characters)."
            )

        session, close_session = self._get_session()
        detected = None
        pieces = []

        try:
            for chunk in _split_chunks(text):
                if not chunk.strip():
                    pieces.append(chunk)
                    continue

                leading = chunk[: len(chunk) - len(chunk.lstrip())]
                trailing = chunk[len(chunk.rstrip()) :]
                core = chunk.strip()

                translated, chunk_detected = await self._translate_chunk(
                    session, core, target
                )
                if detected is None and chunk_detected:
                    detected = chunk_detected
                pieces.append(f"{leading}{translated}{trailing}")
        finally:
            if close_session and not session.closed:
                await session.close()

        translated_text = "".join(pieces).strip()
        if not translated_text:
            raise TranslationError("The translation service returned an empty result.")
        return translated_text, detected

    # -- Rendering -----------------------------------------------------------

    def build_embed(
        self,
        original: str,
        translated: str,
        source_lang: Optional[str],
        target: str,
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🌐 Translation",
            color=discord.Color.blurple(),
            description=_truncate(translated, MAX_EMBED_DESCRIPTION),
        )
        embed.add_field(name="Detected language", value=_language_label(source_lang), inline=True)
        embed.add_field(name="Translated to", value=_language_label(target), inline=True)

        source_code = _normalize_code(source_lang)
        target_code = _normalize_code(target)
        if source_code and target_code and source_code == target_code:
            embed.add_field(
                name="Note",
                value=f"This text is already in {_language_name(target_code)}.",
                inline=False,
            )
        elif original and original.strip() != translated.strip():
            preview = _truncate(original.strip(), MAX_ORIGINAL_PREVIEW)
            preview = "\n".join(f"> {line}" for line in preview.splitlines())
            embed.add_field(
                name="Original",
                value=_truncate(preview, 1024),
                inline=False,
            )

        embed.set_footer(text="Use the menu below to translate into another language.")
        return embed

    def _extract_message_text(self, message: discord.Message) -> str:
        content = (message.content or "").strip()
        if content:
            return content

        for embed in message.embeds:
            parts = [embed.title, embed.description]
            for field in embed.fields:
                parts.extend([field.name, field.value])
            if embed.footer and embed.footer.text:
                parts.append(embed.footer.text)
            if embed.author and embed.author.name:
                parts.append(embed.author.name)

            text = "\n".join(part.strip() for part in parts if part and part.strip())
            if text:
                return text

        return ""

    # -- Context menu --------------------------------------------------------

    async def translate_message_context(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ):
        """Translate the message that was right-clicked via Apps > Translate Message."""
        text = self._extract_message_text(message)
        if not text:
            await interaction.response.send_message(
                "That message doesn't have any text to translate.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        try:
            translated, source = await self.translate_text(text, DEFAULT_TARGET)
        except TranslationError as exc:
            await interaction.followup.send(f"⚠️ {exc}", ephemeral=True)
            return

        embed = self.build_embed(text, translated, source, DEFAULT_TARGET)
        view = TranslationView(self, interaction.user.id, text, source, DEFAULT_TARGET)
        try:
            sent = await interaction.followup.send(embed=embed, view=view)
        except discord.HTTPException as exc:
            log.warning("Could not send translation: %s", exc)
            return
        view.message = sent

    # -- Commands ------------------------------------------------------------

    @commands.hybrid_command(
        name="translate",
        aliases=["tr"],
        description="Translate text or a replied-to message. Defaults to English.",
    )
    @user_app()
    @commands.cooldown(1, 3, commands.BucketType.user)
    @app_commands.describe(
        text="Text to translate. Leave empty when replying to a message with the prefix command.",
        target="Language to translate into. Defaults to English.",
    )
    @app_commands.choices(
        target=[app_commands.Choice(name=label, value=code) for label, code in LANGUAGES]
    )
    async def translate(
        self,
        ctx: commands.Context,
        *,
        text: Optional[str] = None,
        target: Optional[str] = None,
    ):
        # Slash commands pick the target from the option above. Prefix users can
        # use "to:<language>" (for example, "!translate to:fr Bonjour").
        if text:
            text = text.strip()

        if ctx.interaction is None and text:
            match = _TO_DIRECTIVE_RE.match(text)
            if match:
                directive_target = _resolve_language(match.group(1))
                if directive_target:
                    target = directive_target
                    text = match.group(2).strip()

        target_code = _resolve_language(target) if target else DEFAULT_TARGET
        if target and not target_code:
            await ctx.send(
                f"Unknown language `{target}`. Use a supported language code, "
                "or pick a language from the menu after translating.",
                ephemeral=True,
            )
            return

        target_code = target_code or DEFAULT_TARGET

        if not text:
            text = await self._text_from_reply(ctx)
            if not text:
                await ctx.send(
                    "Provide some text to translate, reply to a message with "
                    "`!translate`, or right-click a message and choose "
                    "**Translate Message**.",
                    ephemeral=True,
                )
                return

        await ctx.defer()
        try:
            translated, source = await self.translate_text(text, target_code)
        except TranslationError as exc:
            await ctx.send(f"⚠️ {exc}", ephemeral=True)
            return

        embed = self.build_embed(text, translated, source, target_code)
        view = TranslationView(self, ctx.author.id, text, source, target_code)
        sent = await ctx.send(embed=embed, view=view)
        view.message = sent

    async def _text_from_reply(self, ctx: commands.Context) -> Optional[str]:
        message = getattr(ctx, "message", None)
        reference = getattr(message, "reference", None)
        if reference is None or reference.message_id is None:
            return None

        try:
            replied = await ctx.channel.fetch_message(reference.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

        return self._extract_message_text(replied) or None


async def setup(bot: commands.Bot):
    await bot.add_cog(Translate(bot))
