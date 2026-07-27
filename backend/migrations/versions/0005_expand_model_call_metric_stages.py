"""allow the two-stage image workflow metrics without touching persisted data"""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    # 0004 created this named CHECK constraint.  Replace only its predicate;
    # rows, indexes, foreign keys, and business tables remain untouched.
    op.drop_constraint("chk_model_call_metrics_stage", "model_call_metrics", type_="check")
    op.create_check_constraint(
        "chk_model_call_metrics_stage",
        "model_call_metrics",
        sa.text("stage IN ('text_generation','image_generation','image_reference_generation','image_layout_edit')"),
    )


def downgrade():
    raise RuntimeError("model metric stage expansion downgrade is disabled: persisted observability records must not be invalidated")
