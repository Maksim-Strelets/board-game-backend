"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """
    Upgrade database schema to the next version.

    This method should contain all the changes to be applied when migrating
    to a newer version of the database schema.
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """
    Revert database schema to the previous version.

    This method should contain the necessary steps to undo the changes
    made in the upgrade() method, ensuring database schema can be rolled back.
    """
    ${downgrade if downgrade else "pass"}
