"""Small, dependency-free word banks used by Wordle and Hangman.

The NYT API is the primary Wordle source; this list is only a fallback for
dates the API has not published yet (or when the request fails).  Everything is
lower-case and exactly five letters long.
"""

from __future__ import annotations

WORDLE_FALLBACK: tuple[str, ...] = (
    "about", "above", "abuse", "actor", "acute", "admit", "adopt", "adult",
    "after", "again", "agent", "agree", "ahead", "alarm", "album", "alert",
    "alike", "alive", "allow", "alone", "along", "alter", "among", "anger",
    "angle", "angry", "apart", "apple", "apply", "arena", "argue", "arise",
    "array", "aside", "asset", "audio", "audit", "avoid", "award", "aware",
    "badly", "baker", "bases", "basic", "beach", "began", "begin", "begun",
    "being", "below", "bench", "birth", "black", "blame", "blind", "block",
    "blood", "board", "boost", "booth", "bound", "brain", "brand", "bread",
    "break", "breed", "brief", "bring", "broad", "broke", "brown", "build",
    "built", "buyer", "cable", "calif", "carry", "catch", "cause", "chain",
    "chair", "chart", "chase", "cheap", "check", "chest", "chief", "child",
    "china", "chose", "civil", "claim", "class", "clean", "clear", "click",
    "clock", "close", "coach", "coast", "could", "count", "court", "cover",
    "craft", "crash", "cream", "crime", "cross", "crowd", "crown", "curve",
    "cycle", "daily", "dance", "dated", "dealt", "death", "debut", "delay",
    "depth", "doing", "doubt", "dozen", "draft", "drama", "drawn", "dream",
    "dress", "drill", "drink", "drive", "drove", "dying", "eager", "early",
    "earth", "eight", "elite", "empty", "enemy", "enjoy", "enter", "entry",
    "equal", "error", "event", "every", "exact", "exist", "extra", "faith",
    "false", "fault", "fiber", "field", "fifth", "fifty", "fight", "final",
    "first", "fixed", "flash", "fleet", "floor", "focus", "force", "forth",
    "forty", "forum", "found", "frame", "frank", "fraud", "fresh", "front",
    "fruit", "fully", "funny", "giant", "given", "glass", "globe", "going",
    "grace", "grade", "grand", "grant", "grass", "great", "green", "gross",
    "group", "grown", "guard", "guess", "guest", "guide", "happy", "harry",
    "heart", "heavy", "hence", "horse", "hotel", "house", "human", "ideal",
    "image", "index", "inner", "input", "issue", "japan", "jimmy", "joint",
    "jones", "judge", "known", "label", "large", "laser", "later", "laugh",
    "layer", "learn", "lease", "least", "leave", "legal", "level", "lewis",
    "light", "limit", "links", "lives", "local", "logic", "loose", "lower",
    "lucky", "lunch", "lying", "magic", "major", "maker", "march", "maria",
    "match", "maybe", "mayor", "meant", "media", "metal", "might", "minor",
    "minus", "mixed", "model", "money", "month", "moral", "motor", "mount",
    "mouse", "mouth", "movie", "music", "needs", "never", "newly", "night",
    "noise", "north", "noted", "novel", "nurse", "occur", "ocean", "offer",
    "often", "order", "other", "ought", "paint", "panel", "paper", "party",
    "peace", "peter", "phase", "phone", "photo", "piece", "pilot", "pitch",
    "place", "plain", "plane", "plant", "plate", "point", "pound", "power",
    "press", "price", "pride", "prime", "print", "prior", "prize", "proof",
    "proud", "prove", "quick", "quiet", "quite", "radio", "raise", "range",
    "rapid", "ratio", "reach", "ready", "realm", "refer", "right", "rival",
    "river", "robin", "roger", "roman", "rough", "round", "route", "royal",
    "rural", "scale", "scene", "scope", "score", "sense", "serve", "seven",
    "shall", "shape", "share", "sharp", "sheet", "shelf", "shell", "shift",
    "shirt", "shock", "shoot", "short", "shown", "sight", "since", "sixth",
    "sixty", "sized", "skill", "sleep", "slide", "small", "smart", "smile",
    "smith", "smoke", "solid", "solve", "sorry", "sound", "south", "space",
    "spare", "speak", "speed", "spend", "spent", "split", "spoke", "sport",
    "staff", "stage", "stake", "stand", "start", "state", "steam", "steel",
    "stick", "still", "stock", "stone", "stood", "store", "storm", "story",
    "strip", "stuck", "study", "stuff", "style", "sugar", "suite", "super",
    "sweet", "table", "taken", "taste", "taxes", "teach", "teeth", "terry",
    "texas", "thank", "theft", "their", "theme", "there", "these", "thick",
    "thing", "think", "third", "those", "three", "threw", "throw", "tight",
    "times", "tired", "title", "today", "topic", "total", "touch", "tough",
    "tower", "track", "trade", "train", "treat", "trend", "trial", "tried",
    "tries", "truck", "truly", "trust", "truth", "twice", "under", "undue",
    "union", "unity", "until", "upper", "upset", "urban", "usage", "usual",
    "valid", "value", "video", "virus", "visit", "vital", "voice", "waste",
    "watch", "water", "wheel", "where", "which", "while", "white", "whole",
    "whose", "woman", "women", "world", "worry", "worse", "worst", "worth",
    "would", "wound", "write", "wrong", "wrote", "yield", "young", "youth",
)


# (word, category) pairs for Hangman.  Kept free of spaces and punctuation.
HANGMAN_WORDS: tuple[tuple[str, str], ...] = (
    ("apple", "Food"), ("banana", "Food"), ("cherry", "Food"),
    ("guitar", "Music"), ("piano", "Music"), ("violin", "Music"),
    ("dragon", "Fantasy"), ("wizard", "Fantasy"), ("castle", "Places"),
    ("planet", "Space"), ("galaxy", "Space"), ("comet", "Space"),
    ("rocket", "Space"), ("saturn", "Space"), ("jupiter", "Space"),
    ("python", "Programming"), ("coding", "Programming"),
    ("folder", "Computing"), ("laptop", "Computing"),
    ("keyboard", "Computing"), ("monitor", "Computing"),
    ("elephant", "Animals"), ("giraffe", "Animals"), ("penguin", "Animals"),
    ("dolphin", "Animals"), ("cheetah", "Animals"), ("octopus", "Animals"),
    ("kangaroo", "Animals"), ("butterfly", "Animals"),
    ("volcano", "Nature"), ("mountain", "Nature"), ("rainbow", "Nature"),
    ("thunder", "Nature"), ("forest", "Nature"), ("desert", "Nature"),
    ("island", "Nature"), ("glacier", "Nature"),
    ("pizza", "Food"), ("burger", "Food"), ("cookie", "Food"),
    ("chocolate", "Food"), ("pancake", "Food"), ("sandwich", "Food"),
    ("football", "Sports"), ("baseball", "Sports"), ("soccer", "Sports"),
    ("tennis", "Sports"), ("basketball", "Sports"), ("swimming", "Sports"),
    ("hockey", "Sports"), ("cycling", "Sports"),
    ("pirate", "Adventure"), ("treasure", "Adventure"),
    ("journey", "Adventure"), ("mystery", "Adventure"),
    ("detective", "Adventure"), ("compass", "Adventure"),
    ("library", "Places"), ("museum", "Places"), ("hospital", "Places"),
    ("airport", "Places"), ("harbor", "Places"), ("village", "Places"),
    ("bridge", "Places"), ("temple", "Places"),
    ("winter", "Seasons"), ("summer", "Seasons"), ("autumn", "Seasons"),
    ("festival", "Celebration"), ("birthday", "Celebration"),
    ("holiday", "Celebration"), ("fireworks", "Celebration"),
    ("painting", "Art"), ("sculpture", "Art"), ("theater", "Art"),
    ("orchestra", "Music"), ("melody", "Music"), ("harmony", "Music"),
    ("whisper", "Words"), ("courage", "Words"), ("freedom", "Words"),
    ("balance", "Words"), ("fortune", "Words"), ("gravity", "Science"),
    ("molecule", "Science"), ("electric", "Science"), ("magnet", "Science"),
    ("telescope", "Science"), ("microscope", "Science"),
    ("notebook", "Objects"), ("umbrella", "Objects"), ("backpack", "Objects"),
    ("camera", "Objects"), ("lantern", "Objects"), ("treasure", "Objects"),
    ("candle", "Objects"), ("mirror", "Objects"),
)


def hangman_pool(difficulty: str) -> tuple[tuple[str, str], ...]:
    """Return words matching ``easy``, ``medium`` or ``hard``."""

    difficulty = (difficulty or "medium").lower()
    if difficulty == "easy":
        return tuple(item for item in HANGMAN_WORDS if 4 <= len(item[0]) <= 6)
    if difficulty == "hard":
        return tuple(item for item in HANGMAN_WORDS if len(item[0]) >= 9)
    return tuple(item for item in HANGMAN_WORDS if 7 <= len(item[0]) <= 8)
