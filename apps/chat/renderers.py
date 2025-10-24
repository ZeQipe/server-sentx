from rest_framework import renderers


class SSERenderer(renderers.BaseRenderer):
    """
    Custom renderer for Server-Sent Events (SSE)
    Supports content-type: text/event-stream
    """

    media_type = "text/event-stream"
    format = "sse"
    charset = "utf-8"
    render_style = "text"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """
        Render data as SSE format
        """
        if data is None:
            return ""

        # if data is string - return as is (for streaming)
        if isinstance(data, str):
            return data.encode(self.charset)

        # if data is dict - convert to SSE event
        if isinstance(data, dict):
            import json

            event_data = json.dumps(data)
            return f"data: {event_data}\n\n".encode(self.charset)

        # for other types - just string representation
        return str(data).encode(self.charset)

