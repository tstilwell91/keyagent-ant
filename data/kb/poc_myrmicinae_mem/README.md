# POC Taxonomic Knowledge Base: MEM Myrmicinae Key

This is a small proof-of-concept knowledge base extracted from one source:

- Source: Mississippi Entomological Museum, "Key to MYRMICINAE Genera in the southeastern United States"
- URL: https://mississippientomologicalmuseum.org.msstate.edu/Researchtaxapages/Formicidaepages/Myrmicinaekeys/Myrmicinekey.html
- Scope: Myrmicinae genera in the southeastern United States
- Extracted portion: couplets 1 through 6 only
- Status: needs human review

## Purpose

This KB is intended to support AI-guided taxonomic review. It does not replace a taxonomist. It provides structured rules that can help the system ask better questions, identify missing views, and explain why certain candidate taxa are supported or contradicted.

## Files

- `source_manifest.yaml`: source and scope metadata
- `trait_schema.yaml`: allowed morphology traits and values
- `taxon_registry.yaml`: terminal taxa reached in this POC slice
- `key_rules.json`: structured couplet rules

## Important limitations

- This is not a complete Myrmicinae key.
- This is not a global ant identification key.
- The geographic scope is southeastern United States.
- Rules are marked `needs_human_review`.
- Source line references are included for audit.
