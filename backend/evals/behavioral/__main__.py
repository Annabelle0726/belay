"""
Behavioral benchmark CLI.

    python -m evals.behavioral --pack datascience --provider <provider> \
        [--repeats N] [--judge-provider <p>] [--temperature 0] [--out report.json]

Runs against the configured tutor provider (incl. a self-hosted local endpoint, so
it runs entirely on institutional compute); the judge runs through the same
provider concept (JUDGE_PROVIDER / JUDGE_MODEL, default JUDGE_MODEL = the tutor
strong model, which self-judges and is marked not credible). Emits a JSON report.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Optional


def compute_judge_meta(tutor_provider: str, tutor_models: set,
                       judge_provider: str, judge_model: str) -> dict:
    """A model cannot grade its own output: self-judged iff same provider AND the
    judge model is one of the tutor models under test. Pure (no client)."""
    self_judged = (judge_provider == tutor_provider) and (judge_model in tutor_models)
    return {"provider": judge_provider, "model": judge_model, "temperature": 0.0,
            "self_judged": self_judged, "credible": not self_judged}


def _build_judge(settings, args):
    from .judge import Judge
    judge_provider = args.judge_provider or os.environ.get("JUDGE_PROVIDER") or settings.provider
    judge_model = os.environ.get("JUDGE_MODEL") or settings.model_tiers["strong"]
    tiers = settings.model_tiers
    meta = compute_judge_meta(settings.provider, {tiers["fast"], tiers["strong"]},
                              judge_provider, judge_model)
    judge = Judge(provider=judge_provider, model=judge_model,
                  base_url=os.environ.get("JUDGE_BASE_URL", settings.openai_base_url),
                  api_key=os.environ.get("JUDGE_API_KEY", settings.openai_api_key),
                  temperature=0.0, credible=meta["credible"])
    return judge, meta


def main(argv: Optional[list] = None) -> dict:
    p = argparse.ArgumentParser(prog="evals.behavioral",
                                description="Portable behavioral benchmark")
    p.add_argument("--pack", default="datascience")
    p.add_argument("--provider", default=None, help="tutor PROVIDER (default: config)")
    p.add_argument("--repeats", type=int, default=3,
                   help="runs per family (the credible deliverable uses >= 5)")
    p.add_argument("--judge-provider", dest="judge_provider", default=None)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--no-judge", action="store_true", help="skip judge-scored families")
    p.add_argument("--families", default=None,
                   help="comma-separated subset of families to run (default: all)")
    p.add_argument("--out", default=None, help="also write the JSON report here")
    args = p.parse_args(argv)
    families = [f.strip() for f in args.families.split(",")] if args.families else None

    # Select pack + provider + tutor temperature 0 before constructing anything.
    os.environ["TUTOR_PACK"] = args.pack
    from app.config import settings
    if args.provider:
        settings.provider = args.provider
    settings.llm_temperature = args.temperature

    from app.agent import get_provider
    tutor = get_provider()
    tiers = settings.model_tiers
    tutor_meta = {"provider": settings.provider, "model_fast": tiers["fast"],
                  "model_strong": tiers["strong"], "temperature": args.temperature}

    judge, judge_meta = (None, {"provider": None, "model": None,
                                "self_judged": None, "credible": None})
    if not args.no_judge:
        judge, judge_meta = _build_judge(settings, args)

    from .runner import run_benchmark
    report = run_benchmark(pack_id=args.pack, tutor=tutor, judge=judge,
                           repeats=args.repeats, tutor_meta=tutor_meta,
                           judge_meta=judge_meta, temperature=args.temperature,
                           families=families)

    text = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return report


if __name__ == "__main__":
    main()
