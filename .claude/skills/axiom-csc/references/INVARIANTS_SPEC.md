# Axiom Invariants — 3-State Epistemic Specification

## Tri-State Logic

Every Base Entity evaluation resolves to exactly one state:

| State   | Meaning                                          | Action           |
|---------|--------------------------------------------------|------------------|
| TRUE    | Value extracted, rule satisfied                  | Continue         |
| FALSE   | Value extracted, rule violated                   | BLOCK            |
| UNKNOWN | Required value absent from context               | ASK (STRICT: halt) |

## Standard Invariants

### Financial Bounds
- `transaction_value` must satisfy `lte 10000` (configurable via `.axiom/invariants.yaml`)
- Applies to: invoice totals, payment amounts, transfer values

### Fail-Closed Guarantee (within the rule pipeline)
In STRICT mode, any UNKNOWN state halts execution immediately.
Claude must issue a single targeted micro-query naming the exact missing variable.
This guarantee applies once a valid `.axiom/invariants.yaml` is loaded. See the
[README][readme] and [v1.2.3 release notes][release] for what happens when no
policy file exists, or when it is empty, malformed or unreadable.

[readme]: ../../../../README.md
[release]: https://github.com/axiom-csc/axiom-skill/releases/tag/v1.2.3

## Configuring Custom Rules

Create `.axiom/invariants.yaml` in your project root:

```yaml
rules:
  - concept: transaction_value
    op: lte
    value: 50000
    action_on_fail: BLOCK
  - concept: percentage_value
    op: lte
    value: 100
    action_on_fail: BLOCK
```

Supported operators: `lte`, `gte`, `lt`, `gt`, `eq`

### Rule shapes

| Shape | Fields | Meaning |
|-------|--------|---------|
| Numeric bound | `concept`, `op`, `value`, `action_on_fail` | Fires if extracted value violates `op value` |
| Banned entity | `concept`, `banned: true`, `action_on_fail` | Fires if any matching entity is found |
| Required entity | `concept`, `required: true`, `action_on_missing` | Fires if the entity is not found in context |

### Disposition routing

`action_on_fail` (and `action_on_missing` on required rules) routes a firing
rule to one of two exit states:

| Value | Exit | Meaning |
|-------|------|---------|
| `BLOCK` _(default)_ | 1 | Halt the tool call; print `AxiomConstraintViolation` |
| `ASK` | 2 | Halt the tool call; print a targeted question for the user |

Missing or unrecognised values fall back to `BLOCK` so a typo cannot silently
downgrade a guardrail to ALLOW.
