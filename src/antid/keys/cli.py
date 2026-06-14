"""Command-line interface (CLI) for KB validation and reasoning.

Provides two main subcommands:
1. validate: Performs strict validation on a KB directory.
2. reason: Runs deterministic reasoning over observed traits.
"""

import argparse
import json
import sys
import os
from .kb_loader import load_kb
from .key_reasoner import reason_over_traits
from .reasoning_adapter import build_reasoning_evidence_packet


def run_validate(args) -> int:
    """Runs the KB validation subcommand."""
    try:
        kb_dir = args.kb_dir
        if not kb_dir:
            print(json.dumps({"status": "error", "message": "KB directory path is required."}, indent=2))
            return 1
            
        if not os.path.isdir(kb_dir):
            print(json.dumps({"status": "error", "message": f"KB directory does not exist: {kb_dir}"}, indent=2))
            return 1

        kb = load_kb(kb_dir)
        
        # Build success payload
        output = {
            "status": "success",
            "message": f"Knowledge base validation passed for '{kb_dir}'.",
            "summary": {
                "source_manifest_id": list(kb["valid_source_ids"]),
                "traits_count": len(kb["trait_ids"]),
                "taxa_count": len(kb["taxon_ids"]),
                "couplets_count": len(kb["couplets"]),
            }
        }
        print(json.dumps(output, indent=2))
        return 0
    except Exception as e:
        output = {
            "status": "error",
            "message": f"KB validation failed: {e}"
        }
        print(json.dumps(output, indent=2), file=sys.stderr)
        return 1


def run_reason(args) -> int:
    """Runs the taxonomic reasoning subcommand."""
    try:
        kb_dir = args.kb_dir
        traits_file = args.observed_traits

        if not kb_dir:
            print(json.dumps({"status": "error", "message": "KB directory path is required."}, indent=2))
            return 1

        if not traits_file:
            print(json.dumps({"status": "error", "message": "Observed traits file path is required."}, indent=2))
            return 1

        if not os.path.exists(traits_file):
            print(json.dumps({"status": "error", "message": f"Observed traits file not found: {traits_file}"}, indent=2))
            return 1

        # Load observed traits
        try:
            with open(traits_file, "r", encoding="utf-8") as f:
                observed_traits = json.load(f)
        except Exception as e:
            print(json.dumps({"status": "error", "message": f"Failed to parse observed traits JSON: {e}"}, indent=2))
            return 1

        # Restructure/resolve candidate_taxa list
        candidates = None
        if args.candidate_taxa:
            # Flatten potential comma-separated values
            candidates = []
            for c in args.candidate_taxa:
                if "," in c:
                    candidates.extend([x.strip() for x in c.split(",") if x.strip()])
                else:
                    candidates.append(c.strip())

        # Perform reasoning
        result = reason_over_traits(
            kb_dir_or_dict=kb_dir,
            observed_traits=observed_traits,
            candidate_taxa=candidates,
            view_type=args.view_type,
        )

        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        output = {
            "status": "error",
            "message": f"Reasoning failed: {e}"
        }
        print(json.dumps(output, indent=2), file=sys.stderr)
        return 1


def run_integrate(args) -> int:
    """Runs the prediction-KB reasoning integration subcommand."""
    try:
        kb_dir = args.kb_dir
        model_file = args.model_output

        if not kb_dir:
            print(json.dumps({"status": "error", "message": "KB directory path is required."}, indent=2))
            return 1

        if not model_file:
            print(json.dumps({"status": "error", "message": "Model output file path is required."}, indent=2))
            return 1

        if not os.path.exists(model_file):
            print(json.dumps({"status": "error", "message": f"Model output file not found: {model_file}"}, indent=2))
            return 1

        # Load model output
        try:
            with open(model_file, "r", encoding="utf-8") as f:
                model_output = json.load(f)
        except Exception as e:
            print(json.dumps({"status": "error", "message": f"Failed to parse model output JSON: {e}"}, indent=2))
            return 1

        # Determine filter setting
        candidate_taxa_from_visual = not args.no_candidate_filter

        # Run integration adapter
        result = build_reasoning_evidence_packet(
            kb_dir_or_dict=kb_dir,
            model_output=model_output,
            candidate_taxa_from_visual=candidate_taxa_from_visual
        )

        print(json.dumps(result, indent=2))
        return 0
    except Exception as e:
        output = {
            "status": "error",
            "message": f"Integration failed: {e}"
        }
        print(json.dumps(output, indent=2), file=sys.stderr)
        return 1


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="KeyAgent-Ant Taxonomic KB Validation & Reasoning Harness CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")

    # Validate subcommand
    validate_parser = subparsers.add_parser("validate", help="Validate a KB directory for schema and topology correctness.")
    validate_parser.add_argument(
        "--kb-dir",
        type=str,
        required=True,
        help="Path to the taxonomic KB directory (containing YAMLs and rule JSON)."
    )

    # Reason subcommand
    reason_parser = subparsers.add_parser("reason", help="Run deterministic reasoning over observed traits.")
    reason_parser.add_argument(
        "--kb-dir",
        type=str,
        required=True,
        help="Path to the taxonomic KB directory."
    )
    reason_parser.add_argument(
        "--observed-traits",
        type=str,
        required=True,
        help="Path to a JSON file containing observed traits."
    )
    reason_parser.add_argument(
        "--candidate-taxa",
        type=str,
        nargs="*",
        help="Optional list of taxon_id or scientific_name values to restrict candidate evaluation."
    )
    reason_parser.add_argument(
        "--view-type",
        type=str,
        help="Optional current image view (e.g., 'head', 'profile', 'dorsal') to prioritize missing traits."
    )

    # Integrate subcommand
    integrate_parser = subparsers.add_parser("integrate", help="Integrate model predictions with KB reasoning.")
    integrate_parser.add_argument(
        "--kb-dir",
        type=str,
        required=True,
        help="Path to the taxonomic KB directory."
    )
    integrate_parser.add_argument(
        "--model-output",
        type=str,
        required=True,
        help="Path to a JSON file containing model visual predictions and observed traits."
    )
    integrate_parser.add_argument(
        "--no-candidate-filter",
        action="store_true",
        help="If specified, do not restrict evaluation to visual candidates."
    )

    args = parser.parse_args()

    if args.command == "validate":
        sys.exit(run_validate(args))
    elif args.command == "reason":
        sys.exit(run_reason(args))
    elif args.command == "integrate":
        sys.exit(run_integrate(args))


if __name__ == "__main__":
    main()
