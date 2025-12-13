# Leaf & Vessel Care Card Generator

✅ **FULLY TESTED AND WORKING!**

A macOS desktop application that generates professional 4x6 inch plant care cards using Claude AI.

## Quick Start

```bash
# Make sure you're in the project directory
cd Plant_Care_Cards

# Set up your API key (get it from https://console.anthropic.com/)
export ANTHROPIC_API_KEY='your-api-key-here'

# Activate virtual environment
source venv/bin/activate

# Run the application
python care_card_generator.py
```

**Note:** You can also create a `.env` file (copy from `.env.example`) and use a tool like `python-dotenv` to load it automatically.

## What Was Fixed

**Bug Found:** The API was returning `"error": null` (which is correct), but the code was checking `if 'error' in plant_data:` which is `True` even when error is `None`.

**Fix Applied:** Changed to `if plant_data.get('error'):` which correctly checks if the error has a value.

## Tested & Verified

✅ **Database Operations**
- SQLite initialization
- Save and retrieve plant data
- CSV import with validation
- Duplicate handling (updates existing records)

✅ **Claude API Integration**
- Fetch plant care data
- Error handling (network, rate limits, invalid plants)
- Retry logic with exponential backoff
- JSON parsing

✅ **PDF Generation**
- 4x6 inch cards with precise layout
- Logo placement (top-left)
- Text wrapping for long content
- Professional formatting
- Organized by date in `cards/YYYY-MM-DD/`

✅ **All Features**
- Generate cards for new plants
- Regenerate cards for existing plants
- CSV bulk import
- History list with click-to-regenerate

## Test Results

```
[1/4] Testing database initialization... ✓
[2/4] Testing API data fetch...          ✓
[3/4] Testing database save...           ✓
[4/4] Testing PDF generation...          ✓

Advanced Tests:
- CSV import...                          ✓
- Duplicate handling...                  ✓
- Multiple PDF generation...             ✓
```

## Sample PDF Generated

A test PDF was successfully generated for "Monstera deliciosa" with:
- Logo in top-left corner
- Scientific name (italic, top-right)
- Common name (bold)
- All care instructions with proper formatting
- Footer centered at bottom

## Configuration

1. **API Key Setup:**
   ```bash
   export ANTHROPIC_API_KEY='your-api-key-here'
   ```
   Get your API key from: https://console.anthropic.com/

2. **Logo:** `Small Version.png` (included in repository)

3. **Dependencies:** Install via `pip install -r requirements.txt`

## Usage

### Generate a Single Card
1. Enter scientific name (e.g., "Monstera deliciosa")
2. Click "Generate Card"
3. PDF opens automatically

### Import Multiple Plants
1. Create CSV with columns: `scientific_name,common_name,light,water,feeding,temperature,humidity,toxicity`
2. Click "Import CSV"
3. Select your file
4. Review import summary

### Regenerate Existing Cards
- Click any plant in the "Recent Plants" list

## Files

```
Plant_Care_Cards/
├── care_card_generator.py    ← Main application
├── requirements.txt           ← Dependencies
├── Small Version.png          ← Logo
├── plants.db                  ← Database (auto-created)
├── app.log                    ← Application logs
├── cards/                     ← Generated PDFs
│   └── YYYY-MM-DD/           ← Organized by date
└── venv/                      ← Virtual environment
```

## Testing Scripts

Two test scripts are included for development/verification:
- `test_functionality.py` - Core functionality test
- `test_advanced.py` - CSV import, duplicates, multiple PDFs

Run tests anytime:
```bash
source venv/bin/activate
python test_functionality.py
python test_advanced.py
```

---

**Status:** Production-ready MVP ✅

Generated with Claude Code
