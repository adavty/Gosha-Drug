from __future__ import annotations

import json
import hashlib
import math
import platform
from collections import Counter, defaultdict
from pathlib import Path

from .models import Intent
from .provider import IntentProvider, OfflineProvider


def evaluate(
    path: str | Path,
    provider: IntentProvider | None = None,
    *,
    input_usd_per_million: float | None = None,
    output_usd_per_million: float | None = None,
) -> dict:
    provider = provider or OfflineProvider()
    raw_data = Path(path).read_bytes()
    rows = [json.loads(line) for line in raw_data.decode("utf-8").splitlines() if line.strip()]
    labels = {r["intent"] for r in rows}
    tp, fp, fn = Counter(), Counter(), Counter()
    slot_correct = slot_total = slot_cases = slot_cases_exact = correct = 0
    errors = []
    by_intent: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "correct": 0})
    confusion: dict[str, Counter] = defaultdict(Counter)
    error_taxonomy = Counter()
    slice_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "correct": 0})
    benchmark_slices: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "correct": 0})
    perturbation_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "correct": 0})
    material_intents = {
        Intent.MATERIAL_SAVE.value,
        Intent.MATERIAL_LIST.value,
        Intent.MATERIAL_FIND.value,
        Intent.MATERIAL_CORRECT.value,
        Intent.MATERIAL_DEACTIVATE.value,
    }
    usage_totals = Counter()
    measured_requests = 0
    for row in rows:
        pred = provider.parse(row["text"])
        if pred.usage is not None:
            measured_requests += 1
            for key in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "latency_ms"):
                value = getattr(pred.usage, key)
                if value is not None:
                    usage_totals[key] += value
        gold = row["intent"]
        product_slice = "material" if gold in material_intents else "out_of_scope" if gold == Intent.UNKNOWN.value else "deadline"
        slice_stats[product_slice]["n"] += 1
        benchmark_slice = row.get("slice")
        perturbation = row.get("perturbation")
        if benchmark_slice:
            benchmark_slices[benchmark_slice]["n"] += 1
        if perturbation:
            perturbation_stats[perturbation]["n"] += 1
        labels.add(pred.intent.value)
        confusion[gold][pred.intent.value] += 1
        by_intent[gold]["n"] += 1
        if pred.intent.value == gold:
            correct += 1
            tp[gold] += 1
            by_intent[gold]["correct"] += 1
            slice_stats[product_slice]["correct"] += 1
            if benchmark_slice:
                benchmark_slices[benchmark_slice]["correct"] += 1
            if perturbation:
                perturbation_stats[perturbation]["correct"] += 1
        else:
            fp[pred.intent.value] += 1
            fn[gold] += 1
            if gold in material_intents and pred.intent == Intent.UNKNOWN:
                kind = "missed_material_intent"
            elif gold == Intent.UNKNOWN.value and pred.intent.value in material_intents:
                kind = "unsafe_material_overclassification"
            else:
                kind = "missed_core_intent" if pred.intent == Intent.UNKNOWN and gold != Intent.UNKNOWN.value else "unsafe_overclassification" if gold == Intent.UNKNOWN.value else "intent_confusion"
            error_taxonomy[kind] += 1
            errors.append({"id": row["id"], "gold": gold, "predicted": pred.intent.value, "taxonomy": kind})
        gold_slots = row.get("slots", {})
        if gold_slots:
            slot_cases += 1
            slot_cases_exact += int(all(pred.slots.get(key) == value for key, value in gold_slots.items()))
        for key, value in gold_slots.items():
            slot_total += 1
            slot_correct += int(pred.slots.get(key) == value)
    f1s = []
    per_class = {}
    for label in sorted(labels):
        precision = tp[label] / (tp[label] + fp[label]) if tp[label] + fp[label] else 0
        recall = tp[label] / (tp[label] + fn[label]) if tp[label] + fn[label] else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        f1s.append(f1)
        per_class[label] = {"support": by_intent[label]["n"], "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
    accuracy = correct / len(rows)
    z = 1.959963984540054
    denominator = 1 + z * z / len(rows)
    centre = (accuracy + z * z / (2 * len(rows))) / denominator
    margin = z * math.sqrt((accuracy * (1 - accuracy) + z * z / (4 * len(rows))) / len(rows)) / denominator
    usage_report = None
    if measured_requests:
        usage_report = {
            "measured_requests": measured_requests,
            **{key: usage_totals[key] for key in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "latency_ms")},
            "mean_latency_ms": round(usage_totals["latency_ms"] / measured_requests, 1),
        }
        if input_usd_per_million is not None and output_usd_per_million is not None:
            usage_report["estimated_cost_usd"] = round(
                usage_totals["input_tokens"] * input_usd_per_million / 1_000_000
                + usage_totals["output_tokens"] * output_usd_per_million / 1_000_000,
                6,
            )
            usage_report["pricing_assumption_usd_per_million"] = {
                "input": input_usd_per_million,
                "output": output_usd_per_million,
            }
    provider_name = getattr(provider, "name", type(provider).__name__)
    provider_model = getattr(provider, "model", None)
    provider_label = f"{provider_name}:{provider_model}" if provider_model else provider_name
    is_perturbation_benchmark = "benchmark-v1" in Path(path).name
    if is_perturbation_benchmark:
        claim_limit = (
            "Synthetic perturbation benchmark: 30 semantic seeds x 10 surface transforms; "
            "not 300 independent cases, user data, or the canonical Bronze gate."
        )
    elif isinstance(provider, OfflineProvider):
        claim_limit = "Offline rules smoke test; not an LLM result and not the 300-case Bronze gate."
    else:
        claim_limit = "Model run on a controlled dataset; not user research, pilot evidence, or the 300-case Bronze gate."
    return {
        "dataset": Path(path).name,
        "dataset_kind": "synthetic_perturbation_benchmark" if is_perturbation_benchmark else "synthetic_challenge" if "challenge" in Path(path).name else "synthetic_smoke_test",
        "provider": provider_label,
        "reproducibility": {
            "evaluator_version": "1.4.0",
            "dataset_sha256": hashlib.sha256(raw_data).hexdigest(),
            "python": platform.python_version(),
            "rows": len(rows),
            "semantic_seeds": len({row.get("semantic_seed") for row in rows if row.get("semantic_seed")}),
        },
        "n": len(rows),
        "intent_accuracy": round(accuracy, 4),
        "intent_accuracy_wilson_95": [round(max(0, centre - margin), 4), round(min(1, centre + margin), 4)],
        "intent_macro_f1": round(sum(f1s) / len(f1s), 4),
        "slot_value_accuracy": round(slot_correct / slot_total, 4) if slot_total else None,
        "required_slots_case_exact_match": round(slot_cases_exact / slot_cases, 4) if slot_cases else None,
        "per_class": per_class,
        "slice_metrics": {
            name: {"n": values["n"], "intent_accuracy": round(values["correct"] / values["n"], 4)}
            for name, values in sorted(slice_stats.items())
        },
        "benchmark_slice_metrics": {
            name: {"n": values["n"], "intent_accuracy": round(values["correct"] / values["n"], 4)}
            for name, values in sorted(benchmark_slices.items())
        },
        "perturbation_metrics": {
            name: {"n": values["n"], "intent_accuracy": round(values["correct"] / values["n"], 4)}
            for name, values in sorted(perturbation_stats.items())
        },
        "confusion_matrix": {gold: dict(counts) for gold, counts in confusion.items()},
        "error_taxonomy": dict(error_taxonomy),
        "errors": errors,
        "llm_usage": usage_report,
        "claim_limit": claim_limit,
    }


def write_report(
    dataset: str | Path,
    output: str | Path,
    provider: IntentProvider | None = None,
    *,
    input_usd_per_million: float | None = None,
    output_usd_per_million: float | None = None,
) -> dict:
    report = evaluate(
        dataset, provider,
        input_usd_per_million=input_usd_per_million,
        output_usd_per_million=output_usd_per_million,
    )
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
