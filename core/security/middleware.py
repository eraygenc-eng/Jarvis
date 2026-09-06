import asyncio

from langchain.agents.middleware import wrap_tool_call
from langchain.messages import ToolMessage

from core.security.policy import (
    SecurityAction,
    evaluate_tool_call
)



async def ask_user_confirmation(tool_name, arguments, reason):
    # Show the action to the user
    print("\n[SECURITY] Sensitive action detected")
    print(f"Tool: {tool_name}")
    print(f"Arguments: {arguments}")
    print(f"Reason: {reason}")

    # Ask the user for permission
    answer = await asyncio.to_thread(
        input,
        "Allow this action? [y/N]: "
    )

    return answer.strip().lower() in {"y", "yes"}



@wrap_tool_call
async def security_middleware(request, handler):
    # Get tool info
    tool_name = request.tool_call["name"]
    arguments = request.tool_call.get("args", {})

    # Check tool call
    decision = evaluate_tool_call(
        tool_name=tool_name,
        arguments=arguments
    )

    # Block actions
    if decision.action == SecurityAction.BLOCK:
        return ToolMessage(
            content=f"Security blocked this action: {decision.reason}",
            tool_call_id=request.tool_call["id"],
        )

    # Ask the user before running sensitive actions
    if decision.action == SecurityAction.CONFIRM:
        approved = await ask_user_confirmation(
            tool_name=tool_name,
            arguments=arguments,
            reason=decision.reason,
        )

        # Stop the tool if the user denies the action
        if not approved:
            return ToolMessage(
                content="User denied this action.",
                tool_call_id=request.tool_call["id"],
            )

        # Run the tool after user approval
        return await handler(request)

    # Run allowed tools
    return await handler(request)