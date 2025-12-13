# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A macOS desktop application that generates professional 4x6 inch plant care cards using Claude AI. The app features a CustomTkinter GUI, SQLite database for plant data storage, and PDF generation with ReportLab. The application can fetch plant care information via the Anthropic API or import data from CSV files.

## Development Commands

### Running the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Run the GUI application
python care_card_generator.py
```

### Testing

```bash
# Run core functionality tests (database, API, PDF generation)
python test_functionality.py

# Run advanced tests (CSV import, duplicates, multiple PDFs)
python test_advanced.py

# Run CSV import tests
python test_csv_import.py
```

### Building Distributable App

```bash
# Clean previous builds
rm -rf build dist

# Build macOS .app bundle (requires py2app)
python setup.py py2app

# Create DMG installer
hdiutil create -volname "Care Card Generator" \
  -srcfolder "dist/Leaf & Vessel Care Card Generator.app" \
  -ov -format UDZO \
  "CareCardGenerator-v1.0.dmg"

# Create ZIP archive
cd dist && zip -r "../CareCardGenerator-v1.0.zip" "Leaf & Vessel Care Card Generator.app"
```

### Database Operations

```bash
# Access SQLite database directly
sqlite3 plants.db

# Common queries:
# SELECT * FROM plants;
# SELECT scientific_name, common_name FROM plants ORDER BY created_at DESC;
# DELETE FROM plants WHERE scientific_name = 'Plant Name';
```

## Architecture

### Main Components

The application is structured as a single-file Python application (`care_card_generator.py`) with five major classes:

1. **DatabaseManager**: Manages all SQLite database operations
   - Stores plant data with schema: scientific_name, common_name, description, light, water, feeding, temperature, humidity, toxicity, pdf_path, created_at
   - Handles CSV import from two formats: original format and "Leaf & Vessel" format (with Botanical Name, Cat Friendly, Dog Friendly columns)
   - Uses UPSERT logic (INSERT ... ON CONFLICT DO UPDATE) to handle duplicates

2. **PlantDataFetcher**: Manages Claude API integration for fetching plant data
   - Fetches plant care data using the Anthropic API (Claude Sonnet 4 model)
   - Implements exponential backoff retry logic for rate limits and network errors
   - Parses JSON responses and handles API errors (authentication, timeout, connection, rate limit)
   - Prompt engineering: Requests specific JSON structure with 8 care fields plus error field

3. **FeedbackVerifier**: Verifies user feedback about plant care accuracy
   - Parses user feedback to identify plants and fields being corrected
   - Verifies corrections against authoritative horticultural sources via Claude API
   - Returns verification status (agree/disagree) with citations and reasoning
   - Supports both specific plant selection and natural language plant identification

4. **PDFGenerator**: Creates 4x6 inch landscape PDFs
   - Generates two-page PDFs: page 1 with plant care info, page 2 from Card_Back.pdf template
   - Layout: Title centered at top, scientific name (italic) and common name (bold) right-aligned, description in italics, care fields with labels
   - Implements text wrapping for long content to prevent overflow
   - Organizes output in `cards/` directory
   - Uses PyPDF (pypdf) to merge the care card with Card_Back.pdf

5. **CareCardGeneratorApp**: CustomTkinter GUI application
   - Main window: 1050x600px, two-column layout, non-resizable
   - Left panel: Scientific name input, Generate Card button, Import CSV button, scrollable plant history list
   - Right panel: Feedback chat interface for correcting plant care information
   - Workflow: Check database → Fetch from API if needed → Apply field length limits → Generate PDF → Save to database → Open PDF
   - History list is clickable to regenerate cards for existing plants
   - Feedback chat verifies corrections and allows batch application with PDF regeneration

### Key Data Flow

**Card Generation:**
```
User Input → Check Database → API Fetch (if not cached) → Apply Field Limits → Generate PDF → Save to Database → Display Result
```

**Feedback Correction:**
```
User Feedback → Parse & Identify Plants/Fields → Verify with Claude (citations) → Show Agree/Disagree → User Selects Changes → Update Database → Regenerate PDFs
```

The `apply_field_limits()` function truncates text intelligently at sentence or word boundaries to prevent overflow on cards. This is applied before saving to database AND before PDF generation.

### Field Length Limits

Defined in `FIELD_LIMITS` dictionary:
- description: 250 chars (2-3 sentences)
- light/water/feeding: 180 chars each
- temperature/humidity: 120 chars each
- toxicity: 150 chars

The `truncate_text()` utility function tries to break at sentence boundaries (. ! ?), then word boundaries, before resorting to hard truncation.

### CSV Import Formats

The app supports two CSV formats:

1. **Original format**: scientific_name, common_name, description, light, water, feeding, temperature, humidity, toxicity
2. **Leaf & Vessel format**: Botanical Name, Common Name, Description, Light, Water, Fertilizer, Temperature, Cat Friendly, Dog Friendly

The import logic auto-detects the format and maps Cat Friendly/Dog Friendly columns into a toxicity field.

### PDF Generation Details

- **Page size**: 6x4 inches landscape (432x288 points at 72 DPI)
- **Margins**: 0.25 inches (18 points)
- **Layout structure**:
  - Title "Plant Care Guide" centered at top
  - Scientific name (Helvetica-Oblique, 14pt) right-aligned
  - Common name (Helvetica-Bold, 11pt) right-aligned
  - Description (Helvetica-Oblique, 8pt) full-width with wrapping
  - Care fields (Helvetica-Bold 9pt labels, Helvetica 9pt values) in label-value pairs
- **Two-page output**: Page 1 is generated care card, Page 2 is Card_Back.pdf template

### Error Handling Patterns

The codebase uses comprehensive error handling:

- **API errors**: Catches RateLimitError, APITimeoutError, APIConnectionError, AuthenticationError separately with specific user messages
- **Database errors**: Try/except blocks with detailed logging and traceback
- **PDF generation**: Falls back to single-page PDF if Card_Back.pdf merge fails
- **GUI errors**: Shows messagebox dialogs to user with actionable error messages

### Configuration Constants

All configuration is at the top of `care_card_generator.py`:
- API_KEY, MODEL, timeouts, retry logic
- File paths for database, logo, card back, output directories
- PDF dimensions and margins
- Field length limits
- GUI dimensions and colors (including chat-specific colors)

## Important Notes

### API Key Security

The API key is currently hardcoded. This is visible in the source code. When modifying the app for distribution, consider implementing:
- Environment variable loading
- External config file (config.json)
- Secure keychain integration on macOS

### Database Schema Evolution

The app includes migration logic to add the `description` column to existing databases that may not have it. This pattern should be followed for future schema changes.

### Testing Approach

The codebase includes three test scripts that import classes from the main script. When making changes:
1. Run `test_functionality.py` to verify core features work
2. Run `test_advanced.py` to verify CSV import and bulk operations
3. Manually test the GUI for visual/interaction issues

### Distribution Notes

The app is packaged using py2app (setup.py). The bundle includes:
- All Python dependencies (no Python installation needed on target machines)
- SQLite database file, logo, Card_Back.pdf template
- ~81 MB total size

On first launch, macOS Gatekeeper will block the app (not code-signed). Users must right-click → Open to bypass.

### Known Patterns

1. **Error checking pattern**: `if plant_data.get('error'):` is used instead of `if 'error' in plant_data:` because API returns `"error": null` for valid responses

2. **Text truncation pattern**: Always use `apply_field_limits()` before saving to database AND before PDF generation to ensure consistency

3. **Database access pattern**: Use `conn.row_factory = sqlite3.Row` to return dict-like objects instead of tuples

4. **GUI updates**: Always call `self.root.update()` after changing status labels to force immediate redraw

5. **File organization**: PDFs are saved directly in the `cards/` directory

6. **Retry logic**: Exponential backoff using `RETRY_DELAY * (2 ** attempt)` for API rate limits

### Feedback Chat Feature

The right panel provides a chat interface for correcting plant care information:

1. **Plant Selection**: Users can select a specific plant from the dropdown or leave it as "All Plants" to let the AI identify plants from context
2. **Verification**: User feedback is verified against authoritative sources (universities, botanical gardens) via Claude API
3. **Agree/Disagree**: When Claude agrees with a correction, it's marked [OK]. When Claude disagrees, it shows [?] with citations explaining why
4. **User Choice**: Users can choose to apply corrections even when Claude disagrees - the pending changes list allows selective application
5. **Batch Updates**: Multiple corrections can be selected and applied at once, with automatic PDF regeneration for affected plants
