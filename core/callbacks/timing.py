import time

from langchain_core.callbacks import BaseCallbackHandler


class TimingCallback(BaseCallbackHandler):
    def __init__(self):
        # Store LLM start times
        self.llm_start_times = {}

        # Store tool start times
        self.tool_start_times = {}

        # Store tool names
        self.tool_names = {}

    def on_chat_model_start(
        self,
        serialized,
        messages,
        *,
        run_id,
        **kwargs,
    ):
        # Start timing the chat model
        self.llm_start_times[run_id] = time.perf_counter()

    def on_llm_start(
        self,
        serialized,
        prompts,
        *,
        run_id,
        **kwargs,
    ):
        # Start timing the LLM if not already started
        if run_id not in self.llm_start_times:
            self.llm_start_times[run_id] = time.perf_counter()

    def on_llm_end(
        self,
        response,
        *,
        run_id,
        **kwargs,
    ):
        # Calculate the LLM execution time
        start_time = self.llm_start_times.pop(run_id, None)

        if start_time is not None:
            elapsed_time = time.perf_counter() - start_time

            print(
                f"[Timing] LLM: {elapsed_time:.2f} seconds"
            )

    def on_llm_error(
        self,
        error,
        *,
        run_id,
        **kwargs,
    ):
        # Clear the timer if the LLM fails
        self.llm_start_times.pop(run_id, None)

    def on_tool_start(
        self,
        serialized,
        input_str,
        *,
        run_id,
        **kwargs,
    ):
        # Get the tool name
        tool_name = (serialized or {}).get(
            "name",
            "unknown_tool",
        )

        # Start timing the tool
        self.tool_start_times[run_id] = time.perf_counter()
        self.tool_names[run_id] = tool_name

    def on_tool_end(
        self,
        output,
        *,
        run_id,
        **kwargs,
    ):
        # Get stored tool information
        start_time = self.tool_start_times.pop(run_id, None)
        tool_name = self.tool_names.pop(
            run_id,
            "unknown_tool",
        )

        if start_time is not None:
            elapsed_time = time.perf_counter() - start_time

            print(
                f"[Timing] Tool ({tool_name}): "
                f"{elapsed_time:.2f} seconds"
            )

    def on_tool_error(
        self,
        error,
        *,
        run_id,
        **kwargs,
    ):
        # Get stored tool information
        start_time = self.tool_start_times.pop(run_id, None)
        tool_name = self.tool_names.pop(
            run_id,
            "unknown_tool",
        )

        if start_time is not None:
            elapsed_time = time.perf_counter() - start_time

            print(
                f"[Timing] Tool ({tool_name}) failed after "
                f"{elapsed_time:.2f} seconds"
            )