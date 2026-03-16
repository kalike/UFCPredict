from ufc_core.db import Base, models as db_models


def test_dry_run_lists_steps(test_engine, db_session_real_commit, capsys):
    Base.metadata.create_all(test_engine)
    m = db_models.Model(short="lgbm", family="sklearn", default_feat_type="52f",
                       description="L")
    db_session_real_commit.add(m)
    db_session_real_commit.flush()
    v = db_models.ModelVersion(model_id=m.id, version_idx=1, feature_set="v7",
                              artifact_uri="file:///tmp/x.tar.gz")
    db_session_real_commit.add(v)
    db_session_real_commit.commit()

    # Point the CLI's session factory at the test engine
    from ufc_core.db import engine as engine_mod
    from sqlalchemy.orm import sessionmaker
    import ufc_core.publish.cli as cli_mod
    test_session_factory = sessionmaker(bind=test_engine, future=True)

    # Replace session_scope in cli to use our test factory
    import contextlib

    @contextlib.contextmanager
    def fake_scope():
        s = test_session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    original_scope = cli_mod.session_scope
    cli_mod.session_scope = fake_scope
    try:
        rc = cli_mod.main(["--dry-run", "--version-id", str(v.id)])
    finally:
        cli_mod.session_scope = original_scope

    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out
    assert "lgbm" in out
    assert "v=1" in out


def test_cli_no_active_versions_exits_clean(test_engine, db_session_real_commit, capsys):
    Base.metadata.create_all(test_engine)

    from ufc_core.db import engine as engine_mod
    from sqlalchemy.orm import sessionmaker
    import ufc_core.publish.cli as cli_mod
    import contextlib

    test_session_factory = sessionmaker(bind=test_engine, future=True)

    @contextlib.contextmanager
    def fake_scope():
        s = test_session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    original_scope = cli_mod.session_scope
    cli_mod.session_scope = fake_scope
    try:
        rc = cli_mod.main(["--all-active", "--dry-run"])
    finally:
        cli_mod.session_scope = original_scope

    assert rc == 0
