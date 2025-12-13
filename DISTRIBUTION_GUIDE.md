# Leaf & Vessel Care Card Generator - Distribution Guide

## Overview

This guide explains how to distribute and install the Care Card Generator application on other macOS computers.

## What's Been Created

A standalone macOS application bundle has been created:
- **Location**: `dist/Leaf & Vessel Care Card Generator.app`
- **Size**: ~81 MB
- **Format**: Native macOS .app bundle
- **No Python installation required** on target machines

## Distribution Methods

### Method 1: Direct Copy (Recommended for Local Network)

1. **Copy the .app bundle** from the `dist/` folder
2. **Transfer to target Mac** using:
   - AirDrop
   - USB drive
   - Network file sharing
   - Cloud storage (Dropbox, Google Drive, iCloud)

3. **On the target Mac**:
   - Copy `Leaf & Vessel Care Card Generator.app` to `/Applications` folder
   - Or place it on the Desktop for easy access
   - Double-click to launch

### Method 2: Create a DMG Installer (Recommended for Distribution)

To create a professional disk image installer:

```bash
cd /Users/jason_phillips/Plant_Care_Cards

# Create DMG
hdiutil create -volname "Care Card Generator" \
  -srcfolder "dist/Leaf & Vessel Care Card Generator.app" \
  -ov -format UDZO \
  "CareCardGenerator-v1.0.dmg"
```

This creates a `.dmg` file that users can:
1. Download and double-click to mount
2. Drag the app to their Applications folder
3. Eject the disk image
4. Launch the app from Applications

### Method 3: Compress as ZIP (Simple Distribution)

```bash
cd /Users/jason_phillips/Plant_Care_Cards/dist
zip -r "CareCardGenerator-v1.0.zip" "Leaf & Vessel Care Card Generator.app"
```

Share the ZIP file, users can:
1. Download and double-click to extract
2. Move the .app to Applications
3. Launch

## First-Time Launch on Other Macs

### Important: macOS Gatekeeper

When users first launch the app on a new Mac, macOS Gatekeeper may block it because it's not signed with an Apple Developer certificate.

**Solution**:
1. **Right-click** (or Control+click) on the app
2. Select **"Open"** from the menu
3. Click **"Open"** in the security dialog
4. The app will launch and be trusted from now on

**Alternative**:
1. Go to **System Settings** > **Privacy & Security**
2. Find the message about the blocked app
3. Click **"Open Anyway"**

## Setting Up the API Key

Each installation needs an Anthropic API key configured:

1. Launch the application
2. The interface will show an error if no API key is set
3. Open the main Python file and locate line ~78
4. Replace `"sk-ant-..."` with the actual API key

**Better approach for distribution**: Create a settings file

1. Create a file named `config.json` in the same directory as the app:
```json
{
  "anthropic_api_key": "sk-ant-your-actual-key-here"
}
```

2. Modify the app to read from this file (requires code update)

## Required Files

The .app bundle includes:
- ✅ All Python dependencies (no Python installation needed)
- ✅ Database (`plants.db`)
- ✅ Logo (`Small Version.png`)
- ✅ Card back template (`Card_Back.pdf`)
- ✅ All required libraries

**Users only need**:
- macOS computer
- The .app file
- An Anthropic API key

## Desktop Icon

To add to Dock:
1. Open Applications folder
2. Find "Leaf & Vessel Care Card Generator"
3. Drag it to the Dock
4. It will stay there for quick access

## Testing the Distribution

Before distributing to others, test on a different Mac:

1. Copy the .app to another Mac (if available)
2. Launch it using the Gatekeeper bypass method
3. Verify all features work:
   - Database loads
   - PDFs generate correctly
   - Logo and Card_Back.pdf are found
   - API calls work (with valid key)

## Troubleshooting

### "App is damaged and can't be opened"
This happens when downloading from the internet. Solution:
```bash
xattr -cr "/Applications/Leaf & Vessel Care Card Generator.app"
```

### "No module named 'tkinter'"
The app bundle should include everything, but if this error occurs:
- Rebuild the .app bundle on a Mac with python-tk installed
- Or distribute with installation instructions for Python

### Missing Card_Back.pdf or Logo
The app looks for these files in its Resources folder. They should be included in the bundle, but if missing:
- Recreate the .app with updated setup.py to ensure resources are included

### Database Not Found
The .app includes the database. If it's not found:
- Check that `plants.db` is in the Resources folder of the .app bundle
- Or configure the app to create a new database in ~/Documents

## Rebuilding the Application

If you need to rebuild after code changes:

```bash
cd /Users/jason_phillips/Plant_Care_Cards
source venv/bin/activate

# Clean previous build
rm -rf build dist

# Rebuild
python setup.py py2app

# The new .app will be in dist/
```

## File Locations Inside .app Bundle

To inspect the bundle contents:
```bash
cd "dist/Leaf & Vessel Care Card Generator.app/Contents"
ls -la Resources/
```

This shows all included files:
- Python modules
- Database
- Images
- PDFs

## Distribution Checklist

Before distributing:
- [ ] Test the .app on your Mac
- [ ] Verify all 75 plants load correctly
- [ ] Generate a test PDF
- [ ] Test import functionality
- [ ] Compress as DMG or ZIP
- [ ] Create API key setup instructions
- [ ] Document the Gatekeeper bypass process
- [ ] Test on another Mac if possible

## Code Signing (Optional - Requires Apple Developer Account)

For wider distribution without Gatekeeper warnings:

1. **Get Apple Developer Account** ($99/year)
2. **Create Developer ID certificate**
3. **Sign the app**:
```bash
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: Your Name" \
  "dist/Leaf & Vessel Care Card Generator.app"
```
4. **Notarize with Apple**:
```bash
xcrun notarytool submit "CareCardGenerator-v1.0.zip" \
  --apple-id your@email.com \
  --team-id TEAMID \
  --password app-specific-password
```

This allows distribution without Gatekeeper warnings.

---

## Quick Start for End Users

**Installation**:
1. Download `Leaf & Vessel Care Card Generator.app`
2. Move to Applications folder
3. Right-click → Open (first time only)
4. Set up API key in config

**Usage**:
1. Launch app from Applications or Dock
2. Search for plants or import CSV
3. Generate PDFs
4. Find generated cards in the output folder

---

**Version**: 1.0.0
**Date**: November 28, 2025
**Platform**: macOS (Apple Silicon and Intel)
**Size**: ~81 MB
**Python Version**: Bundled (users don't need Python installed)
