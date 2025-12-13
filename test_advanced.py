#!/usr/bin/env python3
"""
Advanced test scenarios
"""

import sys
import os
import csv

sys.path.insert(0, os.path.dirname(__file__))
from care_card_generator import DatabaseManager, PlantDataFetcher, PDFGenerator, ANTHROPIC_API_KEY

def test_csv_import():
    """Test CSV import functionality"""
    print("\n" + "=" * 60)
    print("TESTING CSV IMPORT")
    print("=" * 60)

    # Create a test CSV
    csv_path = "test_plants.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['scientific_name', 'common_name', 'light', 'water', 'feeding', 'temperature', 'humidity', 'toxicity'])
        writer.writerow(['Pothos aureus', 'Golden Pothos', 'Low to bright indirect light', 'When soil is dry', 'Monthly in growing season', '60-85°F', '40-50%', 'Toxic to pets'])
        writer.writerow(['Sansevieria trifasciata', 'Snake Plant', 'Low to bright light', 'Every 2-3 weeks', 'Rarely', '55-85°F', 'Low', 'Toxic to cats and dogs'])

    db = DatabaseManager()
    imported_count, errors = db.import_from_csv(csv_path)

    if errors:
        print(f"✗ Import had errors: {errors}")
        return False

    print(f"✓ Imported {imported_count} plants successfully")

    # Verify they're in the database
    pothos = db.get_plant('Pothos aureus')
    if pothos and pothos['common_name'] == 'Golden Pothos':
        print("✓ Pothos verified in database")
    else:
        print("✗ Pothos not found or incorrect")
        return False

    # Clean up test CSV
    os.remove(csv_path)
    print("✓ CSV import test passed!")
    return True

def test_duplicate_handling():
    """Test that duplicates update instead of failing"""
    print("\n" + "=" * 60)
    print("TESTING DUPLICATE HANDLING")
    print("=" * 60)

    db = DatabaseManager()

    # Add a plant
    plant1 = {
        'scientific_name': 'Test plantus',
        'common_name': 'Test Plant v1',
        'light': 'Bright',
        'water': 'Weekly',
        'feeding': 'Monthly',
        'temperature': '70°F',
        'humidity': '50%',
        'toxicity': 'Non-toxic'
    }
    db.save_plant(plant1)

    # Update the same plant
    plant2 = {
        'scientific_name': 'Test plantus',
        'common_name': 'Test Plant v2 UPDATED',
        'light': 'Bright indirect',
        'water': 'Bi-weekly',
        'feeding': 'Bi-monthly',
        'temperature': '75°F',
        'humidity': '60%',
        'toxicity': 'Slightly toxic'
    }
    db.save_plant(plant2)

    # Verify it was updated, not duplicated
    retrieved = db.get_plant('Test plantus')
    if retrieved['common_name'] == 'Test Plant v2 UPDATED':
        print("✓ Duplicate correctly updated existing record")
        return True
    else:
        print(f"✗ Duplicate handling failed: {retrieved['common_name']}")
        return False

def test_multiple_pdfs():
    """Test generating multiple PDFs"""
    print("\n" + "=" * 60)
    print("TESTING MULTIPLE PDF GENERATION")
    print("=" * 60)

    db = DatabaseManager()
    pdf_generator = PDFGenerator()

    # Generate PDFs for plants already in database
    plants = db.get_all_plants()[:3]  # Test first 3

    if len(plants) < 2:
        print("⚠ Not enough plants in database, skipping")
        return True

    success_count = 0
    for plant in plants:
        pdf_path = pdf_generator.generate_care_card(plant)
        if pdf_path and os.path.exists(pdf_path):
            print(f"✓ Generated PDF for {plant['scientific_name']}")
            success_count += 1
        else:
            print(f"✗ Failed to generate PDF for {plant['scientific_name']}")

    if success_count == len(plants):
        print(f"✓ Successfully generated {success_count} PDFs")
        return True
    return False

if __name__ == "__main__":
    print("RUNNING ADVANCED TESTS")

    test1 = test_csv_import()
    test2 = test_duplicate_handling()
    test3 = test_multiple_pdfs()

    print("\n" + "=" * 60)
    if all([test1, test2, test3]):
        print("ALL ADVANCED TESTS PASSED! ✓")
        print("=" * 60)
        print("\n🎉 The application is fully functional and ready to use!")
    else:
        print("SOME TESTS FAILED")
        print("=" * 60)
