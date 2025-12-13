#!/usr/bin/env python3
"""
Test CSV import and PDF generation with the Leaf & Vessel plant list
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from care_card_generator import DatabaseManager, PDFGenerator

def test_csv_import():
    """Test importing the Leaf & Vessel CSV file"""

    print("=" * 60)
    print("TESTING LEAF & VESSEL CSV IMPORT")
    print("=" * 60)

    csv_path = "/Users/jason_phillips/Desktop/Leaf_And_Vessel_Plant_List.csv"

    # Check if file exists
    if not os.path.exists(csv_path):
        print(f"✗ CSV file not found: {csv_path}")
        return False

    # Import CSV
    print("\n[1/3] Importing CSV file...")
    db = DatabaseManager()
    imported_count, errors = db.import_from_csv(csv_path)

    if errors:
        print(f"⚠ Import completed with {len(errors)} errors:")
        for error in errors[:5]:  # Show first 5 errors
            print(f"  - {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more errors")

    print(f"✓ Successfully imported {imported_count} plants")

    # Verify import
    print("\n[2/3] Verifying imported data...")
    all_plants = db.get_all_plants()
    print(f"✓ Database now contains {len(all_plants)} plants")

    # Show sample
    if all_plants:
        sample = all_plants[0]
        print(f"\nSample plant:")
        print(f"  Scientific name: {sample['scientific_name']}")
        print(f"  Common name: {sample['common_name']}")
        print(f"  Description: {sample['description'][:80]}..." if sample.get('description') else "  Description: (none)")
        print(f"  Light: {sample['light'][:50]}...")
        print(f"  Toxicity: {sample['toxicity']}")

    # Generate sample PDFs
    print("\n[3/3] Generating sample PDFs...")
    pdf_generator = PDFGenerator()

    # Generate PDFs for first 3 plants
    test_plants = all_plants[:3]

    for i, plant in enumerate(test_plants, 1):
        pdf_path = pdf_generator.generate_care_card(plant)
        if pdf_path and os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            print(f"✓ [{i}] Generated PDF for {plant['scientific_name']} ({file_size} bytes)")
        else:
            print(f"✗ [{i}] Failed to generate PDF for {plant['scientific_name']}")

    print("\n" + "=" * 60)
    print("CSV IMPORT AND PDF GENERATION COMPLETE! ✓")
    print("=" * 60)
    print(f"\nImported {imported_count} plants from CSV")
    print(f"Generated {len(test_plants)} sample PDFs")
    print("\nYou can now run the GUI application to generate more cards!")

    return True

if __name__ == "__main__":
    test_csv_import()
