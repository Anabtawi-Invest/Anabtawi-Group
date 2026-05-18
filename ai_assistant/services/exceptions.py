# -*- coding: utf-8 -*-


class AiAssistantError(Exception):
    """Controlled error raised by the AI assistant service layer."""

    def __init__(self, message, error_code="unknown"):
        super().__init__(message)
        self.error_code = error_code
