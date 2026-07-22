# Gosha AI — stage decision memo template

```markdown
# DEC-[stage]-[number]: [decision]

- Date and decision owners:
- Study/build/provider/protocol versions:
- Frozen hypothesis and threshold:
- Planned / eligible / completed / excluded:
- Independent unit and denominator:
- Raw numerator/denominator:
- Missing data and operational failures:
- Supporting evidence IDs:
- Counterexamples and contradictions:
- Alternative explanations:
- Safety/privacy incidents:
- Result: SUPPORTED / MIXED / NOT SUPPORTED / INVALID:
- Decision: GO / HOLD / ITERATE / STOP / PIVOT:
- Allowed external wording:
- Prohibited inference:
- Required updates: evidence register / product discovery / README:
- Next experiment, owner and revisit date:
```

## Update loop

```text
private raw session/log
→ consent and redaction QA
→ aggregate/evidence card
→ metric result with n/N
→ signed decision memo
→ evidence-register update
→ product-discovery and README claim sync
```

До memo planned threshold не становится result. Изменённый protocol применяется только к новой version/cohort.
