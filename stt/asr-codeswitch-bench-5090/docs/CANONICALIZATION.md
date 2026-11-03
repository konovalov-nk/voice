# Canonicalization Rules

`display_text` is human-readable reference text.
`canonical_text` is normalized text used for scoring.

## Rules (v1)

1. Lowercase all text.
2. Keep letters and digits for `en`, `ru`, and `pl`.
3. Convert punctuation to spaces.
4. Collapse repeated whitespace to one space.
5. Trim leading and trailing spaces.

## Notes

- Keep this policy versioned. Any rule change should bump `dataset_version`.
- If needed, add explicit `yo/e` handling for Russian as a versioned step.
- Do not mix canonicalization versions inside one benchmark report.
