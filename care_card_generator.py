#!/usr/bin/env python3
"""
Leaf & Vessel Care Card Generator
==================================

A macOS desktop application for generating professional 4x6 inch plant care cards.

INSTALLATION:
-------------
1. Install dependencies:
   pip install -r requirements.txt

2. Set up your Anthropic API key:
   - Get your API key from: https://console.anthropic.com/
   - Replace the placeholder below with your actual key

3. Add the logo file:
   - Place 'Small Version.png' in the same directory as this script
   - Logo should be approximately 1"x1" (will be auto-scaled)

4. Run the application:
   python care_card_generator.py

CSV IMPORT FORMAT:
------------------
Your CSV file should have these columns (with header row):
- scientific_name (required)
- common_name
- light
- water
- feeding
- temperature
- humidity
- toxicity

Example:
scientific_name,common_name,light,water,feeding,temperature,humidity,toxicity
"Monstera deliciosa","Swiss Cheese Plant","Bright indirect","When top 2 inches dry","Monthly spring-fall","65-80°F","40-60%","Toxic to cats and dogs"

TESTING CHECKLIST:
------------------
[ ] Database creation and schema initialization
[ ] CSV import with sample data
[ ] API call with valid plant name (e.g., "Monstera deliciosa")
[ ] API call with invalid plant name (e.g., "Fake plantus nonexistus")
[ ] Network error handling (disconnect internet and try)
[ ] PDF generation and file organization in cards/
[ ] GUI interactions (generate button, history click)
[ ] Duplicate plant handling (try adding same plant twice)
[ ] Logo placement on PDF
[ ] API rate limiting (429 errors)
"""

import sqlite3
import json
import logging
import os
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

import customtkinter as ctk
from tkinter import filedialog, messagebox
from reportlab.lib.pagesizes import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image
import anthropic
from pypdf import PdfWriter, PdfReader

# ============================================================================
# CONFIGURATION
# ============================================================================

# Config file for API key storage
CONFIG_FILE = "config.json"

def load_api_key() -> str:
    """Load API key from config file, environment variable, or prompt user."""
    # First, check environment variable (allows override)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return api_key

    # Second, check config file
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                api_key = config.get("anthropic_api_key")
                if api_key:
                    return api_key
        except (json.JSONDecodeError, IOError):
            pass  # Config file invalid, will prompt user

    # Third, prompt user for API key
    api_key = prompt_for_api_key()
    if api_key:
        save_api_key(api_key)
        return api_key

    raise ValueError("API key is required to run this application.")

def prompt_for_api_key() -> Optional[str]:
    """Show a dialog to prompt user for their API key."""
    import tkinter as tk
    from tkinter import simpledialog

    # Create a temporary root window (hidden)
    root = tk.Tk()
    root.withdraw()

    # Show input dialog
    api_key = simpledialog.askstring(
        "API Key Required",
        "Enter your Anthropic API key:\n\n"
        "Get your key from: https://console.anthropic.com/\n"
        "The key will be saved locally in config.json",
        parent=root
    )

    root.destroy()
    return api_key.strip() if api_key else None

def save_api_key(api_key: str) -> None:
    """Save API key to config file."""
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    config["anthropic_api_key"] = api_key
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

# Load API key (will prompt on first run)
ANTHROPIC_API_KEY = load_api_key()

# Model Configuration
CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1024
TEMPERATURE = 0.3
API_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds (will use exponential backoff)

# File Paths
DATABASE_PATH = "plants.db"
LOGO_PATH = "Small Version.png"
CARD_BACK_PATH = "Card_Back.pdf"
CARDS_DIR = "cards"
LOG_FILE = "app.log"

# PDF Configuration (6x4 inches landscape at 72 DPI)
PDF_WIDTH = 6 * inch  # 432 points
PDF_HEIGHT = 4 * inch  # 288 points
PDF_MARGIN = 0.25 * inch  # 18 points
LOGO_SIZE = 1 * inch  # 72 points

# Field Length Limits (characters) - prevents text overflow on cards
FIELD_LIMITS = {
    'description': 250,    # 2-3 sentences of plant description
    'light': 180,          # 1-2 sentences of light requirements
    'water': 180,          # 1-2 sentences of watering guidance
    'feeding': 180,        # 1-2 sentences of fertilizer guidance
    'temperature': 120,    # Temperature range and notes
    'humidity': 120,       # Humidity preferences
    'toxicity': 150        # Toxicity information
}

# GUI Configuration
WINDOW_WIDTH = 1050
WINDOW_HEIGHT = 600
WINDOW_TITLE = "Leaf & Vessel Care Card Generator"

# Color Configuration
PRIMARY_COLOR = "#2E7D32"  # Green
SECONDARY_COLOR = "#4CAF50"  # Light green
ERROR_COLOR = "#D32F2F"  # Red
SUCCESS_COLOR = "#388E3C"  # Dark green
TEXT_COLOR = "#333333"
FOOTER_COLOR = "#666666"
CHAT_USER_COLOR = "#1565C0"  # Blue for user messages
CHAT_ASSISTANT_COLOR = "#2E7D32"  # Green for assistant messages

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def truncate_text(text: str, max_length: int) -> str:
    """
    Intelligently truncate text to fit within max_length.
    Tries to break at sentence or word boundaries when possible.

    Args:
        text: Text to truncate
        max_length: Maximum character length

    Returns:
        Truncated text with ellipsis if shortened
    """
    if not text or len(text) <= max_length:
        return text

    # Try to truncate at sentence boundary (., !, ?)
    truncate_at = max_length - 3  # Leave room for "..."

    # Look for sentence endings within the limit
    for delimiter in ['. ', '! ', '? ']:
        last_sentence = text[:truncate_at].rfind(delimiter)
        if last_sentence > max_length * 0.6:  # At least 60% of max length
            return text[:last_sentence + 1].strip()

    # No good sentence boundary, try word boundary
    truncate_point = text[:truncate_at].rfind(' ')
    if truncate_point > 0:
        return text[:truncate_point].strip() + '...'

    # Last resort: hard truncate
    return text[:truncate_at].strip() + '...'


def apply_field_limits(plant_data: Dict) -> Dict:
    """
    Apply field length limits to plant data.

    Args:
        plant_data: Dictionary with plant information

    Returns:
        Dictionary with truncated fields
    """
    limited_data = plant_data.copy()

    for field, max_length in FIELD_LIMITS.items():
        if field in limited_data and limited_data[field]:
            original = str(limited_data[field])
            if len(original) > max_length:
                limited_data[field] = truncate_text(original, max_length)
                logger.info(f"Truncated {field} from {len(original)} to {len(limited_data[field])} characters")

    return limited_data


def normalize_scientific_name(name: str) -> str:
    """
    Normalize scientific name to proper botanical casing.

    Rules:
    - Genus (first word): Capitalized (e.g., "Monstera")
    - Species (second word): lowercase (e.g., "deliciosa")
    - Subspecies/variety indicators: lowercase (var., subsp., f.)
    - Cultivar names in quotes: Title Case (e.g., 'Thai Constellation')
    - Hybrid marker (×): preserved

    Examples:
    - "MONSTERA DELICIOSA" -> "Monstera deliciosa"
    - "ficus elastica 'ruby'" -> "Ficus elastica 'Ruby'"
    - "PHILODENDRON HEDERACEUM VAR. OXYCARDIUM" -> "Philodendron hederaceum var. oxycardium"

    Args:
        name: Scientific name in any casing

    Returns:
        Properly formatted scientific name
    """
    if not name or not name.strip():
        return name

    name = name.strip()

    # Handle cultivar names in quotes separately
    # Split by single quotes to preserve cultivar names
    parts = re.split(r"('.*?')", name)

    normalized_parts = []
    for i, part in enumerate(parts):
        if part.startswith("'") and part.endswith("'"):
            # This is a cultivar name - use title case inside quotes
            inner = part[1:-1].strip()
            normalized_parts.append("'" + inner.title() + "'")
        else:
            # Regular scientific name part
            words = part.split()
            normalized_words = []

            for j, word in enumerate(words):
                if not word:
                    continue

                # Check if it's a special marker
                lower_word = word.lower()

                if lower_word in ('var.', 'subsp.', 'f.', 'ssp.'):
                    # Variety/subspecies indicators - lowercase
                    normalized_words.append(lower_word)
                elif lower_word == '×' or lower_word == 'x' and len(word) == 1:
                    # Hybrid marker
                    normalized_words.append('×')
                elif j == 0 and not normalized_words:
                    # First word (genus) - capitalize first letter, rest lowercase
                    normalized_words.append(word.capitalize())
                else:
                    # Species, subspecies names - all lowercase
                    normalized_words.append(word.lower())

            normalized_parts.append(' '.join(normalized_words))

    # Join parts, ensuring space before cultivar names
    result_parts = []
    for i, part in enumerate(normalized_parts):
        if part.startswith("'") and result_parts and not result_parts[-1].endswith(' '):
            result_parts.append(' ')
        result_parts.append(part)

    result = ''.join(result_parts)

    # Clean up any double spaces
    result = re.sub(r'\s+', ' ', result).strip()

    return result


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

class DatabaseManager:
    """Manages all database operations for plant data storage."""

    def __init__(self, db_path: str = DATABASE_PATH):
        """
        Initialize database manager and create tables if needed.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.initialize_database()

    def initialize_database(self) -> None:
        """Create database schema if it doesn't exist."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS plants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scientific_name TEXT UNIQUE NOT NULL,
                    common_name TEXT,
                    description TEXT,
                    light TEXT,
                    water TEXT,
                    feeding TEXT,
                    temperature TEXT,
                    humidity TEXT,
                    toxicity TEXT,
                    pdf_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Add description column to existing tables if it doesn't exist
            try:
                cursor.execute("SELECT description FROM plants LIMIT 1")
            except sqlite3.OperationalError:
                logger.info("Adding description column to existing plants table")
                cursor.execute("ALTER TABLE plants ADD COLUMN description TEXT")

            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def get_plant(self, scientific_name: str) -> Optional[Dict]:
        """
        Retrieve plant data by scientific name (case-insensitive).

        Args:
            scientific_name: Scientific name of the plant

        Returns:
            Dictionary with plant data or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM plants WHERE LOWER(scientific_name) = LOWER(?)",
                (scientific_name,)
            )

            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)
            return None
        except sqlite3.Error as e:
            logger.error(f"Error retrieving plant '{scientific_name}': {e}")
            return None

    def save_plant(self, plant_data: Dict, pdf_path: str = None) -> bool:
        """
        Save or update plant data in database.

        Args:
            plant_data: Dictionary containing plant information
            pdf_path: Path to generated PDF file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Apply field length limits before saving
            plant_data = apply_field_limits(plant_data)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO plants (
                    scientific_name, common_name, description, light, water, feeding,
                    temperature, humidity, toxicity, pdf_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scientific_name) DO UPDATE SET
                    common_name = excluded.common_name,
                    description = excluded.description,
                    light = excluded.light,
                    water = excluded.water,
                    feeding = excluded.feeding,
                    temperature = excluded.temperature,
                    humidity = excluded.humidity,
                    toxicity = excluded.toxicity,
                    pdf_path = excluded.pdf_path
            """, (
                plant_data.get('scientific_name'),
                plant_data.get('common_name'),
                plant_data.get('description'),
                plant_data.get('light'),
                plant_data.get('water'),
                plant_data.get('feeding'),
                plant_data.get('temperature'),
                plant_data.get('humidity'),
                plant_data.get('toxicity'),
                pdf_path
            ))

            conn.commit()
            conn.close()
            logger.info(f"Plant '{plant_data.get('scientific_name')}' saved to database")
            return True
        except sqlite3.Error as e:
            import traceback
            logger.error(f"Database error saving plant data: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
        except Exception as e:
            import traceback
            logger.error(f"Unexpected error saving plant data: {e}")
            logger.error(f"Plant data was: {plant_data}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def get_all_plants(self) -> List[Dict]:
        """
        Retrieve all plants from database, ordered by most recent first.

        Returns:
            List of plant dictionaries
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM plants ORDER BY created_at DESC")

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error retrieving all plants: {e}")
            return []

    def normalize_all_scientific_names(self) -> int:
        """
        Normalize scientific names for all existing plants in the database.
        This is a migration function to fix casing on existing entries.

        Returns:
            Number of plants updated
        """
        updated_count = 0

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all plants
            cursor.execute("SELECT id, scientific_name FROM plants")
            rows = cursor.fetchall()

            for row in rows:
                plant_id = row['id']
                current_name = row['scientific_name']
                normalized_name = normalize_scientific_name(current_name)

                if normalized_name != current_name:
                    cursor.execute(
                        "UPDATE plants SET scientific_name = ? WHERE id = ?",
                        (normalized_name, plant_id)
                    )
                    logger.info(f"Normalized: '{current_name}' -> '{normalized_name}'")
                    updated_count += 1

            conn.commit()
            conn.close()

            if updated_count > 0:
                logger.info(f"Normalized {updated_count} plant names in database")

            return updated_count

        except sqlite3.Error as e:
            logger.error(f"Error normalizing plant names: {e}")
            return 0

    def import_from_csv(self, csv_path: str) -> Tuple[int, List[str]]:
        """
        Import plant data from CSV file.

        Args:
            csv_path: Path to CSV file

        Returns:
            Tuple of (number of plants imported, list of error messages)
        """
        imported_count = 0
        errors = []

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as csvfile:  # utf-8-sig handles BOM
                reader = csv.DictReader(csvfile)

                # Detect CSV format (support both old and new formats)
                fieldnames = reader.fieldnames

                # Check if it's the Leaf & Vessel format
                has_botanical_name = 'Botanical Name' in fieldnames
                has_scientific_name = 'scientific_name' in fieldnames

                if not (has_botanical_name or has_scientific_name):
                    errors.append("CSV must contain either 'Botanical Name' or 'scientific_name' column")
                    return 0, errors

                for row_num, row in enumerate(reader, start=2):
                    # Handle both CSV formats
                    if has_botanical_name:
                        # Leaf & Vessel format
                        scientific_name = row.get('Botanical Name', '').strip()
                        common_name = row.get('Common Name', '').strip()
                        description = row.get('Description', '').strip()
                        light = row.get('Light', '').strip()
                        water = row.get('Water', '').strip()
                        feeding = row.get('Fertilizer', '').strip()
                        temperature = row.get('Temperature', '').strip()

                        # Combine cat and dog friendly into toxicity info
                        cat_friendly = row.get('Cat Friendly', '').strip()
                        dog_friendly = row.get('Dog Friendly', '').strip()
                        toxicity_parts = []
                        if cat_friendly.lower() == 'no':
                            toxicity_parts.append('toxic to cats')
                        if dog_friendly.lower() == 'no':
                            toxicity_parts.append('toxic to dogs')

                        if toxicity_parts:
                            toxicity = 'Toxic: ' + ' and '.join(toxicity_parts)
                        elif cat_friendly.lower() == 'yes' and dog_friendly.lower() == 'yes':
                            toxicity = 'Non-toxic to cats and dogs'
                        else:
                            toxicity = ''
                    else:
                        # Original format
                        scientific_name = row.get('scientific_name', '').strip()
                        common_name = row.get('common_name', '').strip()
                        description = row.get('description', '').strip()
                        light = row.get('light', '').strip()
                        water = row.get('water', '').strip()
                        feeding = row.get('feeding', '').strip()
                        temperature = row.get('temperature', '').strip()
                        toxicity = row.get('toxicity', '').strip()

                    if not scientific_name:
                        errors.append(f"Row {row_num}: Missing scientific name")
                        continue

                    # Normalize scientific name to proper casing
                    scientific_name = normalize_scientific_name(scientific_name)

                    plant_data = {
                        'scientific_name': scientific_name,
                        'common_name': common_name,
                        'description': description,
                        'light': light,
                        'water': water,
                        'feeding': feeding,
                        'temperature': temperature,
                        'humidity': row.get('humidity', '').strip() if not has_botanical_name else '',
                        'toxicity': toxicity
                    }

                    if self.save_plant(plant_data):
                        imported_count += 1
                    else:
                        errors.append(f"Row {row_num}: Failed to import '{scientific_name}'")

            logger.info(f"CSV import completed: {imported_count} plants imported")
            return imported_count, errors

        except FileNotFoundError:
            errors.append(f"File not found: {csv_path}")
            return 0, errors
        except Exception as e:
            logger.error(f"CSV import error: {e}")
            errors.append(f"Import error: {str(e)}")
            return 0, errors

# ============================================================================
# CLAUDE API INTEGRATION
# ============================================================================

class PlantDataFetcher:
    """Fetches plant care data using Claude API."""

    def __init__(self, api_key: str = ANTHROPIC_API_KEY):
        """
        Initialize API client.

        Args:
            api_key: Anthropic API key
        """
        self.api_key = api_key
        self.client = None

        if api_key and api_key != "sk-ant-...":
            try:
                self.client = anthropic.Anthropic(api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client: {e}")

    def fetch_plant_data(self, scientific_name: str) -> Dict:
        """
        Fetch plant care data from Claude API with comprehensive error handling.

        Args:
            scientific_name: Scientific name of the plant

        Returns:
            Dictionary with plant data or error information
        """
        if not self.client:
            return {
                'error': 'API key not configured. Please set ANTHROPIC_API_KEY in the script.'
            }

        prompt = self._build_prompt(scientific_name)

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Fetching data for '{scientific_name}' (attempt {attempt + 1}/{MAX_RETRIES})")

                message = self.client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    timeout=API_TIMEOUT
                )

                # Extract JSON from response
                response_text = message.content[0].text
                plant_data = self._parse_response(response_text)

                # Add scientific name to the data
                plant_data['scientific_name'] = scientific_name

                logger.info(f"Successfully fetched data for '{scientific_name}'")
                return plant_data

            except anthropic.RateLimitError as e:
                logger.warning(f"Rate limit hit for '{scientific_name}': {e}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    return {'error': 'API rate limit exceeded. Please try again in a few moments.'}

            except anthropic.APITimeoutError as e:
                logger.error(f"API timeout for '{scientific_name}': {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    return {'error': 'Request timed out. Please check your internet connection and try again.'}

            except anthropic.APIConnectionError as e:
                logger.error(f"Connection error for '{scientific_name}': {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                else:
                    return {'error': 'Network connection error. Please check your internet connection.'}

            except anthropic.AuthenticationError as e:
                logger.error(f"Authentication error: {e}")
                return {'error': 'Invalid API key. Please check your ANTHROPIC_API_KEY configuration.'}

            except Exception as e:
                logger.error(f"Unexpected error fetching plant data: {e}")
                return {'error': f'Unexpected error: {str(e)}'}

        return {'error': 'Failed to fetch plant data after multiple attempts.'}

    def _build_prompt(self, scientific_name: str) -> str:
        """Build the prompt for Claude API."""
        return f"""You are an expert commercial horticulturist writing care cards for "Leaf & Vessel," a plant shop in Hudson, Ohio. Your goal is to provide practical, safe advice for indoor home environments (USDA Zone 6b) where winters are dark and dry, and root rot is the primary killer of houseplants.

Input Plant: {scientific_name}

---

STEP 1: IDENTIFY THE PLANT CATEGORY

Before generating output, determine which category the plant belongs to. This determines watering guidance.

CATEGORY A — Moisture Lovers (keep consistently moist, never soggy):
True ferns, Calathea/Goeppertia, Maranta, Stromanthe, Ctenanthe, Tradescantia, Alocasia, Colocasia, most Begonias, Fittonia, Selaginella, carnivorous plants.
→ Water instruction: "Keep soil lightly moist. Water when top 1" is dry. Never let dry out completely."

CATEGORY B — Moderate (allow partial drying):
Most aroids (Monstera, Philodendron, Pothos, Anthurium, Syngonium), Ficus, Schefflera, Aglaonema, Dieffenbachia, Dracaena (marginata, fragrans, reflexa), Croton, Palms, Pilea, Chlorophytum.
→ Water instruction: "Allow top 50% of soil to dry between waterings. Reduce frequency significantly in winter."

CATEGORY C — Semi-Drought Tolerant (dry almost completely):
Scindapsus, Peperomia, Hoya, Ceropegia, Dischidia, Epipremnum with thick leaves.
→ Water instruction: "Allow soil to dry almost completely between waterings. Very drought tolerant."

CATEGORY D — Drought Tolerant (dry completely):
Sansevieria/Dracaena trifasciata, ZZ Plant, all succulents, all cacti, Ponytail Palm, Euphorbia.
→ Water instruction: "Allow soil to dry out completely. Water sparingly, especially in winter (monthly or less)."

CATEGORY E — Specialized Care:
Orchids (Phalaenopsis): "Water when roots turn silver/gray. Soak and drain method. Never let roots sit in water."
Bromeliads: "Keep central cup filled with water. Moisten soil lightly. Empty and refill cup weekly."
Air plants (Tillandsia): "Soak in water for 20-30 minutes weekly. Shake dry and allow to air dry upside down."

If a plant does not clearly fit any category, state your reasoning in a "notes" field and provide your best guidance.

---

STEP 2: APPLY THESE GUIDELINES

Cultivars & Variegation: Base care on the species. If heavily variegated (e.g., 'Albo', 'Thai Constellation', 'Marble Queen'), note that it requires MORE light than the green form to maintain variegation.

Taxonomy: Use the name most commonly used in commercial retail. If recently reclassified (Calathea → Goeppertia, Sansevieria → Dracaena), prefer the older, widely-recognized name for the "common_name" field.

Light Descriptions: Be specific. Use this scale:
- "Low light tolerant" = survives 50-100 foot-candles (north window, interior room)
- "Medium indirect light" = 100-500 foot-candles (bright room, few feet from window)
- "Bright indirect light" = 500-1000 foot-candles (near east/west window, filtered south)
- "Direct sun tolerant" = can handle some unfiltered sun (south window)

Winter in Zone 6b: Indoor humidity drops to 20-30%. Heating vents are a major threat. Always mention if a plant needs humidity support in winter.

Toxicity: You MUST explicitly state one of:
- "Non-toxic to cats and dogs"
- "Toxic to cats and dogs if ingested. Keep out of reach."
- "Mildly toxic—may cause mouth irritation if chewed."

When uncertain about toxicity, default to "Considered toxic. Keep away from pets and children."

---

OUTPUT FORMAT

Return ONLY a valid JSON object. No markdown, no code fences, no commentary.

{{
  "common_name": "Most recognizable retail name",
  "description": "2-3 sentences. Focus on appearance, growth habit, and what makes it appealing.",
  "light": "Specific guidance using the light scale above. Mention if variegated forms need more light.",
  "water": "Strictly follow the category instruction. Include winter note if applicable.",
  "feeding": "Fertilizer guidance, typically monthly during growing season (spring-summer). Reduce or stop in winter.",
  "temperature": "Ideal range in °F. Note sensitivity to cold drafts or heating vents if applicable.",
  "humidity": "Specific percentage range. Note if humidity support needed in Zone 6b winter.",
  "toxicity": "MUST state toxicity to cats and dogs explicitly using one of the approved phrases.",
  "error": null
}}

If the plant name is invalid or unrecognized, return:
{{
  "error": "Plant not recognized. Please check the scientific name."
}}"""

    def _parse_response(self, response_text: str) -> Dict:
        """
        Parse JSON response from Claude API.

        Args:
            response_text: Raw response text from API

        Returns:
            Dictionary with plant data
        """
        try:
            # Try to find JSON in the response
            # Sometimes the API returns text before/after the JSON
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)

                # Check if the API returned an error
                if data.get('error'):
                    return {'error': data['error']}

                return data
            else:
                logger.error(f"No JSON found in response: {response_text}")
                return {'error': 'Invalid response format from API'}

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}\nResponse: {response_text}")
            return {'error': 'Failed to parse API response'}

# ============================================================================
# FEEDBACK VERIFICATION
# ============================================================================

class FeedbackVerifier:
    """Verifies plant care feedback using Claude API."""

    def __init__(self, api_key: str = ANTHROPIC_API_KEY):
        """Initialize feedback verifier with API client."""
        self.api_key = api_key
        self.client = None

        if api_key and api_key != "sk-ant-...":
            try:
                self.client = anthropic.Anthropic(api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic client for feedback: {e}")

    def verify_feedback(self, feedback: str, plants_data: List[Dict], selected_plant: Optional[str] = None) -> Dict:
        """
        Parse and verify user feedback about plant care.

        Args:
            feedback: User's feedback text
            plants_data: List of all plants in database with their current data
            selected_plant: Optional specific plant name if user selected one

        Returns:
            Dictionary with parsed feedback, verification results, and response text
        """
        if not self.client:
            return {
                'error': 'API key not configured.',
                'response_text': 'Error: API key not configured. Please set ANTHROPIC_API_KEY.',
                'corrections': []
            }

        prompt = self._build_verification_prompt(feedback, plants_data, selected_plant)

        try:
            logger.info(f"Verifying feedback: {feedback[:100]}...")

            message = self.client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2048,
                temperature=0.2,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                timeout=API_TIMEOUT
            )

            response_text = message.content[0].text
            return self._parse_verification_response(response_text)

        except anthropic.RateLimitError:
            return {
                'error': 'Rate limit exceeded. Please try again.',
                'response_text': 'Error: API rate limit exceeded. Please wait a moment and try again.',
                'corrections': []
            }
        except anthropic.APITimeoutError:
            return {
                'error': 'Request timed out.',
                'response_text': 'Error: Request timed out. Please check your connection and try again.',
                'corrections': []
            }
        except Exception as e:
            logger.error(f"Feedback verification error: {e}")
            return {
                'error': str(e),
                'response_text': f'Error: {str(e)}',
                'corrections': []
            }

    def _build_verification_prompt(self, feedback: str, plants_data: List[Dict], selected_plant: Optional[str]) -> str:
        """Build the prompt for feedback verification."""
        # Build plant context
        if selected_plant:
            # Filter to just the selected plant
            relevant_plants = [p for p in plants_data if p.get('scientific_name', '').lower() == selected_plant.lower()]
            plants_context = ""
            for plant in relevant_plants:
                plants_context += f"\n- {plant.get('scientific_name', 'Unknown')}"
                if plant.get('common_name'):
                    plants_context += f" ({plant.get('common_name')})"
                plants_context += ":"
                for field in ['light', 'water', 'feeding', 'temperature', 'humidity', 'toxicity', 'description']:
                    if plant.get(field):
                        plants_context += f"\n  {field}: {plant.get(field)}"
        else:
            # No plant selected - include list of all plant names, then try to find relevant ones
            feedback_lower = feedback.lower()

            # Find plants that might be mentioned in feedback (fuzzy match on name parts)
            relevant_plants = []
            for p in plants_data:
                sci_name = p.get('scientific_name', '').lower()
                common_name = (p.get('common_name') or '').lower()
                # Check if any part of the plant name appears in feedback
                name_parts = sci_name.replace("'", " ").replace('"', ' ').split()
                if any(part in feedback_lower for part in name_parts if len(part) > 3):
                    relevant_plants.append(p)
                elif common_name and any(part in feedback_lower for part in common_name.split() if len(part) > 3):
                    relevant_plants.append(p)

            # Build context with full details for relevant plants
            plants_context = ""
            if relevant_plants:
                plants_context += "\n\nPLANTS POSSIBLY MENTIONED IN FEEDBACK (full details):"
                for plant in relevant_plants:
                    plants_context += f"\n- {plant.get('scientific_name', 'Unknown')}"
                    if plant.get('common_name'):
                        plants_context += f" ({plant.get('common_name')})"
                    plants_context += ":"
                    for field in ['light', 'water', 'feeding', 'temperature', 'humidity', 'toxicity', 'description']:
                        if plant.get(field):
                            plants_context += f"\n  {field}: {plant.get(field)}"

            # Also include a list of all plant names so the AI knows what's available
            all_names = sorted([p.get('scientific_name', '') for p in plants_data])
            plants_context += f"\n\nALL PLANTS IN DATABASE ({len(all_names)} total):\n"
            plants_context += ", ".join(all_names)

        return f"""You are an expert horticulturist verifying feedback about plant care information.

CURRENT PLANT DATA IN DATABASE:
{plants_context}

USER FEEDBACK:
{feedback}

{f"NOTE: User has specifically selected plant: {selected_plant}" if selected_plant else ""}

Your task:
1. Identify which plant(s) and field(s) the user is providing feedback about
2. Verify if the user's suggested correction is accurate based on authoritative horticultural sources
3. For each correction, determine if you AGREE or DISAGREE with citations

Return ONLY a valid JSON object with this exact structure:
{{
  "response_text": "Natural language response to show in chat. Be conversational but concise. Include verification status and brief reasoning.",
  "corrections": [
    {{
      "plant": "scientific name of plant",
      "field": "field name (light, water, feeding, temperature, humidity, toxicity, or description)",
      "current_value": "current value in database",
      "suggested_value": "what user suggests it should be",
      "verification": "agree" or "disagree",
      "reasoning": "Brief explanation of why you agree or disagree",
      "citations": ["Source 1", "Source 2"],
      "recommended_value": "The correct value to use (user's suggestion if agree, or your correction if disagree)"
    }}
  ]
}}

Important:
- If the user mentions a plant not in the database, say so in response_text and return empty corrections
- If feedback is unclear or doesn't suggest specific changes, ask for clarification in response_text
- Always cite authoritative sources (university extension services, botanical gardens, peer-reviewed research)
- If you disagree, explain why and provide the correct information with citations
- Keep recommended_value concise (under 180 characters for most fields)"""

    def _parse_verification_response(self, response_text: str) -> Dict:
        """Parse the verification response from Claude."""
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                data = json.loads(json_str)
                return data
            else:
                logger.error(f"No JSON found in verification response: {response_text}")
                return {
                    'error': 'Invalid response format',
                    'response_text': 'Sorry, I had trouble processing that. Could you try rephrasing your feedback?',
                    'corrections': []
                }

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in verification: {e}\nResponse: {response_text}")
            return {
                'error': 'Failed to parse response',
                'response_text': 'Sorry, I had trouble understanding that. Could you try again?',
                'corrections': []
            }


# ============================================================================
# PDF GENERATION
# ============================================================================

class PDFGenerator:
    """Generates 4x6 inch plant care card PDFs."""

    def __init__(self, logo_path: str = LOGO_PATH, output_dir: str = CARDS_DIR):
        """
        Initialize PDF generator.

        Args:
            logo_path: Path to logo image file
            output_dir: Base directory for PDF output
        """
        self.logo_path = logo_path
        self.output_dir = output_dir

        # Verify logo exists
        if not os.path.exists(logo_path):
            logger.warning(f"Logo file not found: {logo_path}")

    def generate_care_card(self, plant_data: Dict) -> Optional[str]:
        """
        Generate a 6x4 inch landscape PDF care card for a plant.

        Args:
            plant_data: Dictionary containing plant information

        Returns:
            Path to generated PDF file or None if failed
        """
        try:
            # Apply field length limits to prevent text overflow
            plant_data = apply_field_limits(plant_data)

            # Create output directory
            output_path = Path(self.output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Generate filename
            scientific_name = plant_data.get('scientific_name', 'unknown')
            safe_name = re.sub(r'[^\w\s-]', '', scientific_name).strip().replace(' ', '_')
            timestamp = datetime.now().strftime('%Y%m%d')
            filename = f"{safe_name}_{timestamp}.pdf"
            pdf_path = output_path / filename

            # Create temporary PDF for page 1 (plant care info)
            temp_pdf_path = output_path / f"temp_{filename}"
            c = canvas.Canvas(str(temp_pdf_path), pagesize=(PDF_WIDTH, PDF_HEIGHT))

            # Draw title at top center
            c.setFont("Helvetica-Bold", 16)
            title_text = "Plant Care Guide"
            title_width = c.stringWidth(title_text, "Helvetica-Bold", 16)
            title_x = (PDF_WIDTH - title_width) / 2
            title_y = PDF_HEIGHT - PDF_MARGIN - 5
            c.drawString(title_x, title_y, title_text)

            # Set up text positioning - start below title
            y_position = PDF_HEIGHT - PDF_MARGIN - 30

            # Draw scientific name (italic, 14pt)
            c.setFont("Helvetica-Oblique", 14)
            scientific_text = plant_data.get('scientific_name', '')
            text_width = c.stringWidth(scientific_text, "Helvetica-Oblique", 14)
            x_position = PDF_WIDTH - PDF_MARGIN - text_width
            c.drawString(x_position, y_position, scientific_text)
            y_position -= 20

            # Draw common name (bold, 11pt)
            c.setFont("Helvetica-Bold", 11)
            common_name = plant_data.get('common_name', '')
            if common_name:
                text_width = c.stringWidth(common_name, "Helvetica-Bold", 11)
                x_position = PDF_WIDTH - PDF_MARGIN - text_width
                c.drawString(x_position, y_position, common_name)
            y_position -= 20

            # Draw description (italic, 8pt) - wrapped to full width
            description = plant_data.get('description', '')
            if description:
                c.setFont("Helvetica-Oblique", 8)
                desc_max_width = PDF_WIDTH - (2 * PDF_MARGIN)
                wrapped_desc = self._wrap_text(c, description, "Helvetica-Oblique", 8, desc_max_width)

                for line in wrapped_desc:
                    c.drawString(PDF_MARGIN, y_position, line)
                    y_position -= 10
                y_position -= 5  # Extra spacing after description
            else:
                y_position -= 10

            # Draw care information (9pt regular)
            c.setFont("Helvetica", 9)
            care_fields = [
                ('Light:', plant_data.get('light', 'N/A')),
                ('Water:', plant_data.get('water', 'N/A')),
                ('Feeding:', plant_data.get('feeding', 'N/A')),
                ('Temperature:', plant_data.get('temperature', 'N/A')),
                ('Humidity:', plant_data.get('humidity', 'N/A')),
                ('Toxicity:', plant_data.get('toxicity', 'N/A'))
            ]

            label_x = PDF_MARGIN
            value_x = PDF_MARGIN + 80
            max_width = PDF_WIDTH - value_x - PDF_MARGIN

            for label, value in care_fields:
                # Draw label (bold)
                c.setFont("Helvetica-Bold", 9)
                c.drawString(label_x, y_position, label)

                # Draw value (regular), wrap if necessary
                c.setFont("Helvetica", 9)
                wrapped_lines = self._wrap_text(c, value, "Helvetica", 9, max_width)

                for line in wrapped_lines:
                    c.drawString(value_x, y_position, line)
                    y_position -= 12

                y_position -= 3  # Extra spacing between fields

            # Save the first page
            c.save()

            # Merge with Card_Back.pdf as second page
            card_back_path = Path(CARD_BACK_PATH)
            if card_back_path.exists():
                try:
                    # Create a PDF writer
                    pdf_writer = PdfWriter()

                    # Add page 1 (plant care info)
                    with open(temp_pdf_path, 'rb') as f1:
                        pdf_reader1 = PdfReader(f1)
                        pdf_writer.add_page(pdf_reader1.pages[0])

                    # Add page 2 (card back)
                    with open(card_back_path, 'rb') as f2:
                        pdf_reader2 = PdfReader(f2)
                        pdf_writer.add_page(pdf_reader2.pages[0])

                    # Write the merged PDF
                    with open(pdf_path, 'wb') as output_file:
                        pdf_writer.write(output_file)

                    # Clean up temp file
                    temp_pdf_path.unlink()

                    logger.info(f"PDF generated with 2 pages: {pdf_path}")
                except Exception as e:
                    logger.error(f"Error merging Card_Back.pdf: {e}")
                    # If merge fails, use the temp file as final
                    temp_pdf_path.rename(pdf_path)
                    logger.info(f"PDF generated (1 page only): {pdf_path}")
            else:
                # No Card_Back.pdf, use the temp file as final
                logger.warning(f"Card_Back.pdf not found at {card_back_path}")
                temp_pdf_path.rename(pdf_path)
                logger.info(f"PDF generated (1 page only): {pdf_path}")

            return str(pdf_path)

        except Exception as e:
            import traceback
            logger.error(f"PDF generation error: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def _wrap_text(self, canvas_obj, text: str, font: str, font_size: int, max_width: float) -> List[str]:
        """
        Wrap text to fit within specified width.

        Args:
            canvas_obj: ReportLab canvas object
            text: Text to wrap
            font: Font name
            font_size: Font size
            max_width: Maximum width in points

        Returns:
            List of wrapped text lines
        """
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            test_width = canvas_obj.stringWidth(test_line, font, font_size)

            if test_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        return lines if lines else [text]

    def generate_catalog_pdf(self, plants_data: List[Dict]) -> Optional[str]:
        """
        Generate a multi-page PDF catalog with all plants.
        Each page matches the format of the first page of individual care cards.

        Args:
            plants_data: List of plant data dictionaries

        Returns:
            Path to generated PDF file or None if failed
        """
        if not plants_data:
            logger.warning("No plants to include in catalog")
            return None

        try:
            # Create output directory
            output_path = Path(self.output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"Plant_Catalog_{timestamp}.pdf"
            pdf_path = output_path / filename

            # Create the PDF canvas
            c = canvas.Canvas(str(pdf_path), pagesize=(PDF_WIDTH, PDF_HEIGHT))

            for idx, plant_data in enumerate(plants_data):
                # Apply field length limits
                plant_data = apply_field_limits(plant_data)

                # Draw title at top center
                c.setFont("Helvetica-Bold", 16)
                title_text = "Plant Care Guide"
                title_width = c.stringWidth(title_text, "Helvetica-Bold", 16)
                title_x = (PDF_WIDTH - title_width) / 2
                title_y = PDF_HEIGHT - PDF_MARGIN - 5
                c.drawString(title_x, title_y, title_text)

                # Set up text positioning - start below title
                y_position = PDF_HEIGHT - PDF_MARGIN - 30

                # Draw scientific name (italic, 14pt)
                c.setFont("Helvetica-Oblique", 14)
                scientific_text = plant_data.get('scientific_name', '')
                text_width = c.stringWidth(scientific_text, "Helvetica-Oblique", 14)
                x_position = PDF_WIDTH - PDF_MARGIN - text_width
                c.drawString(x_position, y_position, scientific_text)
                y_position -= 20

                # Draw common name (bold, 11pt)
                c.setFont("Helvetica-Bold", 11)
                common_name = plant_data.get('common_name', '')
                if common_name:
                    text_width = c.stringWidth(common_name, "Helvetica-Bold", 11)
                    x_position = PDF_WIDTH - PDF_MARGIN - text_width
                    c.drawString(x_position, y_position, common_name)
                y_position -= 20

                # Draw description (italic, 8pt) - wrapped to full width
                description = plant_data.get('description', '')
                if description:
                    c.setFont("Helvetica-Oblique", 8)
                    desc_max_width = PDF_WIDTH - (2 * PDF_MARGIN)
                    wrapped_desc = self._wrap_text(c, description, "Helvetica-Oblique", 8, desc_max_width)

                    for line in wrapped_desc:
                        c.drawString(PDF_MARGIN, y_position, line)
                        y_position -= 10
                    y_position -= 5  # Extra spacing after description
                else:
                    y_position -= 10

                # Draw care information (9pt regular)
                c.setFont("Helvetica", 9)
                care_fields = [
                    ('Light:', plant_data.get('light', 'N/A')),
                    ('Water:', plant_data.get('water', 'N/A')),
                    ('Feeding:', plant_data.get('feeding', 'N/A')),
                    ('Temperature:', plant_data.get('temperature', 'N/A')),
                    ('Humidity:', plant_data.get('humidity', 'N/A')),
                    ('Toxicity:', plant_data.get('toxicity', 'N/A'))
                ]

                label_x = PDF_MARGIN
                value_x = PDF_MARGIN + 80
                max_width = PDF_WIDTH - value_x - PDF_MARGIN

                for label, value in care_fields:
                    # Draw label (bold)
                    c.setFont("Helvetica-Bold", 9)
                    c.drawString(label_x, y_position, label)

                    # Draw value (regular), wrap if necessary
                    c.setFont("Helvetica", 9)
                    wrapped_lines = self._wrap_text(c, value, "Helvetica", 9, max_width)

                    for line in wrapped_lines:
                        c.drawString(value_x, y_position, line)
                        y_position -= 12

                    y_position -= 3  # Extra spacing between fields

                # Add new page if not the last plant
                if idx < len(plants_data) - 1:
                    c.showPage()

            # Save the PDF
            c.save()
            logger.info(f"Catalog PDF generated with {len(plants_data)} pages: {pdf_path}")
            return str(pdf_path)

        except Exception as e:
            import traceback
            logger.error(f"Catalog PDF generation error: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

# ============================================================================
# EDIT PLANT WINDOW
# ============================================================================

class EditPlantWindow(ctk.CTkToplevel):
    """Popup window for manually editing plant data."""

    # Editable fields (excludes key fields like scientific_name, pdf_path, created_at)
    EDITABLE_FIELDS = [
        ('common_name', 'Common Name'),
        ('description', 'Description'),
        ('light', 'Light'),
        ('water', 'Water'),
        ('feeding', 'Feeding'),
        ('temperature', 'Temperature'),
        ('humidity', 'Humidity'),
        ('toxicity', 'Toxicity')
    ]

    def __init__(self, parent, plant_data: Dict, on_save_callback):
        """
        Initialize the edit window.

        Args:
            parent: Parent window
            plant_data: Dictionary with current plant data
            on_save_callback: Function to call when save is clicked, receives updated plant_data
        """
        super().__init__(parent)

        self.plant_data = plant_data.copy()
        self.on_save_callback = on_save_callback
        self.field_entries = {}

        # Window setup
        self.title(f"Edit: {plant_data.get('scientific_name', 'Plant')}")
        self.geometry("500x600")
        self.resizable(False, False)

        # Make modal
        self.transient(parent)
        self.grab_set()

        # Build UI
        self._build_ui()

        # Center on parent
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + (parent_width - 500) // 2
        y = parent_y + (parent_height - 600) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self) -> None:
        """Build the edit window UI."""
        # Main container with scrolling
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Header with plant name (read-only)
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="ew")

        scientific_label = ctk.CTkLabel(
            header_frame,
            text=self.plant_data.get('scientific_name', 'Unknown Plant'),
            font=ctk.CTkFont(size=16, weight="bold", slant="italic")
        )
        scientific_label.pack()

        # Scrollable frame for fields
        scroll_frame = ctk.CTkScrollableFrame(self, height=450)
        scroll_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        scroll_frame.grid_columnconfigure(0, weight=1)

        # Create entry fields for each editable field
        for i, (field_key, field_label) in enumerate(self.EDITABLE_FIELDS):
            # Label
            label = ctk.CTkLabel(
                scroll_frame,
                text=f"{field_label}:",
                font=ctk.CTkFont(size=12, weight="bold")
            )
            label.grid(row=i*2, column=0, pady=(10, 2), sticky="w")

            # Get current value
            current_value = self.plant_data.get(field_key, '') or ''

            # Use textbox for description (multi-line), entry for others
            if field_key == 'description':
                entry = ctk.CTkTextbox(
                    scroll_frame,
                    height=80,
                    font=ctk.CTkFont(size=11),
                    wrap="word"
                )
                entry.insert("1.0", current_value)
            else:
                entry = ctk.CTkTextbox(
                    scroll_frame,
                    height=50,
                    font=ctk.CTkFont(size=11),
                    wrap="word"
                )
                entry.insert("1.0", current_value)

            entry.grid(row=i*2+1, column=0, pady=(0, 5), sticky="ew")
            self.field_entries[field_key] = entry

        # Button frame
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=2, column=0, padx=20, pady=(5, 15), sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        # Cancel button
        cancel_button = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self._on_cancel,
            font=ctk.CTkFont(size=13),
            height=35,
            fg_color=FOOTER_COLOR,
            hover_color="#888888"
        )
        cancel_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        # Save button
        save_button = ctk.CTkButton(
            button_frame,
            text="Save",
            command=self._on_save,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=35
        )
        save_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self.destroy()

    def _on_save(self) -> None:
        """Handle save button click."""
        # Collect values from all fields
        for field_key, entry in self.field_entries.items():
            value = entry.get("1.0", "end-1c").strip()
            self.plant_data[field_key] = value

        # Apply field limits
        self.plant_data = apply_field_limits(self.plant_data)

        # Call the save callback
        self.on_save_callback(self.plant_data)

        # Close window
        self.destroy()


# ============================================================================
# GUI APPLICATION
# ============================================================================

class CareCardGeneratorApp:
    """Main GUI application for plant care card generation."""

    def __init__(self):
        """Initialize the application."""
        # Set appearance mode and color theme
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("green")

        # Initialize components
        self.db = DatabaseManager()
        self.api_fetcher = PlantDataFetcher()
        self.pdf_generator = PDFGenerator()
        self.feedback_verifier = FeedbackVerifier()

        # Normalize existing scientific names (one-time migration)
        self.db.normalize_all_scientific_names()

        # Feedback state
        self.pending_corrections = []  # List of corrections awaiting approval
        self.correction_checkboxes = []  # Checkbox widgets for corrections
        self.correction_vars = []  # BooleanVar for each checkbox

        # Create main window
        self.root = ctk.CTk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.resizable(False, False)

        # Build GUI
        self._build_gui()

        # Load initial plant list
        self._refresh_plant_list()
        self._refresh_plant_dropdown()

        logger.info("Application initialized")

    def _build_gui(self) -> None:
        """Build the GUI layout with two-column design."""
        # Configure main grid - two columns
        self.root.grid_columnconfigure(0, weight=1)  # Left panel
        self.root.grid_columnconfigure(1, weight=1)  # Right panel (feedback)
        self.root.grid_rowconfigure(1, weight=1)

        # =====================================================================
        # HEADER (spans both columns)
        # =====================================================================
        header_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        header_frame.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="ew")

        title_label = ctk.CTkLabel(
            header_frame,
            text="Leaf & Vessel Care Card Generator",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack()

        # =====================================================================
        # LEFT PANEL - Card Generation
        # =====================================================================
        left_panel = ctk.CTkFrame(self.root)
        left_panel.grid(row=1, column=0, padx=(20, 10), pady=(0, 20), sticky="nsew")
        left_panel.grid_columnconfigure(0, weight=1)
        left_panel.grid_rowconfigure(2, weight=1)

        # Input Section
        input_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        input_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        # Scientific name input
        name_label = ctk.CTkLabel(
            input_frame,
            text="Scientific Name:",
            font=ctk.CTkFont(size=13)
        )
        name_label.grid(row=0, column=0, pady=(5, 3), sticky="w")

        self.name_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="e.g., Monstera deliciosa",
            font=ctk.CTkFont(size=13),
            height=35
        )
        self.name_entry.grid(row=1, column=0, pady=(0, 8), sticky="ew")
        self.name_entry.bind("<Return>", lambda e: self._generate_card())

        # Buttons frame
        button_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        button_frame.grid(row=2, column=0, pady=(0, 5), sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        # Generate button
        self.generate_button = ctk.CTkButton(
            button_frame,
            text="Generate Card",
            command=self._generate_card,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=35
        )
        self.generate_button.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        # Import CSV button
        import_button = ctk.CTkButton(
            button_frame,
            text="Import CSV",
            command=self._import_csv,
            font=ctk.CTkFont(size=13),
            height=35,
            fg_color=SECONDARY_COLOR,
            hover_color=PRIMARY_COLOR
        )
        import_button.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # Export Catalog button
        export_button = ctk.CTkButton(
            input_frame,
            text="Export All Plants to Catalog PDF",
            command=self._export_catalog,
            font=ctk.CTkFont(size=13),
            height=35,
            fg_color="#1976D2",  # Blue color to distinguish from other buttons
            hover_color="#1565C0"
        )
        export_button.grid(row=3, column=0, pady=(8, 0), sticky="ew")

        # Status label
        self.status_label = ctk.CTkLabel(
            input_frame,
            text="Ready",
            font=ctk.CTkFont(size=11),
            text_color=PRIMARY_COLOR
        )
        self.status_label.grid(row=4, column=0, pady=(5, 0))

        # History Section
        history_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        history_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="nsew")
        history_frame.grid_columnconfigure(0, weight=1)
        history_frame.grid_rowconfigure(1, weight=1)

        # History header
        history_header = ctk.CTkFrame(history_frame, fg_color="transparent")
        history_header.grid(row=0, column=0, pady=(0, 5), sticky="ew")
        history_header.grid_columnconfigure(0, weight=1)

        history_title = ctk.CTkLabel(
            history_header,
            text="Recent Plants",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        history_title.grid(row=0, column=0, sticky="w")

        self.count_label = ctk.CTkLabel(
            history_header,
            text="(0 plants)",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.count_label.grid(row=0, column=1, sticky="e", padx=(10, 0))

        # Plant list
        self.plant_listbox = ctk.CTkScrollableFrame(history_frame, height=250)
        self.plant_listbox.grid(row=1, column=0, sticky="nsew")
        self.plant_listbox.grid_columnconfigure(0, weight=1)

        self.plant_buttons = []

        # =====================================================================
        # RIGHT PANEL - Feedback Chat
        # =====================================================================
        right_panel = ctk.CTkFrame(self.root)
        right_panel.grid(row=1, column=1, padx=(10, 20), pady=(0, 20), sticky="nsew")
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(1, weight=1)  # Chat history expands
        right_panel.grid_rowconfigure(3, weight=0)  # Pending changes

        # Feedback header with plant selector
        feedback_header = ctk.CTkFrame(right_panel, fg_color="transparent")
        feedback_header.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        feedback_header.grid_columnconfigure(1, weight=1)

        feedback_title = ctk.CTkLabel(
            feedback_header,
            text="Feedback Chat",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        feedback_title.grid(row=0, column=0, sticky="w")

        # Plant selector dropdown
        plant_label = ctk.CTkLabel(
            feedback_header,
            text="Plant:",
            font=ctk.CTkFont(size=11)
        )
        plant_label.grid(row=0, column=1, sticky="e", padx=(10, 5))

        self.plant_selector = ctk.CTkComboBox(
            feedback_header,
            values=["All Plants"],
            width=200,
            font=ctk.CTkFont(size=11),
            state="readonly",
            command=self._on_plant_selection_changed
        )
        self.plant_selector.grid(row=0, column=2, sticky="e")
        self.plant_selector.set("All Plants")

        # Edit button (only enabled when a specific plant is selected)
        self.edit_button = ctk.CTkButton(
            feedback_header,
            text="Edit",
            command=self._open_edit_window,
            font=ctk.CTkFont(size=11),
            width=50,
            height=28,
            state="disabled"
        )
        self.edit_button.grid(row=0, column=3, sticky="e", padx=(5, 0))

        # Chat history display
        self.chat_display = ctk.CTkTextbox(
            right_panel,
            font=ctk.CTkFont(size=11),
            wrap="word",
            state="disabled"
        )
        self.chat_display.grid(row=1, column=0, padx=10, pady=(5, 5), sticky="nsew")

        # Configure chat text tags for colors
        self.chat_display._textbox.tag_configure("user", foreground=CHAT_USER_COLOR)
        self.chat_display._textbox.tag_configure("assistant", foreground=CHAT_ASSISTANT_COLOR)
        self.chat_display._textbox.tag_configure("error", foreground=ERROR_COLOR)
        self.chat_display._textbox.tag_configure("agree", foreground=SUCCESS_COLOR)
        self.chat_display._textbox.tag_configure("disagree", foreground="#FF9800")  # Orange

        # Input area
        input_area = ctk.CTkFrame(right_panel, fg_color="transparent")
        input_area.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="ew")
        input_area.grid_columnconfigure(0, weight=1)

        self.feedback_entry = ctk.CTkEntry(
            input_area,
            placeholder_text="Type your feedback about plant care info...",
            font=ctk.CTkFont(size=11),
            height=35
        )
        self.feedback_entry.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        self.feedback_entry.bind("<Return>", lambda e: self._send_feedback())

        self.send_button = ctk.CTkButton(
            input_area,
            text="Send",
            command=self._send_feedback,
            font=ctk.CTkFont(size=11),
            width=60,
            height=35
        )
        self.send_button.grid(row=0, column=1)

        # Pending changes section
        pending_frame = ctk.CTkFrame(right_panel)
        pending_frame.grid(row=3, column=0, padx=10, pady=(5, 10), sticky="ew")
        pending_frame.grid_columnconfigure(0, weight=1)

        self.pending_label = ctk.CTkLabel(
            pending_frame,
            text="Pending Changes (0):",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.pending_label.grid(row=0, column=0, padx=10, pady=(8, 5), sticky="w")

        # Scrollable frame for pending corrections
        self.pending_list = ctk.CTkScrollableFrame(pending_frame, height=100)
        self.pending_list.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")
        self.pending_list.grid_columnconfigure(0, weight=1)

        # Action buttons
        action_frame = ctk.CTkFrame(pending_frame, fg_color="transparent")
        action_frame.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")
        action_frame.grid_columnconfigure(0, weight=1)
        action_frame.grid_columnconfigure(1, weight=1)

        self.apply_button = ctk.CTkButton(
            action_frame,
            text="Apply Selected",
            command=self._apply_corrections,
            font=ctk.CTkFont(size=11),
            height=30,
            state="disabled"
        )
        self.apply_button.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.clear_button = ctk.CTkButton(
            action_frame,
            text="Clear All",
            command=self._clear_corrections,
            font=ctk.CTkFont(size=11),
            height=30,
            fg_color=FOOTER_COLOR,
            hover_color="#888888"
        )
        self.clear_button.grid(row=0, column=1, padx=(4, 0), sticky="ew")

    def _refresh_plant_list(self) -> None:
        """Refresh the plant history list."""
        # Clear existing buttons
        for button in self.plant_buttons:
            button.destroy()
        self.plant_buttons.clear()

        # Get all plants
        plants = self.db.get_all_plants()

        # Update count
        self.count_label.configure(text=f"({len(plants)} plants)")

        # Add plant buttons
        for plant in plants:
            scientific_name = plant['scientific_name']
            common_name = plant.get('common_name', '')

            display_text = scientific_name
            if common_name:
                display_text += f" - {common_name}"

            button = ctk.CTkButton(
                self.plant_listbox,
                text=display_text,
                command=lambda name=scientific_name: self._regenerate_card(name),
                anchor="w",
                height=35,
                fg_color="transparent",
                hover_color=SECONDARY_COLOR,
                text_color=TEXT_COLOR,
                font=ctk.CTkFont(size=12)
            )
            button.grid(row=len(self.plant_buttons), column=0, padx=5, pady=2, sticky="ew")
            self.plant_buttons.append(button)

    def _refresh_plant_dropdown(self) -> None:
        """Refresh the plant selector dropdown in feedback panel."""
        plants = self.db.get_all_plants()
        plant_names = sorted([p['scientific_name'] for p in plants], key=str.lower)
        plant_names = ["All Plants"] + plant_names
        self.plant_selector.configure(values=plant_names)

    def _on_plant_selection_changed(self, selection: str) -> None:
        """Handle plant selector dropdown selection change."""
        if selection == "All Plants":
            self.edit_button.configure(state="disabled")
        else:
            self.edit_button.configure(state="normal")

    def _open_edit_window(self) -> None:
        """Open the edit window for the selected plant."""
        selected_plant = self.plant_selector.get()
        if selected_plant == "All Plants":
            return

        # Get plant data from database
        plant_data = self.db.get_plant(selected_plant)
        if not plant_data:
            messagebox.showerror("Error", f"Could not find plant: {selected_plant}")
            return

        # Open edit window
        EditPlantWindow(self.root, plant_data, self._on_plant_edited)

    def _on_plant_edited(self, updated_plant_data: Dict) -> None:
        """Handle save from edit window - update database and regenerate PDF."""
        plant_name = updated_plant_data.get('scientific_name', 'Unknown')

        try:
            # Save to database
            if self.db.save_plant(updated_plant_data):
                # Regenerate PDF
                pdf_path = self.pdf_generator.generate_care_card(updated_plant_data)
                if pdf_path:
                    self.db.save_plant(updated_plant_data, pdf_path)
                    logger.info(f"Updated and regenerated card for: {plant_name}")

                    # Refresh lists
                    self._refresh_plant_list()
                    self._refresh_plant_dropdown()

                    # Show success in chat
                    self._add_chat_message(
                        "assistant",
                        f"Updated {plant_name} and regenerated care card.",
                        "agree"
                    )

                    # Open the regenerated PDF
                    self._open_file(pdf_path)
                else:
                    messagebox.showerror("Error", "Failed to regenerate PDF.")
            else:
                messagebox.showerror("Error", "Failed to save changes to database.")

        except Exception as e:
            logger.error(f"Error saving plant edits: {e}")
            messagebox.showerror("Error", f"Failed to save changes: {str(e)}")

    def _add_chat_message(self, sender: str, message: str, tag: str = None) -> None:
        """Add a message to the chat display."""
        self.chat_display.configure(state="normal")

        if self.chat_display.get("1.0", "end-1c"):  # If not empty, add newline
            self.chat_display.insert("end", "\n\n")

        prefix = "You: " if sender == "user" else "Assistant: "
        self.chat_display.insert("end", prefix, tag or sender)
        self.chat_display.insert("end", message)

        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")

    def _send_feedback(self) -> None:
        """Send feedback for verification."""
        feedback = self.feedback_entry.get().strip()
        if not feedback:
            return

        # Clear input
        self.feedback_entry.delete(0, 'end')

        # Add user message to chat
        self._add_chat_message("user", feedback, "user")

        # Disable send button during processing
        self.send_button.configure(state="disabled")
        self.root.update()

        try:
            # Get selected plant (if any)
            selected = self.plant_selector.get()
            selected_plant = None if selected == "All Plants" else selected

            # Get all plants data for context
            plants_data = self.db.get_all_plants()

            # Verify feedback
            result = self.feedback_verifier.verify_feedback(feedback, plants_data, selected_plant)

            # Add assistant response to chat
            response_text = result.get('response_text', 'Sorry, something went wrong.')
            self._add_chat_message("assistant", response_text, "assistant")

            # Process any corrections
            corrections = result.get('corrections', [])
            for correction in corrections:
                self._add_correction_to_pending(correction)

        except Exception as e:
            logger.error(f"Error sending feedback: {e}")
            self._add_chat_message("assistant", f"Error: {str(e)}", "error")

        finally:
            self.send_button.configure(state="normal")

    def _add_correction_to_pending(self, correction: Dict) -> None:
        """Add a correction to the pending changes list."""
        # Check if this correction already exists
        for existing in self.pending_corrections:
            if (existing['plant'] == correction['plant'] and
                existing['field'] == correction['field']):
                # Update existing correction
                existing.update(correction)
                self._refresh_pending_list()
                return

        # Add new correction
        self.pending_corrections.append(correction)
        self._refresh_pending_list()

    def _refresh_pending_list(self) -> None:
        """Refresh the pending corrections display."""
        # Clear existing checkboxes
        for checkbox in self.correction_checkboxes:
            checkbox.destroy()
        self.correction_checkboxes.clear()
        self.correction_vars.clear()

        # Update label
        self.pending_label.configure(text=f"Pending Changes ({len(self.pending_corrections)}):")

        # Add checkboxes for each correction
        for i, correction in enumerate(self.pending_corrections):
            var = ctk.BooleanVar(value=True)
            self.correction_vars.append(var)

            # Build display text
            plant = correction.get('plant', 'Unknown')
            field = correction.get('field', 'Unknown')
            new_value = correction.get('recommended_value', '')[:50]
            if len(correction.get('recommended_value', '')) > 50:
                new_value += '...'

            verification = correction.get('verification', 'unknown')
            icon = "[OK]" if verification == 'agree' else "[?]"

            display_text = f"{icon} {plant} - {field}: \"{new_value}\""

            checkbox = ctk.CTkCheckBox(
                self.pending_list,
                text=display_text,
                variable=var,
                font=ctk.CTkFont(size=10),
                command=self._update_apply_button
            )
            checkbox.grid(row=i, column=0, pady=2, sticky="w")
            self.correction_checkboxes.append(checkbox)

        # Update apply button state
        self._update_apply_button()

    def _update_apply_button(self) -> None:
        """Enable/disable apply button based on selections."""
        any_selected = any(var.get() for var in self.correction_vars)
        self.apply_button.configure(state="normal" if any_selected else "disabled")

    def _apply_corrections(self) -> None:
        """Apply selected corrections to database and regenerate PDFs."""
        # Get selected corrections
        selected_corrections = [
            self.pending_corrections[i]
            for i, var in enumerate(self.correction_vars)
            if var.get()
        ]

        if not selected_corrections:
            return

        # Group corrections by plant
        plants_to_update = {}
        for correction in selected_corrections:
            plant_name = correction['plant']
            if plant_name not in plants_to_update:
                plants_to_update[plant_name] = {}
            plants_to_update[plant_name][correction['field']] = correction['recommended_value']

        # Apply changes
        self.apply_button.configure(state="disabled")
        self.root.update()

        updated_plants = []
        try:
            for plant_name, field_updates in plants_to_update.items():
                # Get current plant data
                plant_data = self.db.get_plant(plant_name)
                if not plant_data:
                    logger.warning(f"Plant not found: {plant_name}")
                    continue

                # Apply field updates
                for field, value in field_updates.items():
                    plant_data[field] = value

                # Save to database
                if self.db.save_plant(plant_data):
                    # Regenerate PDF
                    pdf_path = self.pdf_generator.generate_care_card(plant_data)
                    if pdf_path:
                        self.db.save_plant(plant_data, pdf_path)
                        updated_plants.append(plant_name)
                        logger.info(f"Updated and regenerated card for: {plant_name}")

            # Remove applied corrections from pending list
            self.pending_corrections = [
                c for i, c in enumerate(self.pending_corrections)
                if not self.correction_vars[i].get()
            ]
            self._refresh_pending_list()

            # Refresh plant list and dropdown
            self._refresh_plant_list()
            self._refresh_plant_dropdown()

            # Show success message in chat
            if updated_plants:
                msg = f"Applied changes and regenerated cards for: {', '.join(updated_plants)}"
                self._add_chat_message("assistant", msg, "agree")

        except Exception as e:
            logger.error(f"Error applying corrections: {e}")
            self._add_chat_message("assistant", f"Error applying changes: {str(e)}", "error")

        finally:
            self._update_apply_button()

    def _clear_corrections(self) -> None:
        """Clear all pending corrections."""
        self.pending_corrections.clear()
        self._refresh_pending_list()

    def _update_status(self, message: str, color: str = PRIMARY_COLOR) -> None:
        """
        Update status label.

        Args:
            message: Status message to display
            color: Text color
        """
        self.status_label.configure(text=message, text_color=color)
        self.root.update()

    def _generate_card(self) -> None:
        """Generate a care card for the entered plant."""
        scientific_name = self.name_entry.get().strip()

        # Normalize scientific name to proper casing
        scientific_name = normalize_scientific_name(scientific_name)

        # Validate input
        if not scientific_name:
            self._update_status("Please enter a scientific name", ERROR_COLOR)
            messagebox.showwarning("Input Required", "Please enter a scientific name")
            return

        # Disable button during generation
        self.generate_button.configure(state="disabled")
        self._update_status("Searching...", PRIMARY_COLOR)

        try:
            # Check database first
            plant_data = self.db.get_plant(scientific_name)

            if not plant_data:
                # Fetch from API
                logger.info(f"Plant '{scientific_name}' not in database, fetching from API")
                plant_data = self.api_fetcher.fetch_plant_data(scientific_name)
                logger.info(f"API returned data: {plant_data}")

                # Check for errors
                if plant_data.get('error'):
                    error_msg = plant_data['error']
                    self._update_status(f"Error: {error_msg}", ERROR_COLOR)
                    messagebox.showerror("Error", error_msg)
                    return

                # Save to database
                logger.info("About to save plant to database")
                save_result = self.db.save_plant(plant_data)
                logger.info(f"Database save result: {save_result}")

            # Generate PDF
            self._update_status("Creating PDF...", PRIMARY_COLOR)
            logger.info(f"Plant data to PDF: {plant_data}")
            pdf_path = self.pdf_generator.generate_care_card(plant_data)
            logger.info(f"PDF generation result: {pdf_path}")

            if pdf_path:
                # Update database with PDF path
                self.db.save_plant(plant_data, pdf_path)

                # Success - status update and auto-open (no annoying dialog)
                self._update_status("Card created!", SUCCESS_COLOR)

                # Open PDF
                self._open_file(pdf_path)

                # Clear input and refresh list
                self.name_entry.delete(0, 'end')
                self._refresh_plant_list()
                self._refresh_plant_dropdown()
            else:
                self._update_status("PDF generation failed", ERROR_COLOR)
                messagebox.showerror("Error", "Failed to generate PDF. Check logs for details.")

        except Exception as e:
            import traceback
            logger.error(f"Error generating card: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self._update_status("Error occurred", ERROR_COLOR)
            messagebox.showerror("Error", f"An unexpected error occurred:\n{str(e)}")

        finally:
            self.generate_button.configure(state="normal")

            # Reset status after 3 seconds
            self.root.after(3000, lambda: self._update_status("Ready", PRIMARY_COLOR))

    def _regenerate_card(self, scientific_name: str) -> None:
        """
        Regenerate a care card for an existing plant.

        Args:
            scientific_name: Scientific name of the plant
        """
        self.name_entry.delete(0, 'end')
        self.name_entry.insert(0, scientific_name)
        self._generate_card()

    def _import_csv(self) -> None:
        """Import plant data from CSV file."""
        file_path = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if not file_path:
            return

        self._update_status("Importing CSV...", PRIMARY_COLOR)
        self.root.update()

        try:
            imported_count, errors = self.db.import_from_csv(file_path)

            # Show results
            if errors:
                error_msg = "\n".join(errors[:10])  # Show first 10 errors
                if len(errors) > 10:
                    error_msg += f"\n... and {len(errors) - 10} more errors"

                messagebox.showwarning(
                    "Import Completed with Errors",
                    f"Imported {imported_count} plants\n\nErrors:\n{error_msg}"
                )
            else:
                messagebox.showinfo(
                    "Import Successful",
                    f"Successfully imported {imported_count} plants!"
                )

            # Refresh list and dropdown
            self._refresh_plant_list()
            self._refresh_plant_dropdown()
            self._update_status(f"Imported {imported_count} plants", SUCCESS_COLOR)

            # Reset status after 3 seconds
            self.root.after(3000, lambda: self._update_status("Ready", PRIMARY_COLOR))

        except Exception as e:
            logger.error(f"CSV import error: {e}")
            messagebox.showerror("Import Error", f"Failed to import CSV:\n{str(e)}")
            self._update_status("Import failed", ERROR_COLOR)

    def _export_catalog(self) -> None:
        """Export all plants to a single catalog PDF."""
        # Get all plants from database
        plants = self.db.get_all_plants()

        if not plants:
            messagebox.showinfo("No Plants", "No plants in database to export.")
            return

        self._update_status("Generating catalog...", PRIMARY_COLOR)
        self.root.update()

        try:
            # Generate catalog PDF
            pdf_path = self.pdf_generator.generate_catalog_pdf(plants)

            if pdf_path:
                self._update_status(f"Catalog created ({len(plants)} plants)", SUCCESS_COLOR)
                messagebox.showinfo(
                    "Catalog Created",
                    f"Successfully created catalog with {len(plants)} plants.\n\n"
                    f"Saved to: {pdf_path}"
                )
                # Open the PDF
                self._open_file(pdf_path)
            else:
                self._update_status("Catalog generation failed", ERROR_COLOR)
                messagebox.showerror("Error", "Failed to generate catalog PDF. Check logs for details.")

        except Exception as e:
            logger.error(f"Catalog export error: {e}")
            self._update_status("Export failed", ERROR_COLOR)
            messagebox.showerror("Export Error", f"Failed to export catalog:\n{str(e)}")

        finally:
            # Reset status after 3 seconds
            self.root.after(3000, lambda: self._update_status("Ready", PRIMARY_COLOR))

    def _open_file(self, file_path: str) -> None:
        """
        Open a file with the default system application.

        Args:
            file_path: Path to file to open
        """
        try:
            import subprocess
            subprocess.run(['open', file_path], check=True)
        except Exception as e:
            logger.warning(f"Failed to open file automatically: {e}")

    def run(self) -> None:
        """Start the application."""
        logger.info("Starting application")
        self.root.mainloop()

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point for the application."""
    try:
        # Check if API key is configured
        if ANTHROPIC_API_KEY == "sk-ant-...":
            logger.warning("API key not configured")
            messagebox.showwarning(
                "API Key Required",
                "Please set your Anthropic API key in the script.\n\n"
                "Edit care_card_generator.py and replace:\n"
                "ANTHROPIC_API_KEY = \"sk-ant-...\"\n\n"
                "You can still use the app to import CSV data and regenerate "
                "cards for existing plants."
            )

        # Check if logo exists
        if not os.path.exists(LOGO_PATH):
            logger.warning(f"Logo file not found: {LOGO_PATH}")
            messagebox.showwarning(
                "Logo Not Found",
                f"Logo file not found: {LOGO_PATH}\n\n"
                "PDFs will be generated without the logo.\n"
                "Place 'Small Version.png' in the app directory."
            )

        # Start application
        app = CareCardGeneratorApp()
        app.run()

    except Exception as e:
        logger.error(f"Application error: {e}")
        messagebox.showerror("Fatal Error", f"Application failed to start:\n{str(e)}")

if __name__ == "__main__":
    main()
