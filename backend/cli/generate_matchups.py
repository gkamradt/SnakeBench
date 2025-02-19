#!/usr/bin/env python3
"""
This script generates battle matchups for LLM Snake Arena.

Two modes are supported:
1. all: Generate all unique combinations from the model list, each repeated as specified.
2. single: Generate matchups with a fixed model (provided via --model) against all other models from the input file.

Usage Examples:
-------------
Generate all matchups from model_lists.txt for 3 rounds and output to matchups.txt:
    python cli/generate_matchups.py --mode all --rounds 3

Generate matchups for a single fixed model against all other models:
    python cli/generate_matchups.py --mode single --model my_fixed_model --rounds 3
"""

import argparse
import itertools
import sys

def read_models(filename):
    """Reads models from a file, ignoring blank lines."""
    try:
        with open(filename, 'r') as f:
            models = [line.strip() for line in f if line.strip()]
        return models
    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        sys.exit(1)

def generate_all_combinations(models, rounds):
    """
    Generates all unique matchup combinations from the list of models.
    Each matchup is repeated 'rounds' times.
    """
    matchups = []
    # itertools.combinations returns unique pairs (order doesn't matter).
    for model_a, model_b in itertools.combinations(models, 2):
        for _ in range(rounds):
            matchups.append(f"{model_a} {model_b}")
    return matchups

def generate_single_matchups(fixed_model, models, rounds):
    """
    Generates matchups where the fixed_model battles every other model in the list.
    Each matchup is repeated 'rounds' times.
    """
    matchups = []
    for model in models:
        if model == fixed_model:
            continue  # Skip the fixed model if it appears in the list.
        for _ in range(rounds):
            matchups.append(f"{fixed_model} {model}")
    return matchups

def main():
    parser = argparse.ArgumentParser(
        description="Generate model battle selection matchups for the LLM Snake Arena."
    )
    parser.add_argument(
        '--mode',
        choices=['all', 'single'],
        default='all',
        help="Mode to generate matchups. 'all' for all combinations; 'single' for a fixed model vs all others."
    )
    parser.add_argument(
        '--model',
        type=str,
        help="Fixed model name (required for 'single' mode)."
    )
    parser.add_argument(
        '--rounds',
        type=int,
        default=1,
        help="Number of rounds to generate for each matchup combination (default: 1)."
    )
    parser.add_argument(
        '--input',
        type=str,
        default='model_lists.txt',
        help="Input file containing the list of models (default: model_lists.txt)."
    )
    parser.add_argument(
        '--output',
        type=str,
        default='matchups.txt',
        help="Output file to write matchups (default: matchups.txt)."
    )

    args = parser.parse_args()

    models = read_models(args.input)
    if not models:
        print("No models found in the input file.")
        sys.exit(1)

    if args.mode == 'single':
        if not args.model:
            print("Error: --model argument must be specified in 'single' mode.")
            sys.exit(1)
        if args.model not in models:
            print(f"Warning: Fixed model '{args.model}' not found in the input list. It will still be used as the fixed model.")
        matchups = generate_single_matchups(args.model, models, args.rounds)
    else:
        matchups = generate_all_combinations(models, args.rounds)

    try:
        with open(args.output, 'w') as f:
            for matchup in matchups:
                f.write(matchup + "\n")
        print(f"Matchups generated and written to {args.output}")
    except Exception as e:
        print(f"Error writing to output file {args.output}: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()