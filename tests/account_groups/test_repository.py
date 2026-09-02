import uuid
from unittest.mock import MagicMock

from sqlalchemy.dialects import postgresql

from app.account_groups.repository import AccountGroupMemberRepository


def test_group_member_mutation_read_locks_members_in_stable_order():
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = []
    repository = AccountGroupMemberRepository(db)
    group_id = uuid.uuid4()

    repository.get_group_members_by_group_id(group_id, for_update=True)

    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql
    assert "ORDER BY account_group_members.id" in sql
