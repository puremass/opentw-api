import os
from server import app

if __name__ == "__main__":
    # Get host and port from environment or use defaults
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    # Run with production settings
    app.run(
        host=host,
        port=port,
        debug=False,
        access_log=True,
        workers=4
    )
