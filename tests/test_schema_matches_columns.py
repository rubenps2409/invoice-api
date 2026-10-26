"""A text limit is written in the schema AND in the column. If they drift apart,
a value the API accepts fails inside PostgreSQL as a 500 (or a limit is stricter
than it needs to be). The reusable string types (Str100, Str255) cannot import
the column lengths, so this test keeps them in step."""

from typing import get_args

import pytest
from pydantic import BaseModel

from invoice_api.models import Category, Invoice, Supplier, User
from invoice_api.schemas.category import CategoryCreate, CategoryUpdate
from invoice_api.schemas.extraction import ExtractedInvoice
from invoice_api.schemas.invoice import InvoiceCreate, InvoiceUpdate
from invoice_api.schemas.supplier import SupplierCreate, SupplierUpdate
from invoice_api.schemas.user import UserCreate


def declared_max_length(schema: type[BaseModel], field: str) -> int:
    info = schema.model_fields[field]
    constraints = list(info.metadata)
    # Optional fields keep their constraints inside the Annotated union member.
    for arg in get_args(info.annotation):
        constraints += getattr(arg, "__metadata__", ())
    lengths = {c.max_length for c in constraints if getattr(c, "max_length", None)}
    assert len(lengths) == 1, f"{schema.__name__}.{field} must declare one max_length"
    return lengths.pop()


def column_length(model, column: str) -> int:
    return model.__table__.c[column].type.length


@pytest.mark.parametrize(
    ("schema", "field", "model", "column"),
    [
        (CategoryCreate, "name", Category, "name"),
        (CategoryUpdate, "name", Category, "name"),
        (SupplierCreate, "name", Supplier, "name"),
        (SupplierUpdate, "name", Supplier, "name"),
        (InvoiceCreate, "number", Invoice, "number"),
        (InvoiceUpdate, "number", Invoice, "number"),
        (UserCreate, "email", User, "email"),
        (ExtractedInvoice, "supplier_name", Supplier, "name"),
        (ExtractedInvoice, "invoice_number", Invoice, "number"),
        (ExtractedInvoice, "category_name", Category, "name"),
    ],
    ids=lambda v: getattr(v, "__name__", v),
)
def test_a_schema_limit_equals_the_column_length(schema, field, model, column):
    assert declared_max_length(schema, field) == column_length(model, column)
