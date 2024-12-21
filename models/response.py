from sanic.response import JSONResponse


class Response(JSONResponse):
    def __init__(
        self: "Response",
        ok: bool = False,
        data: dict = None,
        status: int = 200,
    ):
        super().__init__({
            "ok": ok,
            "data": data,
        }, status=status)
