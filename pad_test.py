import time

def parse_step_to_seconds(step: str) -> int:
    unit = step[-1]
    val = int(step[:-1])
    if unit == 's': return val
    elif unit == 'm': return val * 60
    elif unit == 'h': return val * 3600
    elif unit == 'd': return val * 86400
    return val

step_secs = parse_step_to_seconds("15s")
print(step_secs)
