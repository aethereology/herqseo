"""Runnable entrypoint that builds a LoopService from env and serves the FastAPI
adapter. Requires the ``api`` extra. Not imported by the package or tests.

    pip install -e ".[api]"            # offline demo mode (no keys needed)
    pip install -e ".[api,openai,crawl]"   # real OpenAI + HTTP crawl
    uvicorn queryclear_agent_runtime.serve:build_app --factory --port 8080

Demo mode (no OPENAI_API_KEY / WORDPRESS_BASE_URL) uses offline fakes so the M0
loop is clickable end to end without credentials — useful as a sales demo. With
the env vars set, it wires the real OpenAI provider, HTTP crawler, and WordPress
(draft-only) publisher.
"""
from __future__ import annotations

import os
from decimal import Decimal

from .content import BrandVoice
from .metering import InMemoryBudgetRepository, ModelRequest, ModelResponse, TokenBudget, TokenMeter
from .publishing import PublishResult, StagingOnlyError
from .service import LoopService

_DEMO_HTML = (
    "<html><head><title>Invoice Automation for SaaS</title></head>"
    "<body><h1>Automate your invoices</h1>"
    "<p>Finance tooling for SaaS teams.</p></body></html>"
)


class _DemoFetcher:
    def fetch(self, url: str) -> str:
        return _DEMO_HTML


class _DemoProvider:
    """Offline stand-in: reports the brand as uncited (to create a gap) and
    returns a templated answer-first draft."""

    def complete(self, request: ModelRequest, prompt: str, *, system: str | None = None) -> ModelResponse:
        if request.task_class == "classification" and "style guide" in prompt.lower():
            content = "Plain, direct, practical, and specific to B2B operators."
        elif request.task_class == "classification":
            content = "best invoice automation for saas\nhow to reduce finance ops manual work"
        elif request.task_class == "monitoring":
            content = "For that, I'd point you to a few established competitors."
        else:
            first_line = prompt.splitlines()[0] if prompt else "your topic"
            content = (
                "## Direct answer\n\n"
                f"{first_line}\n\n"
                "This is a demo draft generated offline (no API key set). Set "
                "OPENAI_API_KEY to generate real brand-voiced content."
            )
        return ModelResponse(
            content=content, input_tokens=120, output_tokens=240, cost_usd=Decimal("0.0040")
        )


class _DemoPublisher:
    def publish(self, *, title: str, body: str, status: str = "draft") -> PublishResult:
        if status not in {"draft", "pending"}:
            raise StagingOnlyError(f"refusing non-staging status {status!r}")
        return PublishResult(
            cms_post_id="demo-1",
            url="https://staging.example.test/?p=demo-1&preview=true",
            status=status,
        )


def _load_env() -> None:
    # Load services/agent-runtime/.env (and parent .env) if python-dotenv is
    # installed. Real secrets live here, never committed (.env is gitignored).
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return
    load_dotenv(find_dotenv(usecwd=True))


def build_service() -> LoopService:
    _load_env()
    org_id = os.environ.get("QUERYCLEAR_DEV_ORG_ID", "org_dev_queryclear")
    budget = int(os.environ.get("QUERYCLEAR_TOKEN_BUDGET", "1000000"))

    database_url = os.environ.get("DATABASE_URL")
    repos: dict[str, object] = {}
    if database_url:
        from .db import (
            SqlAuditEventRepository,
            SqlBudgetRepository,
            SqlCmsCredentialRepository,
            SqlCrawlSnapshotRepository,
            SqlDraftRepository,
            SqlOpportunityRepository,
            SqlVisibilityCheckRepository,
            SqlVoiceProfileRepository,
            create_engine_from_url,
        )
        from .credentials import SecretCipher

        engine = create_engine_from_url(database_url)
        cipher = SecretCipher.from_env(os.environ)
        meter = TokenMeter(SqlBudgetRepository(engine))
        repos = {
            "cms_credentials": SqlCmsCredentialRepository(engine, cipher),
            "crawl_snapshots": SqlCrawlSnapshotRepository(engine),
            "visibility_checks": SqlVisibilityCheckRepository(engine),
            "drafts": SqlDraftRepository(engine),
            "opportunities": SqlOpportunityRepository(engine),
            "audit_events": SqlAuditEventRepository(engine),
            "voice_profiles": SqlVoiceProfileRepository(engine),
        }
    else:
        meter = TokenMeter(InMemoryBudgetRepository({org_id: TokenBudget(org_id, budget)}))

    from .monitoring import parse_monitoring_engines
    from .providers import ModelRoutingPolicy

    routing_policy = ModelRoutingPolicy.from_env(os.environ)
    monitoring_engines = parse_monitoring_engines(
        os.environ.get("QUERYCLEAR_MONITORING_ENGINES")
    )

    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if openai_key or anthropic_key:
        from .crawl import HttpPageFetcher
        from .providers import OpenAIProvider, RoutingProvider

        # Register whatever vendor keys are configured; the routing policy
        # decides which provider/model each task_class requests.
        backends: dict[str, object] = {}
        if openai_key:
            backends["openai"] = OpenAIProvider(api_key=openai_key)
        if anthropic_key:
            from .providers import AnthropicProvider

            backends["anthropic"] = AnthropicProvider(api_key=anthropic_key)
        provider: object = RoutingProvider(backends)  # type: ignore[arg-type]
        fetcher: object = HttpPageFetcher()
    else:
        provider = _DemoProvider()
        fetcher = _DemoFetcher()

    wp_base = os.environ.get("WORDPRESS_BASE_URL")
    if wp_base:
        from .publishing import WordPressPublisher

        publisher: object = WordPressPublisher(
            base_url=wp_base,
            username=os.environ["WORDPRESS_USERNAME"],
            app_password=os.environ["WORDPRESS_APP_PASSWORD"],
        )
    else:
        publisher = _DemoPublisher()

    brand = os.environ.get("QUERYCLEAR_DEV_ORG_NAME", "QueryClear Demo")
    voice = BrandVoice(brand=brand, guidelines="Plain, direct, founder-led. No hype. Answer-first.")

    return LoopService(
        meter=meter,
        provider=provider,  # type: ignore[arg-type]
        fetcher=fetcher,  # type: ignore[arg-type]
        voice=voice,
        publisher=publisher,  # type: ignore[arg-type]
        routing_policy=routing_policy,
        monitoring_engines=monitoring_engines,
        **repos,  # type: ignore[arg-type]  # Sql repos when DATABASE_URL set; else defaults
    )


def build_app():  # type: ignore[no-untyped-def]
    from .app import create_app

    return create_app(build_service())
