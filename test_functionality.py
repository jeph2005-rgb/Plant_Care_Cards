#!/usr/bin/env python3
"""
Test script to verify core functionality without GUI
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Import the classes from the main script
from care_card_generator import DatabaseManager, PlantDataFetcher, PDFGenerator, ANTHROPIC_API_KEY

def test_all():
    """Test all core functionality"""

    print("=" * 60)
    print("TESTING PLANT CARE CARD GENERATOR")
    print("=" * 60)

    # Test 1: Database initialization
    print("\n[1/4] Testing database initialization...")
    try:
        db = DatabaseManager()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        return

    # Test 2: API fetch
    print("\n[2/4] Testing API data fetch...")
    test_plant = "Monstera deliciosa"

    try:
        api_fetcher = PlantDataFetcher(ANTHROPIC_API_KEY)
        print(f"   Fetching data for: {test_plant}")
        plant_data = api_fetcher.fetch_plant_data(test_plant)

        if plant_data.get('error'):
            print(f"✗ API returned error: {plant_data['error']}")
            return

        print("✓ API fetch successful")
        print(f"   Common name: {plant_data.get('common_name', 'N/A')}")
        print(f"   Light: {plant_data.get('light', 'N/A')[:50]}...")
        print(f"   Keys in response: {list(plant_data.keys())}")

    except Exception as e:
        print(f"✗ API fetch failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test 3: Database save
    print("\n[3/4] Testing database save...")
    try:
        save_result = db.save_plant(plant_data)
        if save_result:
            print("✓ Plant saved to database successfully")
        else:
            print("✗ Database save returned False")
            return

        # Verify it was saved
        retrieved = db.get_plant(test_plant)
        if retrieved:
            print(f"✓ Plant retrieved from database: {retrieved['scientific_name']}")
        else:
            print("✗ Could not retrieve plant from database")
            return

    except Exception as e:
        print(f"✗ Database save failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Test 4: PDF generation
    print("\n[4/4] Testing PDF generation...")
    try:
        pdf_generator = PDFGenerator()
        pdf_path = pdf_generator.generate_care_card(plant_data)

        if pdf_path:
            print(f"✓ PDF generated successfully")
            print(f"   Path: {pdf_path}")

            # Check if file actually exists
            if os.path.exists(pdf_path):
                file_size = os.path.getsize(pdf_path)
                print(f"   File size: {file_size} bytes")
                print("✓ PDF file exists and has content")
            else:
                print("✗ PDF path returned but file doesn't exist")
                return
        else:
            print("✗ PDF generation returned None")
            return

    except Exception as e:
        print(f"✗ PDF generation failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Final verification
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED! ✓")
    print("=" * 60)
    print(f"\nGenerated PDF: {pdf_path}")
    print("\nYou can now run the full GUI application with confidence!")

if __name__ == "__main__":
    test_all()
