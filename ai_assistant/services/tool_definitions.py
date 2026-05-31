# -*- coding: utf-8 -*-
"""OpenAI function/tool schemas for generic Odoo ORM tools."""

OPENAI_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_models",
            "description": (
                "List Odoo models available for querying. Call this when you are unsure "
                "which model to use."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of models to return (default 50).",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_fields",
            "description": (
                "Get field names and types for an Odoo model. Use before search or "
                "aggregation when field names are uncertain."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "description": "Technical model name, e.g. sale.order",
                    },
                },
                "required": ["model"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_records",
            "description": "Search and read records from an Odoo model.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string", "description": "Technical model name"},
                    "domain": {
                        "type": "array",
                        "description": "Odoo domain filter, e.g. [['state','=','sale']]",
                        "items": {},
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Field names to return",
                    },
                    "limit": {"type": "integer", "description": "Max records (default 20, max 100)"},
                },
                "required": ["model"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_records",
            "description": "Read specific records by database id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Record ids to read",
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["model", "ids"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_count",
            "description": "Count records matching a domain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "domain": {
                        "type": "array",
                        "items": {},
                        "description": "Odoo domain filter",
                    },
                },
                "required": ["model"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aggregate_records",
            "description": (
                "Aggregate records (read_group): sums, counts, group by fields. "
                "Use for top-N, totals, revenue, quantities by dimension."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "domain": {"type": "array", "items": {}},
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Fields to aggregate, e.g. ['amount_total:sum']",
                    },
                    "groupby": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Group-by field names",
                    },
                    "limit": {"type": "integer"},
                },
                "required": ["model", "groupby"],
                "additionalProperties": False,
            },
        },
    },
]
