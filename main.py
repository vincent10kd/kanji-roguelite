import os
import random
import sqlite3
from dataclasses import dataclass
from textual.app import App, ComposeResult
from textual.widgets import Static, Input, Footer
from textual.containers import Vertical
from textual.reactive import reactive
import romkan
import jaconv

try:
    from fugashi import Tagger

    tagger = Tagger()
    FUGASHI_AVAILABLE = True
except ImportError:
    FUGASHI_AVAILABLE = False
    print("Warning: fugashi not available. Install with: pip install fugashi unidic-lite")

# -----------------------------
# Utility: visual bars
# -----------------------------
def bar(current, maximum, width=16, color="green"):
    if maximum <= 0:
        return ""
    filled = int(width * current / maximum)
    empty = width - filled
    return f"[{color}]" + "█" * filled + "[/]" + "░" * empty

# -----------------------------
# Frequency list loader
# -----------------------------
def load_frequency_list(freq_path=None):
    """
    Load word frequency data from a file to assign realistic tiers.

    Expected format: CSV/TSV with columns: word, frequency (or rank)
    Example:
        する,100000
        ある,95000
        ...

    Returns dict mapping word -> frequency score
    """
    if not freq_path or not os.path.exists(freq_path):
        print("No frequency list provided - using length-based tiers")
        return {}

    print(f"Loading frequency list from {freq_path}...")

    freq_dict = {}
    try:
        with open(freq_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                # Try comma or tab separator
                parts = line.split(',') if ',' in line else line.split('\t')
                if len(parts) >= 2:
                    word = parts[0].strip()
                    try:
                        freq = float(parts[1].strip())
                        freq_dict[word] = freq
                    except ValueError:
                        continue

        print(f"Loaded {len(freq_dict)} word frequencies")
        return freq_dict

    except Exception as e:
        print(f"Could not load frequency list: {e}")
        return {}


def assign_tier_from_frequency(word, freq_dict):
    """
    Assign tier based on real-world frequency data.

    Tier 1: Very common (top 2000 words)
    Tier 2: Common (2001-5000)
    Tier 3: Uncommon (5001+)
    """
    if word not in freq_dict:
        # Fallback to length-based if not in frequency list
        if len(word) <= 2:
            return 1
        elif len(word) == 3:
            return 2
        else:
            return 3

    freq = freq_dict[word]

    # Adjust these thresholds based on your frequency list format
    # If using rank (1, 2, 3...), lower numbers = more common
    # If using frequency count, higher numbers = more common

    # Assuming frequency count (higher = more common)
    if freq >= 1000:  # Very common
        return 1
    elif freq >= 100:  # Common
        return 2
    else:  # Uncommon
        return 3


# -----------------------------
# Japanese utilities
# -----------------------------
def romaji_to_hiragana(romaji):
    try:
        hira = romkan.to_hiragana(romaji)
        return jaconv.normalize(jaconv.kata2hira(hira))
    except Exception:
        return ""


def contains_kanji(word):
    return any("\u4e00" <= c <= "\u9fff" for c in word)


def is_japanese_word(word):
    return any("\u4e00" <= c <= "\u9fff" for c in word) or any("\u3040" <= c <= "\u309f" for c in word)


def get_readings(word):
    """Get readings using fugashi/MeCab"""
    if not FUGASHI_AVAILABLE:
        return []
    readings = set()
    try:
        for token in tagger(word):
            if token.feature.kana:
                readings.add(jaconv.normalize(jaconv.kata2hira(token.feature.kana)))
    except Exception:
        pass
    return list(readings)


# -----------------------------
# JMdict dictionary loader (for meanings)
# -----------------------------
def load_jmdict_dictionary(jmdict_path):
    """Load JMdict as a lookup dictionary for meanings"""
    if not os.path.exists(jmdict_path):
        print(f"JMdict file not found at {jmdict_path}")
        return {}

    print(f"Loading JMdict dictionary from {jmdict_path}...")

    try:
        conn = sqlite3.connect(jmdict_path)
        cur = conn.cursor()

        # Try to detect structure
        tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if not tables:
            conn.close()
            return {}

        table_name = tables[0][0]
        cols_info = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
        cols = [c[1] for c in cols_info]

        # Detect columns
        word_col = next((c for c in cols if c.lower() in ("surface", "word", "term")), cols[0])
        meaning_col = next(
            (c for c in cols if c.lower() in ("meaning", "meanings", "definition", "definitions", "gloss")), None)

        if not meaning_col:
            print("No meaning column found in JMdict")
            conn.close()
            return {}

        # Build lookup dictionary
        sql = f"SELECT {word_col}, {meaning_col} FROM {table_name}"
        cur.execute(sql)

        meaning_dict = {}
        for row in cur.fetchall():
            word, meaning = row
            if word and meaning:
                meaning_dict[word.strip()] = meaning.strip()

        conn.close()
        print(f"Loaded {len(meaning_dict)} meanings from JMdict")
        return meaning_dict

    except Exception as e:
        print(f"Could not load JMdict for meanings: {e}")
        return {}


# -----------------------------
# Vocab loaders
# -----------------------------

def load_kindle_vocab(kindle_path, jmdict_path, freq_dict=None):
    """Load from Kindle vocab.db using fugashi for readings and JMdict for meanings"""

    if not FUGASHI_AVAILABLE:
        raise RuntimeError("fugashi is required for Kindle vocab.db. Install with: pip install fugashi unidic-lite")

    print(f"\nLoading Kindle vocab from {kindle_path}...")

    conn = sqlite3.connect(kindle_path)
    cur = conn.cursor()

    cur.execute("""
        SELECT DISTINCT word
        FROM WORDS
        WHERE lang='ja'
    """)

    # Filter: only words with kanji, and max 3 characters for common everyday words
    # Most common Japanese words are 1-3 characters
    words = [w for (w,) in cur.fetchall() if contains_kanji(w) and len(w) <= 3]
    conn.close()

    # Load JMdict for meanings
    meaning_dict = load_jmdict_dictionary(jmdict_path)

    vocab = []
    tier_buckets = {1: [], 2: [], 3: []}

    print(f"Processing {len(words)} words with fugashi...")

    for w in words:
        readings = get_readings(w)
        if readings:
            # Try to get meaning from JMdict
            meaning = meaning_dict.get(w, "No meaning available")

            # Assign tier based on frequency list if available
            if freq_dict:
                tier = assign_tier_from_frequency(w, freq_dict)
            else:
                # Fallback to length-based tiers
                if len(w) == 1:
                    tier = 1  # Single kanji - easiest and most common
                elif len(w) == 2:
                    tier = 1  # Two kanji - still very common
                else:  # len(w) == 3
                    tier = 2  # Three kanji - less common

            entry = (w, readings, meaning, tier)
            vocab.append(entry)
            tier_buckets[tier].append(entry)

    print(f"Successfully loaded {len(vocab)} words with readings")
    if vocab:
        print(f"\nSample entries:")
        for i in range(min(5, len(vocab))):
            word, readings, meaning, tier = vocab[i]
            meaning_short = meaning[:60] + "..." if len(meaning) > 60 else meaning
            print(f"  {word} → {readings[0]} | {meaning_short}")

    return vocab, tier_buckets


def load_jmdict_only(jmdict_path, freq_dict=None):
    """Load from JMdict database only"""

    print(f"\nLoading JMdict vocab from {jmdict_path}...")

    if not os.path.exists(jmdict_path):
        raise FileNotFoundError(f"JMdict file not found: {jmdict_path}")

    conn = sqlite3.connect(jmdict_path)
    cur = conn.cursor()

    # Get table name
    tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    if not tables:
        raise RuntimeError("No tables found in JMdict DB")

    table_name = tables[0][0]

    # Get columns
    cols_info = cur.execute(f"PRAGMA table_info({table_name})").fetchall()
    cols = [c[1] for c in cols_info]

    # Detect columns
    word_col = next((c for c in cols if c.lower() in ("surface", "word", "term")), cols[0])
    reading_col = next((c for c in cols if c.lower() in ("reading", "kana")), None)
    meaning_col = next((c for c in cols if c.lower() in ("meaning", "meanings", "definition", "definitions", "gloss")),
                       None)
    freq_col = next((c for c in cols if c.lower() in ("frequency", "freq")), None)
    freq_score_col = next((c for c in cols if c.lower() == "frequency_score"), None)

    print(
        f"Detected columns: word={word_col}, reading={reading_col}, meaning={meaning_col}, freq={freq_col}, freq_score={freq_score_col}")

    # Build SQL - select only what exists
    select_cols = [word_col]

    if reading_col:
        select_cols.append(reading_col)
    else:
        select_cols.append("NULL as reading")

    if meaning_col:
        select_cols.append(meaning_col)
    else:
        select_cols.append("'Meaning not found' as meaning")

    if freq_score_col:
        select_cols.append(freq_score_col)
    elif freq_col:
        select_cols.append(freq_col)
    else:
        select_cols.append("3.0 as frequency")

    sql = f"SELECT {', '.join(select_cols)} FROM {table_name}"
    cur.execute(sql)

    vocab = []
    tier_buckets = {1: [], 2: [], 3: []}
    skipped = 0

    for row in cur.fetchall():
        word = row[0]
        if not word or not is_japanese_word(word):
            skipped += 1
            continue

        # Skip very long words - focus on common everyday vocabulary (max 3 chars)
        if len(word) > 3:
            skipped += 1
            continue

        # Get reading (index 1)
        reading_raw = row[1]
        if reading_raw and isinstance(reading_raw, str) and reading_raw.strip():
            # Normalize to hiragana
            reading = [jaconv.kata2hira(reading_raw.strip())]
        else:
            # Skip if no reading
            skipped += 1
            continue

        # Get meaning (index 2)
        meaning = row[2] if len(row) > 2 and row[2] else "Meaning not found"

        # Get frequency (index 3) - could be frequency_score or old frequency
        freq = row[3] if len(row) > 3 and row[3] else 3.0

        # Assign tier based on external frequency list if available
        if freq_dict:
            tier = assign_tier_from_frequency(word, freq_dict)
        elif freq_score_col:
            # Using frequency_score (lower = more common)
            # Adjust thresholds based on your data
            try:
                score = float(freq)
            except:
                score = 5000.0

            # Thresholds for frequency_score (sum of kanji ranks)
            # Single kanji: ~100-2000
            # Two kanji: ~200-4000
            # Three kanji: ~300-6000
            if score <= 800:  # Very common words
                tier = 1
            elif score <= 2500:  # Common words
                tier = 2
            else:  # Less common words
                tier = 3
        else:
            # Fallback to JMdict frequency + length
            try:
                freq_val = float(freq)
            except:
                freq_val = 3.0

            # Combine frequency and length for better common word detection
            if len(word) == 1:
                tier = 1  # Single character words are almost always common
            elif len(word) == 2:
                # 2-char words use frequency
                if freq_val >= 4.0:
                    tier = 1
                elif freq_val >= 2.5:
                    tier = 1  # Still tier 1, very common
                else:
                    tier = 2
            else:  # len(word) == 3
                # 3-char words are less common
                if freq_val >= 4.5:
                    tier = 1
                elif freq_val >= 3.0:
                    tier = 2
                else:
                    tier = 3

        entry = (word, reading, meaning, tier)
        vocab.append(entry)
        tier_buckets[tier].append(entry)

    conn.close()

    print(f"Loaded {len(vocab)} words from JMdict (skipped {skipped})")
    if vocab:
        print(f"\nSample entries:")
        for i in range(min(5, len(vocab))):
            word, readings, meaning, tier = vocab[i]
            meaning_short = meaning[:60] + "..." if len(meaning) > 60 else meaning
            print(f"  {word} → {readings[0]} | {meaning_short}")

    return vocab, tier_buckets


# -----------------------------
# Leveling system
# -----------------------------
def xp_for_level(level):
    """Calculate XP needed for a given level (exponential growth)"""
    return int(50 * (1.5 ** (level - 1)))


def get_level_from_xp(xp):
    """Determine current level based on total XP"""
    level = 1
    total_xp_needed = 0
    while True:
        xp_needed = xp_for_level(level)
        if total_xp_needed + xp_needed > xp:
            break
        total_xp_needed += xp_needed
        level += 1
    return level, total_xp_needed


def max_tier_for_level(level):
    """Determine maximum tier unlocked at a given level"""
    if level >= 5:
        return 3  # All tiers unlocked
    elif level >= 3:
        return 2  # Tiers 1 and 2
    else:
        return 1  # Only tier 1


# -----------------------------
# Game models
# -----------------------------
@dataclass
class Player:
    x: int
    y: int
    hp: int = 30  # Increased from 20
    max_hp: int = 30  # Increased from 20
    xp: int = 0
    streak: int = 0
    level: int = 1


@dataclass
class Enemy:
    hp: int
    dmg: int
    xp: int
    tier: int
    words: list  # list of (surface, readings, meanings, tier)

    def next_word(self):
        if not self.words:
            return ("ERROR", ["えらー"], "No meaning available", 1)
        return random.choice(self.words)


# -----------------------------
# Map generation
# -----------------------------
def generate_map(w=40, h=18):
    grid = [["#" for _ in range(w)] for _ in range(h)]
    x, y = w // 2, h // 2
    # Carve random paths
    for _ in range(w * h * 3):
        grid[y][x] = "."
        dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        x = max(1, min(w - 2, x + dx))
        y = max(1, min(h - 2, y + dy))
    # Place enemies
    for _ in range(8):
        ex, ey = random.randrange(w), random.randrange(h)
        if grid[ey][ex] == ".":
            grid[ey][ex] = "E"
    # Place healing items
    for _ in range(5):
        ix, iy = random.randrange(w), random.randrange(h)
        if grid[iy][ix] == ".":
            grid[iy][ix] = "!"
    return grid


# -----------------------------
# Enemy creation
# -----------------------------
def create_enemy(tier_buckets, player_level):
    """Create enemy with tiers limited by player level"""
    max_tier = max_tier_for_level(player_level)

    # Weight tiers based on what's unlocked - heavily favor tier 1 (common words)
    if max_tier == 1:
        tier = 1
    elif max_tier == 2:
        tier = random.choices([1, 2], weights=[0.85, 0.15])[0]  # 85% tier 1, 15% tier 2
    else:
        tier = random.choices([1, 2, 3], weights=[0.75, 0.20, 0.05])[0]  # Mostly tier 1

    words = tier_buckets.get(tier, [])
    if not words:
        # Fallback to any available tier
        for t in range(max_tier, 0, -1):
            if tier_buckets.get(t):
                words = tier_buckets[t]
                tier = t
                break
        if not words:
            words = sum(tier_buckets.values(), [])

    if not words:
        raise RuntimeError("No words available to create enemy!")

    # Give a large pool to each enemy to avoid early repetition
    if len(words) > 25:
        words = random.sample(words, 25)

    # Reduced HP and damage for easier game
    hp = 2 + tier * 3  # Tier 1=5HP, Tier 2=8HP, Tier 3=11HP
    dmg = 1 + tier * 2  # Tier 1=3dmg, Tier 2=5dmg, Tier 3=7dmg (increased from 2/3/4)
    xp = 10 * tier
    return Enemy(hp=hp, dmg=dmg, xp=xp, tier=tier, words=words)


# -----------------------------
# Main Game App
# -----------------------------
class KanjiRoguelite(App):
    CSS = "Screen { align: center middle; }"
    mode = reactive("overworld")
    current_word = reactive("")
    current_readings = reactive([])
    current_meaning = reactive("")
    current_kana = reactive("")

    def __init__(self, vocab, tier_buckets):
        super().__init__()
        self.vocab = vocab
        self.tier_buckets = tier_buckets
        self.player = None  # Will be created in on_mount

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", id="map")
            yield Static("", id="kana")
            yield Static("", id="feedback")
            yield Static("", id="stats")
            yield Input(placeholder="Type romaji…", id="input")
            yield Footer()

    def on_mount(self):
        # Create player once at the start - BEFORE showing intro
        if self.player is None:
            self.player = Player(20, 9)
        self.show_intro()

    # -------------------------
    # Intro Screen
    # -------------------------
    def show_intro(self):
        self.mode = "intro"
        intro_text = """


┏━━━━━━━━━━━━━━━━━━━━━━┓
┃      漢 字 修 行      ┃
┗━━━━━━━━━━━━━━━━━━━━━━┛

    KANJI ROGUELITE
    by V. ten Cate, 2026

    Practice your Japanese vocabulary
    through dungeon exploration!

    • Level up to unlock harder words
    • Defeat enemies with correct readings
    • Explore procedurally generated maps


    Press ENTER to begin...


"""
        self.query_one("#map", Static).update(intro_text)
        self.query_one("#kana", Static).update("")
        self.query_one("#feedback", Static).update("")
        self.query_one("#stats", Static).update("")
        self.query_one(Input).display = False  # Hide input on intro screen

    # -------------------------
    # Map & Movement
    # -------------------------
    def new_map(self):
        self.map = generate_map()
        # Keep player stats, only reset position
        self.player.x = 20
        self.player.y = 9
        self.refresh_overworld()
        self.update_stats()  # Ensure stats are displayed on new map

    def enemies_remaining(self):
        return any("E" in row for row in self.map)

    def refresh_overworld(self):
        self.mode = "overworld"
        out = ""
        for y, row in enumerate(self.map):
            for x, ch in enumerate(row):
                out += "@" if (x, y) == (self.player.x, self.player.y) else ch
            out += "\n"
        self.query_one("#map", Static).update(out)
        self.query_one("#kana", Static).update("")
        self.query_one("#feedback", Static).update("")
        self.update_stats()

    def update_stats(self):
        # Safety check - don't update if player doesn't exist yet
        if self.player is None:
            return

        # Calculate level and XP progress
        level, xp_for_current_level = get_level_from_xp(self.player.xp)
        xp_needed_for_next = xp_for_level(level)
        xp_progress = self.player.xp - xp_for_current_level
        max_tier = max_tier_for_level(level)

        self.query_one("#stats", Static).update(
            f"HP {self.player.hp}/{self.player.max_hp} | "
            f"Level {level} | "
            f"XP {xp_progress}/{xp_needed_for_next} | "
            f"Streak {self.player.streak} | "
            f"Max Tier: {max_tier}"
        )

    def on_key(self, event):
        if event.key == "escape":
            self.exit()

        # Intro screen - press enter to start
        if self.mode == "intro" and event.key == "enter":
            self.query_one(Input).display = True  # Show input again
            self.new_map()
            return

        if self.mode == "overworld":
            self.move(event.key)
        elif self.mode == "feedback" and event.key in ("enter", "space"):
            inp = self.query_one(Input)
            inp.disabled = False
            inp.focus()
            self.query_one("#feedback", Static).update("")
            if self.enemy and self.enemy.hp > 0:
                next_word = self.enemy.next_word()
                self.set_battle_word(next_word)
                self.mode = "battle"
            else:
                self.enemy = None
                if not self.enemies_remaining():
                    self.new_map()
                else:
                    self.refresh_overworld()
                self.mode = "overworld"

    def move(self, key):
        moves = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
        if key not in moves:
            return
        dx, dy = moves[key]
        nx, ny = self.player.x + dx, self.player.y + dy
        if nx < 0 or nx >= len(self.map[0]) or ny < 0 or ny >= len(self.map):
            return
        tile = self.map[ny][nx]
        if tile == "#":
            return
        if tile == "!":
            self.player.hp = min(self.player.max_hp, self.player.hp + 10)
            self.map[ny][nx] = "."
            self.update_stats()  # Update stats after healing
        if tile == "E":
            self.map[ny][nx] = "."
            self.start_battle()
            return
        self.player.x, self.player.y = nx, ny
        self.refresh_overworld()

    # -------------------------
    # Battle
    # -------------------------
    def start_battle(self):
        self.mode = "battle"
        self.player.streak = 0
        level, _ = get_level_from_xp(self.player.xp)
        self.enemy = create_enemy(self.tier_buckets, level)
        self.set_battle_word(self.enemy.next_word())

    def set_battle_word(self, word_entry):
        self.current_word, self.current_readings, self.current_meaning, _ = word_entry
        self.current_kana = ""
        self.query_one("#map", Static).update(f"\n\n   {self.current_word}   \n\nE HP: {self.enemy.hp}")
        self.query_one("#kana", Static).update("→ ")
        self.query_one("#feedback", Static).update("")
        inp = self.query_one(Input)
        inp.value = ""
        inp.focus()

    def on_input_changed(self, event):
        if self.mode != "battle":
            return
        self.current_kana = romaji_to_hiragana(event.value)
        self.query_one("#kana", Static).update(f"→ {self.current_kana}")

    def on_input_submitted(self, event):
        if self.mode != "battle":
            return

        # Normalize input to hiragana
        user_input = jaconv.kata2hira(self.current_kana.strip())

        # Normalize all correct readings to hiragana
        correct_readings_normalized = [jaconv.kata2hira(r.strip()) for r in self.current_readings]

        # Get display values
        correct_reading = self.current_readings[0] if self.current_readings else self.current_word
        meaning = self.current_meaning if self.current_meaning else "Meaning not found"

        # Check if correct
        is_correct = user_input in correct_readings_normalized

        # Store old level to detect level up
        old_level, _ = get_level_from_xp(self.player.xp)

        if is_correct:
            dmg = 2 + self.player.streak  # Base damage increased from 1 to 2
            self.enemy.hp -= dmg
            self.player.streak += 1
            feedback_text = f"✓ Correct! Meaning: {meaning}"
            # Remove the word from enemy rotation to avoid repetition
            self.enemy.words = [w for w in self.enemy.words
                                if not (w[0] == self.current_word and
                                        w[1] == self.current_readings and
                                        w[2] == self.current_meaning)]
        else:
            self.player.hp -= self.enemy.dmg
            self.player.streak = 0
            feedback_text = f"✗ Wrong! Correct: {correct_reading} | Meaning: {meaning}"

        self.update_stats()
        self.query_one("#feedback", Static).update(feedback_text)
        self.query_one(Input).disabled = True
        self.mode = "feedback"

        if self.player.hp <= 0:
            self.game_over()
            return

        # Enemy defeated
        if self.enemy.hp <= 0:
            self.player.xp += self.enemy.xp
            new_level, _ = get_level_from_xp(self.player.xp)

            # Check for level up
            level_up_text = ""
            if new_level > old_level:
                level_up_text = f"\n🎉 LEVEL UP! Now level {new_level}! Max tier: {max_tier_for_level(new_level)}"

            self.update_stats()
            # Show meaning in the victory message
            self.query_one("#feedback", Static).update(
                f"✓ Correct! Meaning: {meaning}\n"
                f"Enemy defeated! XP +{self.enemy.xp}{level_up_text}\n"
                f"[Press Enter/Space]"
            )

    def game_over(self):
        self.mode = "gameover"
        level, _ = get_level_from_xp(self.player.xp)
        self.query_one("#map", Static).update(
            f"\n💀 GAME OVER 💀\n\nLevel: {level}\nXP: {self.player.xp}\n\nPress Esc to quit"
        )
        self.query_one(Input).display = False
        self.query_one("#kana", Static).update("")
        self.query_one("#feedback").update("")


# -----------------------------
# Entry point
# -----------------------------
def main():
    print("=" * 60)
    print("KANJI ROGUELITE - Vocab Loader")
    print("=" * 60)

    # Ask if user has Kindle vocab.db
    use_kindle = input("\nDo you have a Kindle vocab.db file? (y/n, default=n): ").strip().lower()

    # Ask for frequency list (optional)
    use_freq = input("Do you have a word frequency list? (y/n, default=n): ").strip().lower()
    freq_dict = {}
    if use_freq == 'y':
        freq_path = input("Path to frequency list CSV/TSV (word,frequency): ").strip()
        freq_dict = load_frequency_list(freq_path)

    try:
        if use_kindle == 'y':
            # Use Kindle vocab with JMdict meanings
            kindle_path = input("Path to Kindle vocab.db (leave empty for 'vocab.db'): ").strip()
            if not kindle_path:
                kindle_path = "vocab.db"

            jmdict_path = input("Path to JMdict database (leave empty for 'jmdict.sqlite'): ").strip()
            if not jmdict_path:
                jmdict_path = "jmdict.sqlite"

            vocab, tier_buckets = load_kindle_vocab(kindle_path, jmdict_path, freq_dict)
        else:
            # Use JMdict only
            jmdict_path = input("Path to JMdict database (leave empty for 'jmdict.sqlite'): ").strip()
            if not jmdict_path:
                jmdict_path = "jmdict.sqlite"

            vocab, tier_buckets = load_jmdict_only(jmdict_path, freq_dict)

        print(f"\n{'=' * 60}")
        print(f"Successfully loaded {len(vocab)} words.")
        print(f"Tier 1: {len(tier_buckets[1])} words")
        print(f"Tier 2: {len(tier_buckets[2])} words")
        print(f"Tier 3: {len(tier_buckets[3])} words")
        print(f"{'=' * 60}\n")
        print("Leveling system:")
        print("  Level 1-2: Only Tier 1 words")
        print("  Level 3-4: Tier 1-2 words")
        print("  Level 5+: All tiers unlocked")
        print(f"{'=' * 60}\n")

        if len(vocab) == 0:
            print("ERROR: No words loaded! Check your database.")
            return

        input("Press Enter to start the game...")
        KanjiRoguelite(vocab, tier_buckets).run()

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
