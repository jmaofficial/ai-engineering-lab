import datetime

def get_current_time() -> str:
    """Returns the current time as a string in ISO 8601 format."""
    print("🔧 TOOL EXECUTED: get_current_time()")
    return datetime.datetime.now().isoformat()