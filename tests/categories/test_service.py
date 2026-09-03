import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.categories.commands import CategoryCommand, UpdateCategoryCommand
from app.categories.models import Category
from app.categories.repository import CategoryRepository
from app.categories.schemas import UpdateCategoryRequest
from app.categories.service import CategoryService
from app.shared.commands import UNSET
from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError

ACTOR_ID = uuid.uuid4()


def make_category(**overrides: object) -> Category:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "group_id": uuid.uuid4(),
        "parent_id": None,
        "name": "Test Category",
        "color": None,
        "icon": None,
        "is_active": True,
        "created_by": None,
        "updated_by": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Category(**defaults)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def category_repo() -> MagicMock:
    return MagicMock(spec=CategoryRepository)


@pytest.fixture
def service(category_repo: MagicMock) -> CategoryService:
    return CategoryService(category_repo)


class TestCreateCategory:
    def test_creates_root_category_without_checking_parent(
        self, service: CategoryService, category_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        created = make_category(group_id=group_id)
        category_repo.create_category.return_value = created
        command = CategoryCommand(
            group_id=group_id, name="Root", parent_id=None, color=None, icon=None
        )

        result = service.create_category(uuid.uuid4(), command)

        assert result.parent_id is None
        category_repo.get_category_by_id.assert_not_called()

    def test_creates_subcategory_of_existing_root(
        self, service: CategoryService, category_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        root = make_category(group_id=group_id, parent_id=None)
        category_repo.get_category_by_id.return_value = root
        created = make_category(group_id=group_id, parent_id=root.id)
        category_repo.create_category.return_value = created

        command = CategoryCommand(
            group_id=group_id, name="Sub", parent_id=root.id, color=None, icon=None
        )
        result = service.create_category(uuid.uuid4(), command)

        assert result.parent_id == root.id

    def test_raises_conflict_when_parent_does_not_exist(
        self, service: CategoryService, category_repo: MagicMock
    ):
        category_repo.get_category_by_id.return_value = None
        command = CategoryCommand(
            group_id=uuid.uuid4(),
            name="Orphan",
            parent_id=uuid.uuid4(),
            color=None,
            icon=None,
        )

        with pytest.raises(ConflictError):
            service.create_category(uuid.uuid4(), command)

        category_repo.create_category.assert_not_called()

    def test_raises_conflict_when_parent_is_from_another_group(
        self, service: CategoryService, category_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        parent = make_category(group_id=uuid.uuid4())
        category_repo.get_category_by_id.return_value = parent
        command = CategoryCommand(
            group_id=group_id,
            name="Cross group",
            parent_id=parent.id,
            color=None,
            icon=None,
        )

        with pytest.raises(ConflictError):
            service.create_category(uuid.uuid4(), command)

    def test_raises_conflict_when_parent_is_already_a_subcategory(
        self, service: CategoryService, category_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        grandparent = make_category(group_id=group_id)
        parent = make_category(group_id=group_id, parent_id=grandparent.id)
        category_repo.get_category_by_id.return_value = parent
        command = CategoryCommand(
            group_id=group_id,
            name="Third level",
            parent_id=parent.id,
            color=None,
            icon=None,
        )

        with pytest.raises(ConflictError):
            service.create_category(uuid.uuid4(), command)


class TestGetCategories:
    def test_returns_all_categories_in_group(
        self, service: CategoryService, category_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        category_repo.get_categories_by_group_id.return_value = [
            make_category(group_id=group_id),
            make_category(group_id=group_id, is_active=False),
        ]

        result = service.get_categories(group_id)

        assert len(result) == 2


class TestGetCategory:
    def test_returns_category_when_found(
        self, service: CategoryService, category_repo: MagicMock
    ):
        category = make_category()
        category_repo.get_category_by_id.return_value = category

        result = service.get_category(category.id)

        assert result.id == category.id

    def test_raises_not_found_when_missing(
        self, service: CategoryService, category_repo: MagicMock
    ):
        category_repo.get_category_by_id.return_value = None

        with pytest.raises(NotFoundError):
            service.get_category(uuid.uuid4())


class TestUpdateCategory:
    def test_raises_bad_request_when_no_fields(self, service: CategoryService):
        command = UpdateCategoryCommand()

        with pytest.raises(BadRequestError):
            service.update_category(uuid.uuid4(), command, ACTOR_ID)

    def test_updates_simple_field_without_touching_parent(
        self, service: CategoryService, category_repo: MagicMock
    ):
        updated = make_category(name="Renamed")
        category_repo.update_category.return_value = updated
        command = UpdateCategoryCommand(name="Renamed")

        category_id = uuid.uuid4()
        result = service.update_category(category_id, command, ACTOR_ID)

        assert result.name == "Renamed"
        category_repo.update_category.assert_called_once_with(
            category_id, command, ACTOR_ID
        )
        category_repo.get_category_by_id.assert_not_called()

    def test_raises_not_found_when_category_itself_missing(
        self, service: CategoryService, category_repo: MagicMock
    ):
        category_repo.get_category_by_id.return_value = None
        command = UpdateCategoryCommand(parent_id=uuid.uuid4())

        with pytest.raises(NotFoundError):
            service.update_category(uuid.uuid4(), command, ACTOR_ID)

    def test_raises_conflict_when_new_parent_is_self(
        self, service: CategoryService, category_repo: MagicMock
    ):
        category_id = uuid.uuid4()
        group_id = uuid.uuid4()
        current = make_category(id=category_id, group_id=group_id)
        category_repo.get_category_by_id.return_value = current
        command = UpdateCategoryCommand(parent_id=category_id)

        with pytest.raises(ConflictError):
            service.update_category(category_id, command, ACTOR_ID)

    def test_raises_conflict_when_category_already_has_children(
        self, service: CategoryService, category_repo: MagicMock
    ):
        category_id = uuid.uuid4()
        group_id = uuid.uuid4()
        current = make_category(id=category_id, group_id=group_id)
        other_root = make_category(group_id=group_id)

        def get_by_id(cid: uuid.UUID) -> Category | None:
            return current if cid == category_id else other_root

        category_repo.get_category_by_id.side_effect = get_by_id
        category_repo.has_children.return_value = True

        command = UpdateCategoryCommand(parent_id=other_root.id)

        with pytest.raises(ConflictError):
            service.update_category(category_id, command, ACTOR_ID)

    def test_reparents_successfully_when_valid(
        self, service: CategoryService, category_repo: MagicMock
    ):
        category_id = uuid.uuid4()
        group_id = uuid.uuid4()
        current = make_category(id=category_id, group_id=group_id)
        new_root = make_category(group_id=group_id)

        def get_by_id(cid: uuid.UUID) -> Category | None:
            return current if cid == category_id else new_root

        category_repo.get_category_by_id.side_effect = get_by_id
        category_repo.has_children.return_value = False
        updated = make_category(
            id=category_id, group_id=group_id, parent_id=new_root.id
        )
        category_repo.update_category.return_value = updated

        command = UpdateCategoryCommand(parent_id=new_root.id)
        result = service.update_category(category_id, command, ACTOR_ID)

        assert result.parent_id == new_root.id

    def test_archiving_does_not_trigger_parent_checks(
        self, service: CategoryService, category_repo: MagicMock
    ):
        updated = make_category(is_active=False)
        category_repo.update_category.return_value = updated
        command = UpdateCategoryCommand(is_active=False)

        result = service.update_category(uuid.uuid4(), command, ACTOR_ID)

        assert result.is_active is False
        category_repo.get_category_by_id.assert_not_called()


class TestUpdateCategoryClearingFields:
    """ARCHITECTURE.md §5.5: null explícito vacía; ausente no toca nada."""

    def test_explicit_null_parent_promotes_to_root_without_checks(
        self, service: CategoryService, category_repo: MagicMock
    ):
        category_repo.update_category.return_value = make_category(parent_id=None)

        service.update_category(
            uuid.uuid4(), UpdateCategoryCommand(parent_id=None), ACTOR_ID
        )

        applied = category_repo.update_category.call_args.args[1]
        assert applied.parent_id is None
        # Vaciar no asigna padre, así que no hay jerarquía que validar.
        category_repo.get_category_by_id.assert_not_called()

    def test_absent_fields_stay_unset(
        self, service: CategoryService, category_repo: MagicMock
    ):
        category_repo.update_category.return_value = make_category(color=None)

        service.update_category(
            uuid.uuid4(), UpdateCategoryCommand(color=None), ACTOR_ID
        )

        applied = category_repo.update_category.call_args.args[1]
        assert applied.color is None
        assert applied.parent_id is UNSET
        assert applied.icon is UNSET

    def test_rejects_explicit_null_on_not_null_columns(self):
        for field in ("name", "is_active"):
            with pytest.raises(ValidationError):
                UpdateCategoryRequest.model_validate({field: None})
