#!/usr/bin/env python3
"""
Update missing humidity information for plants in the database
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
from care_card_generator import DatabaseManager, ANTHROPIC_API_KEY, apply_field_limits
import anthropic

def fetch_humidity_info(scientific_name: str, api_key: str) -> str:
    """
    Fetch humidity information for a specific plant using Claude API.

    Args:
        scientific_name: Scientific name of the plant
        api_key: Anthropic API key

    Returns:
        Humidity information string or empty string if failed
    """
    try:
        client = anthropic.Anthropic(api_key=api_key)

        prompt = f"""You are an expert horticulturist. Provide the humidity requirements for this plant: {scientific_name}

Return ONLY the humidity information in a concise format (1-2 sentences maximum), such as:
- "40-60% relative humidity"
- "High humidity (60-80%); benefits from regular misting"
- "Tolerates average home humidity (40-50%)"
- "Low humidity tolerant; 30-50%"

If you cannot find reliable information, return: "Average home humidity (40-60%)"

Humidity information:"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
            timeout=30
        )

        humidity_info = message.content[0].text.strip()

        # Remove any quotes or extra formatting
        humidity_info = humidity_info.strip('"\'')

        return humidity_info

    except Exception as e:
        print(f"  Error fetching humidity for {scientific_name}: {e}")
        return ""

def update_missing_humidity():
    """Update all plants missing humidity information."""

    print("=" * 70)
    print("UPDATING MISSING HUMIDITY INFORMATION")
    print("=" * 70)

    # Check API key
    if ANTHROPIC_API_KEY == "sk-ant-...":
        print("Error: API key not configured")
        return

    db = DatabaseManager()

    # Get all plants missing humidity
    plants = db.get_all_plants()
    missing_humidity = [p for p in plants if not p.get('humidity') or p['humidity'].strip() == '']

    print(f"\nFound {len(missing_humidity)} plants missing humidity information")
    print(f"Total plants in database: {len(plants)}")

    if not missing_humidity:
        print("\nAll plants already have humidity information!")
        return

    # Confirm before proceeding
    response = input(f"\nUpdate humidity for {len(missing_humidity)} plants? (yes/no): ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return

    print("\nStarting updates...\n")

    success_count = 0
    error_count = 0

    for i, plant in enumerate(missing_humidity, 1):
        scientific_name = plant['scientific_name']
        common_name = plant.get('common_name', '')

        print(f"[{i}/{len(missing_humidity)}] {scientific_name}", end='')
        if common_name:
            print(f" ({common_name})", end='')
        print("...")

        # Fetch humidity info
        humidity_info = fetch_humidity_info(scientific_name, ANTHROPIC_API_KEY)

        if humidity_info:
            # Apply field limits
            limited_data = apply_field_limits({'humidity': humidity_info})
            humidity_info = limited_data['humidity']

            # Update the plant record
            plant['humidity'] = humidity_info
            if db.save_plant(plant):
                print(f"  ✓ Updated: {humidity_info}")
                success_count += 1
            else:
                print(f"  ✗ Failed to save to database")
                error_count += 1
        else:
            print(f"  ⚠ Could not fetch humidity info")
            error_count += 1

        # Rate limiting - be nice to the API
        if i < len(missing_humidity):
            time.sleep(1)  # Wait 1 second between requests

    # Summary
    print("\n" + "=" * 70)
    print("UPDATE COMPLETE")
    print("=" * 70)
    print(f"Successfully updated: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Total processed: {len(missing_humidity)}")

    if success_count > 0:
        print("\n✓ Database has been updated with humidity information!")

if __name__ == "__main__":
    update_missing_humidity()
