"""ufc-publish CLI — promote trained models from lab → AWS.

F1 scope: --dry-run is operational and lists planned steps without writing.
Real S3/SageMaker/RDS execution is scheduled for F4.
"""

import argparse
import sys

from ufc_core.db.engine import session_scope
from ufc_core.db import models as db_models


def _list_active_version_ids(db) -> list[int]:
    rows = db.query(db_models.ActiveModel).all()
    return [r.version_id for r in rows]


def _build_plan(
    db, version_ids: list[int], target: str, skip_data: bool
) -> list[dict]:
    plan: list[dict] = []
    for vid in version_ids:
        v = (
            db.query(db_models.ModelVersion)
              .filter_by(id=vid)
              .one_or_none()
        )
        if v is None:
            continue
        m = db.query(db_models.Model).filter_by(id=v.model_id).one()
        plan.append({
            "model_short": m.short,
            "version_idx": v.version_idx,
            "artifact_uri": v.artifact_uri,
            "target": target,
            "steps": (
                ["package_tar", "upload_s3", "register_sagemaker"]
                + ([] if skip_data else ["dump_slice_to_rds"])
                + ["audit_publish_run"]
            ),
        })
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ufc-publish",
        description="Promote a trained model from lab → AWS (S3 + SageMaker + RDS).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--version-id", type=int,
                       help="ModelVersion.id concreto a publicar")
    group.add_argument("--all-active", action="store_true",
                       help="Publica todas las versiones marcadas activas")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe nada; muestra el plan de ejecución")
    parser.add_argument("--skip-data", action="store_true",
                        help="No sincronizar slice de datos a RDS")
    parser.add_argument("--target", choices=["local", "aws"], default="aws",
                        help="Destino del publish (default: aws)")

    args = parser.parse_args(argv)

    import sys as _sys
    _mod = _sys.modules[__name__]
    with _mod.session_scope() as db:
        if args.all_active:
            version_ids = _list_active_version_ids(db)
        else:
            version_ids = [args.version_id]

        plan = _build_plan(db, version_ids, args.target, args.skip_data)

        if not plan:
            print("[publish] Nada que publicar (sin versiones activas o id desconocido).",
                  file=sys.stderr)
            return 0

        if args.dry_run:
            print("DRY RUN — no se ejecutará nada")
            for entry in plan:
                print(
                    f"  {entry['model_short']} v={entry['version_idx']} "
                    f"target={entry['target']} steps={entry['steps']}"
                )
            return 0

        print("[publish] Ejecución real disponible en F4. Usa --dry-run por ahora.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
