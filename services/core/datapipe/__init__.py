# core.datapipe — Reusable Schema-Aware Data Pipeline Engine
#
# This package contains zero ERP business logic.
# It can be imported into any SQLAlchemy + FastAPI project.
#
# Public surface:
#   from core.datapipe.introspect import introspect_model, SchemaDefinitionObject
#   from core.datapipe.builder import build_template
#   from core.datapipe.parser import parse_workbook
#   from core.datapipe.coerce import coerce_row
#   from core.datapipe.validate import validate_rows
#   from core.datapipe.mapper import FKResolver
#   from core.datapipe.executor import execute_import
#   from core.datapipe.exporter import export_data
