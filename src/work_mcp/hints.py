from __future__ import annotations


NOTIFY_USER_INSTRUCTION = "tell the user in your reply"
ASK_USER_HOW_TO_PROCEED_INSTRUCTION = "ask the user how you should proceed"

STOP_AND_NOTIFY_USER_INSTRUCTION = (
    f"Stop and {NOTIFY_USER_INSTRUCTION}."
)
STOP_NOTIFY_AND_ASK_USER_HOW_TO_PROCEED_INSTRUCTION = (
    f"Stop, {NOTIFY_USER_INSTRUCTION}, and {ASK_USER_HOW_TO_PROCEED_INSTRUCTION}."
)

INTERNAL_ERROR_RETRY_HINT = (
    "An internal error occurred. Retry up to 2 times; "
    "if still failing, stop and notify the user with the message above."
)
DINGTALK_INTERNAL_ERROR_HINT = (
    "An internal error occurred. Stop and tell the user in your reply: "
    "the notification could not be sent."
)


def required_param_hint(param_name: str) -> str:
    return f"`{param_name}` must not be empty. Fix the parameter and retry."


def positive_int_param_hint(param_name: str) -> str:
    return f"`{param_name}` must be greater than 0. Fix the parameter and retry."
