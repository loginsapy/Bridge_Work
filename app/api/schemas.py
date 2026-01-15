from marshmallow import Schema, fields, validates, ValidationError, validate


class ProjectSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=1))
    client_id = fields.Int(allow_none=True)
    manager_id = fields.Int(allow_none=True)
    status = fields.Str(load_default="PLANNING")
    project_type = fields.Str(load_default="APP_DEVELOPMENT")
    metadata_json = fields.Dict(allow_none=True)
    budget_hours = fields.Float(allow_none=True)
    start_date = fields.Date(allow_none=True)
    end_date = fields.Date(allow_none=True)


class TaskSchema(Schema):
    id = fields.Int(dump_only=True)
    project_id = fields.Int(required=True)
    parent_task_id = fields.Int(allow_none=True)
    title = fields.Str(required=True, validate=validate.Length(min=1))
    description = fields.Str(allow_none=True)
    assigned_to_id = fields.Int(allow_none=True)
    assigned_client_id = fields.Int(allow_none=True)
    status = fields.Str(load_default="BACKLOG")
    priority = fields.Str(load_default="MEDIUM")
    start_date = fields.DateTime(allow_none=True)
    due_date = fields.DateTime(allow_none=True)
    is_external_visible = fields.Bool(load_default=False)
    estimated_hours = fields.Float(allow_none=True)


class TimeEntrySchema(Schema):
    id = fields.Int(dump_only=True)
    task_id = fields.Int(required=True)
    user_id = fields.Int(required=True)
    date = fields.Date(required=True)
    hours = fields.Float(required=True)
    description = fields.Str(allow_none=True)
    is_billable = fields.Bool(load_default=True)

    @validates("hours")
    def validate_hours(self, value, **kwargs):
        if value < 0:
            raise ValidationError("hours must be >= 0")
