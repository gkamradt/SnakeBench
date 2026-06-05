#!/usr/bin/env python3
"""
Sync OpenRouter model catalog to the local database.

This script pulls the latest model information from OpenRouter's API and
upserts it into the models table. New models are auto-activated when they
pass baseline filters; otherwise they remain inactive and await evaluation.

Usage:
    python backend/cli/sync_openrouter_models.py [--api-key <key>]
"""

import os
import sys
import json
import argparse
import requests
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

# Add parent directory to path to import database modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database_postgres import get_connection
from services.webhook_service import send_new_model_webhook


def fetch_openrouter_models(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetch all models from OpenRouter API.

    Args:
        api_key: OpenRouter API key (optional, but recommended)

    Returns:
        List of model dictionaries from OpenRouter

    Raises:
        requests.RequestException: If API call fails
    """
    url = "https://openrouter.ai/api/v1/models"
    headers = {}

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print(f"Fetching models from OpenRouter API...")

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        models = data.get('data', [])

        print(f"✓ Fetched {len(models)} models from OpenRouter")
        return models

    except requests.RequestException as e:
        print(f"✗ Error fetching models from OpenRouter: {e}")
        raise


def normalize_model_data(openrouter_model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize OpenRouter model data to our database schema.

    Args:
        openrouter_model: Model data from OpenRouter API

    Returns:
        Dictionary with normalized fields for database insertion
    """
    # Extract pricing (OpenRouter uses per-token pricing)
    pricing = openrouter_model.get('pricing', {})

    # Convert to per-million tokens (OpenRouter may use different units)
    # OpenRouter pricing is typically in dollars per token, multiply by 1M
    prompt_price = pricing.get('prompt')
    completion_price = pricing.get('completion')

    # Handle BigNumberUnion (can be number or string)
    if isinstance(prompt_price, str):
        prompt_price = float(prompt_price)
    if isinstance(completion_price, str):
        completion_price = float(completion_price)

    # Convert to per-million if needed (OpenRouter uses per-token)
    pricing_input = prompt_price * 1_000_000 if prompt_price else None
    pricing_output = completion_price * 1_000_000 if completion_price else None

    # Extract other fields
    model_id = openrouter_model.get('id', '')
    name = openrouter_model.get('name', model_id)

    # Derive provider from model ID (format is usually "provider/model-name")
    provider = model_id.split('/')[0] if '/' in model_id else 'unknown'

    # Get context length and max completion tokens
    context_length = openrouter_model.get('context_length')
    top_provider = openrouter_model.get('top_provider', {})
    max_completion_tokens = top_provider.get('max_completion_tokens', context_length)

    # Store additional metadata as JSON
    metadata = {
        'canonical_slug': openrouter_model.get('canonical_slug'),
        'description': openrouter_model.get('description', ''),
        'architecture': openrouter_model.get('architecture', {}),
        'context_length': context_length,
        'supported_parameters': openrouter_model.get('supported_parameters', []),
        'created': openrouter_model.get('created'),
        'hugging_face_id': openrouter_model.get('hugging_face_id'),
    }

    return {
        'name': name,
        'provider': provider,
        'model_slug': model_id,
        'pricing_input': pricing_input,
        'pricing_output': pricing_output,
        'max_completion_tokens': max_completion_tokens,
        'metadata_json': json.dumps(metadata)
    }


def upsert_model(model_data: Dict[str, Any]) -> Tuple[Optional[int], bool]:
    """
    Insert or update a model in the database.

    Args:
        model_data: Normalized model data

    Returns:
        (Model ID if successful, is_new flag) — ID is None on failure/skip
    """
    # Skip Auto Router entirely
    if model_data.get('name') == 'Auto Router':
        print(f"  ⊘ Skipped: Auto Router (excluded from sync)")
        return None, False

    # Only auto-activate new models from these providers (OpenRouter slug
    # prefixes). All other providers are paused: they still get synced/upserted
    # but stay inactive until manually enabled.
    AUTO_ACTIVATE_PROVIDERS = {
        'openai',      # OpenAI
        'anthropic',   # Anthropic
        'google',      # Google
        'meta-llama',  # Meta
        'x-ai',        # xAI
    }

    def qualifies_for_auto_activation(data: Dict[str, Any]) -> bool:
        """Decide if a brand-new model should start as active."""
        provider = (data.get('provider') or '').lower()
        if provider not in AUTO_ACTIVATE_PROVIDERS:
            return False

        max_tokens = data.get('max_completion_tokens')
        price_in = data.get('pricing_input')

        return (
            max_tokens is not None and max_tokens >= 5000
            and price_in is not None and 0 < price_in <= 11
        )

    conn = get_connection()
    cursor = conn.cursor()
    is_new = False

    try:
        # Check if model already exists
        cursor.execute("""
            SELECT id, is_active, test_status, games_played
            FROM models
            WHERE model_slug = %s
        """, (model_data['model_slug'],))

        existing = cursor.fetchone()

        if existing:
            model_id = existing['id']
            is_active = existing['is_active']
            test_status = existing['test_status']
            games_played = existing['games_played']

            # Update pricing and metadata only, preserve status and stats
            cursor.execute("""
                UPDATE models
                SET name = %s,
                    provider = %s,
                    pricing_input = %s,
                    pricing_output = %s,
                    max_completion_tokens = %s,
                    metadata_json = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                model_data['name'],
                model_data['provider'],
                model_data['pricing_input'],
                model_data['pricing_output'],
                model_data['max_completion_tokens'],
                model_data['metadata_json'],
                model_id
            ))

            print(f"  ↻ Updated: {model_data['name']} (already has {games_played} games)")
        else:
            # Insert new model; auto-activate if it meets baseline filters
            is_active_default = qualifies_for_auto_activation(model_data)
            cursor.execute("""
                INSERT INTO models (
                    name, provider, model_slug,
                    pricing_input, pricing_output,
                    max_completion_tokens, metadata_json,
                    is_active, test_status,
                    discovered_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'untested', %s)
                RETURNING id
            """, (
                model_data['name'],
                model_data['provider'],
                model_data['model_slug'],
                model_data['pricing_input'],
                model_data['pricing_output'],
                model_data['max_completion_tokens'],
                model_data['metadata_json'],
                is_active_default,
                datetime.now().isoformat()
            ))

            result = cursor.fetchone()
            model_id = result['id'] if result else None
            is_new = True
            status_note = "auto-activated" if is_active_default else "inactive"
            print(f"  + Added: {model_data['name']} (new, untested, {status_note})")

        conn.commit()
        return model_id, is_new

    except Exception as e:
        print(f"  ✗ Error upserting model {model_data.get('name')}: {e}")
        conn.rollback()
        return None, False

    finally:
        conn.close()


def sync_models(api_key: Optional[str] = None) -> Dict[str, int]:
    """
    Main sync function to pull OpenRouter catalog and upsert models.

    Args:
        api_key: OpenRouter API key

    Returns:
        Dictionary with sync statistics
    """
    print("=" * 70)
    print("OpenRouter Model Sync")
    print("=" * 70)

    # Fetch models from OpenRouter
    try:
        openrouter_models = fetch_openrouter_models(api_key)
    except Exception as e:
        print(f"Failed to fetch models: {e}")
        return {'error': 1}

    # Process each model
    stats = {
        'total': len(openrouter_models),
        'added': 0,
        'updated': 0,
        'skipped': 0
    }

    print(f"\nProcessing {stats['total']} models...")

    for or_model in openrouter_models:
        try:
            # Normalize and upsert
            normalized = normalize_model_data(or_model)
            model_id, is_new = upsert_model(normalized)

            if model_id is None:
                stats['skipped'] += 1
                continue

            if is_new:
                stats['added'] += 1
                send_new_model_webhook(
                    model_id=model_id,
                    name=normalized['name'],
                    provider=normalized['provider'],
                    model_slug=normalized['model_slug'],
                    pricing_input=normalized.get('pricing_input'),
                    pricing_output=normalized.get('pricing_output'),
                    max_completion_tokens=normalized.get('max_completion_tokens'),
                )
            else:
                stats['updated'] += 1

        except Exception as e:
            print(f"  ✗ Error processing model: {e}")
            stats['skipped'] += 1

    # Print summary
    print(f"\n{'=' * 70}")
    print("Sync Complete")
    print(f"{'=' * 70}")
    print(f"Total models processed: {stats['total']}")
    print(f"New models added: {stats['added']}")
    print(f"Existing models updated: {stats['updated']}")
    print(f"Models skipped: {stats['skipped']}")

    print(f"{'=' * 70}\n")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Sync OpenRouter model catalog to local database"
    )
    parser.add_argument(
        '--api-key',
        type=str,
        help="OpenRouter API key (or set OPENROUTER_API_KEY env var)"
    )

    args = parser.parse_args()

    # Get API key from args or environment
    api_key = args.api_key or os.getenv('OPENROUTER_API_KEY')

    if not api_key:
        print("Warning: No API key provided. Some features may be limited.")
        print("Set OPENROUTER_API_KEY environment variable or use --api-key flag.")

    # Run sync
    sync_models(api_key=api_key)


if __name__ == "__main__":
    main()
