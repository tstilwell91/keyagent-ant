# KeyAgent-Ant Taxonomic KB Validation & Reasoning Harness

This document describes the design, commands, and options for running the KeyAgent-Ant deterministic taxonomic Knowledge Base (KB) validation and reasoning harness.

---

## Overview

The harness is a deterministic, unit-testable evaluation system designed to validate and reason over biological dichotomous keys and trait schemas without relying on stochastic language models. It operates directly on physical or digital specimen traits represented as flat observation files.

The harness parses and validates four core files that compose our taxonomic knowledge base:
1. `source_manifest.yaml` - Defines key provenance, taxonomic scope, geographic scope, and notes.
2. `trait_schema.yaml` - Outlines valid physical traits, their allowed values, body regions, and views.
3. `taxon_registry.yaml` - Registers valid taxonomic IDs, scientific names, and ranks.
4. `key_rules.json` - Encodes structured conditional rules composing the dichotomous decision tree.

---

## Architectural Features

### 1. Multi-Source Validation
To support diverse and complex keys, the validator does not assume a single `source_id`. It dynamically parses `source_manifest.yaml` supporting:
- Single string `source_id` keys
- Custom list-based `source_ids`
- Structured `sources` lists containing sub-dictionaries

Every rule loaded from `key_rules.json` is validated to ensure that its resolved source ID is explicitly registered within the manifest.

### 2. Strict Topological Verification
To verify dichotomous key integrity, the validator builds a directed graph of decision nodes (couplets) and enforces:
- **Rule Mutual Exclusion**: Every rule must define *either* `terminal_taxon_id` or `next_couplet`, but never both and never neither.
- **Unreachable Couplets**: All couplets defined in rules must be reachable via decision pathways starting from the root couplet `"1"`.
- **Cyclic Couplet Paths**: Detection of any loop/cycle in the couplet pathways, raising a `ValueError`.
- **Unknown next_couplet references**: Every `next_couplet` reference must point to a defined couplet in the ruleset. 
  - *Note*: Couplet `"7"` is explicitly whitelisted as a temporary POC behavior because the current ruleset covers only couplets 1 through 6, making `"7"` an out-of-scope boundary couplet.
  - **TODO**: Future versions should declare out-of-scope or boundary couplets in metadata (e.g., in `source_manifest.yaml`) rather than hard-coding them in the validator.

### 3. Explicit Condition Operators
The reasoner evaluates conditions using only four explicit, allowed operators:
- `equals`: Checks if the observed trait value is exactly the specified value.
- `not_equals`: Checks if the observed trait value differs from the specified value.
- `in`: Checks if the observed trait value is in a list of allowed values.
- `not_in`: Checks if the observed trait value is not in a list of allowed values.

### 4. Transparent Scoring Algorithm
Each candidate taxon is assigned a `raw_score` and a `normalized_score` calculated from its unique path starting from root couplet `"1"`.
- **Rule Evaluation**:
  - `+1` (Support): The rule matches all conditions.
  - `-1` (Conflict): The rule has at least one condition that does not match.
  - `0` (Unresolved): The rule has no mismatches, but has at least one condition whose trait is unobserved.
- **Score Calculation**:
  - The `raw_score` of a taxon is the sum of rule evaluations along its traversal path.
  - The `normalized_score` scales the raw score relative to the total number of rules on its path.

### 5. Recommended Next Action Output
Each reasoning output includes a `recommended_next_action` field to suggest the next traits to observe.
- *Note*: This is currently returned as a temporary string field.
- **TODO**: Future versions should return a structured object with `action_type`, `trait_id`, `reason`, and `visible_in_current_view` instead of a flat string.

---

## CLI Usage Instructions

You can run the harness using the virtual environment interpreter from the project root:

### 1. KB Validation
Validates the structural and topological correctness of the knowledge base directory:
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli validate \
  --kb-dir data/kb/poc_myrmicinae_mem
```

#### Example Output:
```json
{
  "status": "success",
  "message": "Knowledge base validation passed for 'data/kb/poc_myrmicinae_mem'.",
  "summary": {
    "source_manifest_id": [
      "mem_myrmicinae_genera_se_us"
    ],
    "traits_count": 11,
    "taxa_count": 6,
    "couplets_count": 6
  }
}
```

### 2. Taxonomic Reasoning
Runs the reasoning engine over an input JSON observation file:
```bash
PYTHONPATH=src .venv/bin/python -m antid.keys.cli reason \
  --kb-dir data/kb/poc_myrmicinae_mem \
  --observed-traits examples/kb/poc_observation_01.json
```

#### Advanced Options:
- `--candidate-taxa <name_or_id_list>`: Space/comma-separated candidate list to restrict candidate evaluation. Resolves aliases against registered scientific names case-insensitively, raising errors if ambiguous.
- `--view-type <view_name>`: Filters and categorizes missing traits by image view (e.g., `head`, `profile`, `dorsal`).

---

## Mock Examples

We provide two pre-configured mock observation files for demonstrating key paths:
- [poc_observation_01.json](file:///Users/tstilwel/Documents/phd/cs895_genai/2026/KeyAgent-Ant/keyagent-ant/examples/kb/poc_observation_01.json): Leads to supported `Crematogaster`.
- [poc_observation_02.json](file:///Users/tstilwel/Documents/phd/cs895_genai/2026/KeyAgent-Ant/keyagent-ant/examples/kb/poc_observation_02.json): Matches initial branching toward `Solenopsis`.
