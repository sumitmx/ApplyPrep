from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, config, documents, profile, pull, service, store
from .documents import layout, palette

UI_DIST = Path(__file__).resolve().parents[1] / "ui" / "dist"


class MarkBody(BaseModel):
    action: str
    reason: str | None = None


class StatusBody(BaseModel):
    status: str
    note: str | None = None


class PullBody(BaseModel):
    countries: list[str] | None = None
    since_days: int | None = None


class AskBody(BaseModel):
    question: str


class PasteJobBody(BaseModel):
    title: str
    company: str
    description: str
    url: str | None = None
    location: str | None = None
    employment_type: str | None = None


class SettingsBody(BaseModel):
    ai_provider: str


class SkillExtractBody(BaseModel):
    text: str


class SkillEntry(BaseModel):
    name: str
    tier: str
    context: str | None = None


class SaveSkillsBody(BaseModel):
    skills: list[SkillEntry]


class HighlightBody(BaseModel):
    text: str
    topic: str | None = None


def create_app(cfg=None):
    cfg = cfg or config.load()
    app = FastAPI(title="ApplyPrep", docs_url="/api/docs", redoc_url=None)

    def db():
        conn = store.connect(cfg["db_path"])
        store.migrate(conn)
        return conn

    def master():
        return profile.load_master(cfg.get("master_path", "master.yaml"))

    def _require_agent(conn):
        provider = service.get_ai_provider(conn)
        if not agent.available(provider):
            info = agent.PROVIDERS[provider]
            raise HTTPException(
                status_code=503,
                detail="The " + info["command"] + " command was not found. "
                       + info["setup_hint"],
            )

    @app.get("/api/settings")
    def get_settings():
        conn = db()
        try:
            return service.ai_providers(conn)
        finally:
            conn.close()

    @app.post("/api/settings")
    def post_settings(body: SettingsBody):
        conn = db()
        try:
            service.set_ai_provider(conn, body.ai_provider)
            return service.ai_providers(conn)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            conn.close()

    @app.get("/api/dashboard")
    def get_dashboard(hours: int = 168):
        conn = db()
        try:
            return service.dashboard(conn, hours=hours, limits=service.band_limits(cfg))
        finally:
            conn.close()

    @app.get("/api/sources")
    def get_sources():
        conn = db()
        try:
            return service.sources(conn)
        finally:
            conn.close()

    @app.get("/api/jobs")
    def get_jobs(gate: str | None = None, country: str | None = None,
                 min_fit: int | None = None, status: str | None = None,
                 hours: int | None = None, remote: str | None = None,
                 agency: bool | None = None, source: str | None = None,
                 band: str | None = None, applied: bool | None = None,
                 limit: int = 50, offset: int = 0):
        conn = db()
        try:
            return service.jobs(conn, gate=gate, country=country, min_fit=min_fit,
                                status=status, hours=hours, remote=remote,
                                agency=agency, source=source, band=band,
                                applied=applied,
                                limit=min(limit, 200), offset=offset,
                                limits=service.band_limits(cfg))
        finally:
            conn.close()

    @app.post("/api/jobs/paste")
    def post_paste_job(body: PasteJobBody):
        """Add a job from a description pasted by hand.

        For boards that cannot be scraped - LinkedIn, Upwork, remote.com. The
        job it creates is indistinguishable from a pulled one downstream.
        """
        conn = db()
        try:
            return pull.paste_job(
                conn, cfg, body.model_dump(), master(),
                profile.load_profile(cfg.get("profile_path", "profile.yaml")),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            conn.close()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: int):
        conn = db()
        try:
            job = service.job_detail(conn, job_id, master())
            if job is None:
                raise HTTPException(status_code=404, detail="job not found")
            job["neighbours"] = service.neighbours(conn, job_id)
            return job
        finally:
            conn.close()

    @app.post("/api/jobs/{job_id}/rate")
    def post_rate(job_id: int):
        loaded = master()
        if not loaded:
            raise HTTPException(
                status_code=409,
                detail="master.yaml was not found, so there is nothing to score against.",
            )
        conn = db()
        try:
            _require_agent(conn)
            result = service.rate_job(
                conn, job_id, loaded,
                profile.load_profile(cfg.get("profile_path", "profile.yaml")),
                service.band_limits(cfg),
            )
        except HTTPException:
            raise
        except agent.AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=type(exc).__name__ + ": " + str(exc)[:300],
            )
        finally:
            conn.close()
        if result is None:
            raise HTTPException(status_code=404, detail="job not found")
        return result

    @app.post("/api/jobs/{job_id}/estimate/{kind}")
    def post_estimate(job_id: int, kind: str):
        if kind not in ("ats", "offer"):
            raise HTTPException(status_code=400, detail="kind must be ats or offer")
        loaded = master()
        if not loaded:
            raise HTTPException(
                status_code=409,
                detail="master.yaml was not found, so there is nothing to score against.",
            )
        conn = db()
        try:
            _require_agent(conn)
            result = service.rate_estimate(
                conn, job_id, loaded,
                profile.load_profile(cfg.get("profile_path", "profile.yaml")),
                kind,
            )
        except HTTPException:
            raise
        except service.NotRatedError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except agent.AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=type(exc).__name__ + ": " + str(exc)[:300],
            )
        finally:
            conn.close()
        if result is None:
            raise HTTPException(status_code=404, detail="job not found")
        return result

    @app.get("/api/jobs/{job_id}/chat")
    def get_job_chat(job_id: int):
        conn = db()
        try:
            return {"messages": service.job_chat(conn, job_id)}
        finally:
            conn.close()

    @app.post("/api/jobs/{job_id}/ask")
    def post_ask(job_id: int, body: AskBody):
        if not body.question.strip():
            raise HTTPException(status_code=400, detail="question is empty")
        conn = db()
        try:
            _require_agent(conn)
            answer = service.ask_about_job(conn, job_id, master(), body.question)
        except HTTPException:
            raise
        except agent.AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=type(exc).__name__ + ": " + str(exc)[:300],
            )
        finally:
            conn.close()
        if answer is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {"answer": answer}

    @app.post("/api/jobs/{job_id}/apply")
    def post_apply(job_id: int):
        conn = db()
        try:
            result = service.start_application(conn, job_id)
        finally:
            conn.close()
        if result is None:
            raise HTTPException(status_code=404, detail="job not found")
        return result

    @app.post("/api/jobs/{job_id}/mark")
    def post_mark(job_id: int, body: MarkBody):
        conn = db()
        try:
            try:
                result = service.mark_job(conn, job_id, body.action, body.reason)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            if result is None:
                raise HTTPException(status_code=404, detail="job not found")
            return result
        finally:
            conn.close()

    @app.get("/api/applications")
    def get_applications():
        conn = db()
        try:
            return service.applications(conn)
        finally:
            conn.close()

    @app.post("/api/applications/{application_id}")
    def post_application(application_id: int, body: StatusBody):
        conn = db()
        try:
            result = service.set_application_status(
                conn, application_id, body.status, body.note
            )
            if result is None:
                raise HTTPException(status_code=404, detail="application not found")
            return result
        finally:
            conn.close()

    @app.get("/api/master-cv")
    def get_master_cv():
        data = service.master_cv(master())
        docs_dir = cfg.get("documents_dir", "documents")
        data["uploads"] = {
            kind: service.master_upload_info(docs_dir, kind)
            for kind in service.MASTER_UPLOAD_KINDS
        }
        return data

    @app.post("/api/master-cv/{kind}/upload")
    async def post_master_upload(kind: str, file: UploadFile = File(...)):
        if kind not in service.MASTER_UPLOAD_KINDS:
            raise HTTPException(status_code=400, detail="kind must be cv")
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="the file was empty")
        try:
            return service.save_master_upload(
                cfg.get("documents_dir", "documents"), kind, file.filename, content
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/master-cv/{kind}/download")
    def get_master_download(kind: str):
        if kind not in service.MASTER_UPLOAD_KINDS:
            raise HTTPException(status_code=400, detail="kind must be cv")
        path = service.master_upload_path(cfg.get("documents_dir", "documents"), kind)
        if not path or not path.exists():
            raise HTTPException(status_code=404, detail="nothing uploaded yet")
        return FileResponse(path, filename=path.name)

    @app.delete("/api/master-cv/{kind}")
    def delete_master_upload(kind: str):
        if kind not in service.MASTER_UPLOAD_KINDS:
            raise HTTPException(status_code=400, detail="kind must be cv")
        removed = service.discard_master_upload(cfg.get("documents_dir", "documents"), kind)
        if not removed:
            raise HTTPException(status_code=404, detail="nothing uploaded yet")
        return {"kind": kind, "discarded": True}

    @app.post("/api/skills/extract")
    def post_extract_skills(body: SkillExtractBody):
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="nothing to extract from")
        conn = db()
        try:
            _require_agent(conn)
            skills = service.extract_skills(conn, master(), body.text)
        except HTTPException:
            raise
        except agent.AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        finally:
            conn.close()
        return {"skills": skills}

    @app.post("/api/skills")
    def post_save_skills(body: SaveSkillsBody):
        if not body.skills:
            raise HTTPException(status_code=400, detail="nothing to save")
        return service.save_skills(
            master(), cfg.get("master_path", "master.yaml"),
            [s.model_dump() for s in body.skills],
        )

    @app.get("/api/profile/kpis")
    def get_profile_kpis():
        conn = db()
        try:
            loaded = master()
            return {
                "skill_demand": service.skill_demand(conn, loaded),
                "freshness": service.profile_freshness(
                    conn, cfg.get("master_path", "master.yaml")
                ),
                "bullet_usage": service.bullet_usage(conn, loaded),
                "sponsorship_mix": service.sponsorship_mix(conn),
                "keyword_coverage": service.keyword_coverage(conn),
            }
        finally:
            conn.close()

    @app.get("/api/profile/skill-gaps")
    def get_skill_gaps():
        conn = db()
        try:
            return service.skill_gaps(conn, master())
        finally:
            conn.close()

    @app.post("/api/profile/skill-gaps/refresh")
    def post_skill_gaps_refresh():
        conn = db()
        try:
            _require_agent(conn)
            return service.refresh_skill_gaps(conn, master())
        except HTTPException:
            raise
        except agent.AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        finally:
            conn.close()

    @app.get("/api/documents")
    def get_all_documents():
        conn = db()
        try:
            return {"documents": service.all_documents(conn)}
        finally:
            conn.close()

    @app.get("/api/documents/cv-accents")
    def get_cv_accents():
        return {
            "accents": [
                {"key": k, **v,
                 "ink": palette.ink_for(v["hex"]),
                 "text": palette.on_paper(v["hex"])}
                for k, v in palette.ACCENTS.items()
            ],
            "default": palette.DEFAULT_ACCENT,
            # The preview reads the same type scale the exports use, so the
            # three renderings cannot drift apart.
            "layout": layout.css_vars(),
        }

    @app.get("/api/documents/{job_id}")
    def get_documents(job_id: int):
        conn = db()
        try:
            return {
                "job_id": job_id,
                "agent_available": agent.available(service.get_ai_provider(conn)),
                "cv": service.stored_document(conn, job_id, "cv"),
                "letter": service.stored_document(conn, job_id, "letter"),
                "review": service.stored_review(conn, job_id),
            }
        finally:
            conn.close()

    def _generate(job_id, kind):
        loaded = master()
        if not loaded:
            raise HTTPException(
                status_code=409,
                detail="master.yaml was not found, so there is nothing to tailor from.",
            )
        conn = db()
        try:
            _require_agent(conn)
            if kind == "cv":
                result = service.generate_cv(conn, job_id, loaded)
            else:
                result = service.generate_letter(
                    conn, job_id, loaded,
                    profile.load_profile(cfg.get("profile_path", "profile.yaml")),
                )
        except HTTPException:
            raise
        except documents.FabricationError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except agent.AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        finally:
            conn.close()
        if result is None:
            raise HTTPException(status_code=404, detail="job not found")
        return result

    @app.post("/api/documents/{job_id}/cv")
    def post_cv(job_id: int):
        return _generate(job_id, "cv")

    @app.post("/api/documents/{job_id}/letter")
    def post_letter(job_id: int):
        return _generate(job_id, "letter")

    def _kind(kind):
        if kind not in ("cv", "letter"):
            raise HTTPException(status_code=400, detail="kind must be cv or letter")
        return kind

    @app.post("/api/documents/{job_id}/{kind}/accept")
    def post_accept(job_id: int, kind: str, accent: str = palette.DEFAULT_ACCENT):
        conn = db()
        try:
            result = service.accept_document(
                conn, job_id, _kind(kind), master(),
                cfg.get("documents_dir", "documents"), accent=accent,
            )
            if result is None:
                raise HTTPException(status_code=404, detail="nothing written yet")
            if result.get("error"):
                raise HTTPException(status_code=409, detail=result["error"])
            return result
        finally:
            conn.close()

    @app.delete("/api/documents/{job_id}/{kind}")
    def delete_document(job_id: int, kind: str):
        conn = db()
        try:
            result = service.discard_document(conn, job_id, _kind(kind))
            if result is None:
                raise HTTPException(status_code=404, detail="nothing to discard")
            return result
        finally:
            conn.close()

    @app.get("/api/documents/{job_id}/{kind}/download")
    def download_document(job_id: int, kind: str):
        conn = db()
        try:
            row = service.stored_document(conn, job_id, _kind(kind))
        finally:
            conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="nothing written yet")
        if not row.get("has_file"):
            raise HTTPException(
                status_code=409,
                detail="Save it first, then the file is created and can be downloaded.",
            )
        name = "cv.docx" if kind == "cv" else "cover-letter.docx"
        return FileResponse(
            row["path"],
            filename=name,
            media_type="application/vnd.openxmlformats-officedocument."
                       "wordprocessingml.document",
        )

    @app.get("/api/documents/{job_id}/cv/export")
    def export_cv(job_id: int, fmt: str = "docx", accent: str = palette.DEFAULT_ACCENT):
        if fmt not in ("docx", "pdf"):
            raise HTTPException(status_code=400, detail="fmt must be docx or pdf")
        conn = db()
        try:
            try:
                result = service.export_cv(conn, job_id, fmt, accent)
            except service.ExportUnavailable as exc:
                raise HTTPException(status_code=409, detail=str(exc))
        finally:
            conn.close()
        if result is None:
            raise HTTPException(status_code=404, detail="nothing written yet")
        media = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if fmt == "docx" else "application/pdf"
        )
        return StreamingResponse(
            result["data"], media_type=media,
            headers={"Content-Disposition": 'attachment; filename="' + result["filename"] + '"'},
        )

    @app.post("/api/documents/{job_id}/cv/review")
    def post_review(job_id: int):
        conn = db()
        try:
            _require_agent(conn)
            result = service.review_cv(conn, job_id, master())
        except service.NoTailoredCvError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except agent.AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        finally:
            conn.close()
        if result is None:
            raise HTTPException(status_code=404, detail="job not found")
        return result

    @app.post("/api/documents/{job_id}/cv/highlights")
    def post_highlight(job_id: int, body: HighlightBody):
        conn = db()
        try:
            result = service.add_cv_highlight(conn, job_id, master(), body.text, body.topic)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except service.ExportUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        finally:
            conn.close()
        if result is None:
            raise HTTPException(status_code=404, detail="job not found")
        return result

    @app.post("/api/pull")
    def post_pull(body: PullBody | None = None):
        conn = db()
        try:
            body = body or PullBody()
            return pull.run(conn, cfg, body.countries, body.since_days)
        finally:
            conn.close()

    if UI_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            candidate = UI_DIST / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(
                UI_DIST / "index.html",
                headers={"Cache-Control": "no-store, must-revalidate"},
            )
    else:
        @app.get("/")
        def missing_ui():
            return {
                "message": "UI not built yet",
                "build": "cd ui && npm install && npm run build",
                "api": "/api/docs",
            }

    return app


def create_default_app():
    return create_app(config.load())


def serve(cfg=None, host="127.0.0.1", port=None, open_browser=True, reload=False):
    import threading
    import webbrowser

    import uvicorn

    cfg = cfg or config.load()
    port = port or cfg.get("port", 8756)
    url = "http://" + host + ":" + str(port)
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    if reload:
        uvicorn.run(
            "jobagent.api:create_default_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
            reload_dirs=[str(Path(__file__).resolve().parent)],
            log_level="info",
        )
        return
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="info")
