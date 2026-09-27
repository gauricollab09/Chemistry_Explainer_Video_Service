"""FastAPI entry point: wires store, artifacts, topic registry, pipeline and worker together."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from app.api.routes import router
from app.artifacts.store import LocalArtifactStore
from app.config import Settings, load_settings
from app.generation.contracts import Runner
from app.generation.topics import TopicRegistry, default_registry
from app.jobs.store import SQLiteJobStore
from app.jobs.worker import Worker

log = logging.getLogger("chemvid")


@dataclass
class Services:
    settings: Settings
    store: SQLiteJobStore
    artifacts: LocalArtifactStore
    registry: TopicRegistry
    worker: Worker


def create_app(settings: Settings, runner: Runner | None = None) -> FastAPI:
    store = SQLiteJobStore(settings.db_path)
    artifacts = LocalArtifactStore(settings.artifacts_dir)
    registry = default_registry()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        recovered = store.recover_interrupted()
        if recovered:
            log.warning("Marked %d interrupted job(s) as failed: %s", len(recovered), recovered)
        job_runner = runner
        if job_runner is None:
            from app.generation.pipeline import Pipeline

            job_runner = Pipeline(settings, artifacts, registry)
        worker = Worker(store, job_runner, settings.job_timeout_s, settings.pipeline_version)
        app.state.services = Services(settings, store, artifacts, registry, worker)
        worker.start()
        yield
        await worker.stop()

    app = FastAPI(
        title="Chemistry Explainer Video Service",
        description="Request a short narrated chemistry explainer video; poll the job until it is ready.",
        version=settings.pipeline_version,
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
app = create_app(load_settings())
