# Live-model investigation evaluation

ATLAS includes an optional runner for measuring a configured model against a
frozen synthetic incident dataset. It is separate from ordinary CI because it
can contact a paid or locally hosted model and model behavior can change without
a source-code change.

## Run the evaluation

Configure a provider that supports chat-completions JSON-schema responses:

```sh
export ATLAS_LLM_API_KEY='provider-secret'
export ATLAS_LLM_MODEL='exact-model-version'
export ATLAS_LLM_BASE_URL='https://provider.example/v1'
python -m scripts.evaluate_llm --output evaluation-result.json
```

The default input is
`tests/evaluations/live_model_cases.json`. The report records the exact model,
prompt version, dataset version, dataset SHA-256 digest, evidence digest for
every case, aggregate metrics, and individual pass/fail checks. It does not
write the model's full findings into the report.

## Metrics

- **model generated**: the response passed the strict schema and provenance
  contract instead of using the deterministic fallback;
- **classification correct**: the closed fault classification matches the
  expected label;
- **confidence correct**: supported, limited, or insufficient matches the
  expected evidence level;
- **citations complete**: every required event, mission, and document ID is
  present;
- **no prohibited claims**: frozen unsupported-cause phrases are absent; and
- **safe recommendation**: the output contains none of the forbidden approval,
  safety-override, or robot-command phrases.

Missing triggering events must produce `unknown` classification with
`insufficient` confidence. Any other model response fails the evidence contract
and uses the deterministic result.

## Interpretation limits

The prohibited-claim check is a transparent phrase-based regression measure.
It cannot detect every semantic hallucination. A published result applies only
to the recorded model, prompt, dataset, provider configuration, and run. Repeat
runs are needed to measure nondeterminism even though ATLAS requests temperature
zero. These results do not establish physical robot safety or reliability.

No live-model result is currently published in the repository. The checked-in
tests validate the runner and contract with a deterministic fake client; they
do not support a model-accuracy claim.
