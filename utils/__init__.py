from datetime import datetime

def _get_timestamp() -> str:
    return str(int(datetime.now().timestamp())) + '000'
