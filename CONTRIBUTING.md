# Contributing

Issues and small patches are welcome. This is a public instrument. A change should earn its place on the plate the way the existing readings did: a stated method, public data, tests, and limits written next to the result.

## Before you start

- Read [DESIGN.md](DESIGN.md). The plate is typographic: paper `#EFECE6`, ink `#141414`, one accent `#8C1D12`, IBM Plex Sans and Mono only. No emoji, no gradients, no second colour for long versus short.
- The planned increment is [docs/ROADMAP.md](docs/ROADMAP.md). A proposal that is already on that list is easier to review than a new kind of reading.
- Run the tests (no network):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q
```

## Pull requests

- Keep the change focused. A new reading needs tests and a README methodology note (or a link to one).
- Formulas that appear on GitHub should use `$...$` and `$$`, `\mathrm` rather than `\operatorname`, and no `#` inside maths. In prose write "USD 1,000" so a dollar sign does not open math mode.
- Do not edit `.github/workflows/`. If a workflow change is truly needed, add the proposed YAML under `docs/` (see [docs/github-workflow-sweep.yml](docs/github-workflow-sweep.yml), a copy kept in sync with the live workflow). The live file is the one that runs.
- Do not add `Co-authored-by` trailers, and do not mention AI tools in commits or in the copy.
- Do not invent placeholder numbers. An empty state is a sentence, not a fake reading.

There is no contributor licence agreement. The project is under the [MIT License](LICENSE).
