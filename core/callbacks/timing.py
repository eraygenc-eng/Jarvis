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

        # Store LLM statistics
        self.llm_success_count = 0
        self.llm_error_count = 0
        self.llm_durations = []

        # Store token usage
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.token_usage_available = False

        # Store the largest LLM input
        self.max_input_messages = 0
        self.max_input_chars = 0

        # Store tool statistics
        self.tool_stats = {}

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

        # Measure message content size
        message_count = sum(len(batch) for batch in messages)
        content_chars = sum(
            len(str(message.content))
            for batch in messages
            for message in batch
        )

        self.max_input_messages = max(
            self.max_input_messages,
            message_count,
        )

        self.max_input_chars = max(
            self.max_input_chars,
            content_chars,
        )

        print(
            f"[Timing] LLM input: "
            f"messages={message_count}, "
            f"content_chars={content_chars}"
        )

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
        # Count successful LLM calls
        self.llm_success_count += 1

        # Calculate the LLM execution time
        start_time = self.llm_start_times.pop(run_id, None)

        if start_time is not None:
            elapsed_time = time.perf_counter() - start_time
            self.llm_durations.append(elapsed_time)

            print(
                f"[Timing] LLM: {elapsed_time:.2f} seconds"
            )

        # Read token usage from the generated message
        usage_metadata = None

        for batch in getattr(response, "generations", []) or []:
            for generation in batch:
                message = getattr(generation, "message", None)

                if message is None:
                    continue

                usage_metadata = getattr(
                    message,
                    "usage_metadata",
                    None,
                )

                if usage_metadata:
                    break

            if usage_metadata:
                break

        if usage_metadata:
            input_tokens = usage_metadata.get("input_tokens")
            output_tokens = usage_metadata.get("output_tokens")

            input_details = (
                usage_metadata.get("input_token_details") or {}
            )
            cache_read = input_details.get("cache_read")

            if isinstance(input_tokens, int):
                self.input_tokens += input_tokens
                self.token_usage_available = True

            if isinstance(output_tokens, int):
                self.output_tokens += output_tokens
                self.token_usage_available = True

            if isinstance(cache_read, int):
                self.cache_read_tokens += cache_read

    def on_llm_error(
        self,
        error,
        *,
        run_id,
        **kwargs,
    ):
        # Count failed LLM calls
        self.llm_error_count += 1

        # Measure how long the failed call took
        start_time = self.llm_start_times.pop(run_id, None)

        if start_time is not None:
            elapsed_time = time.perf_counter() - start_time
            self.llm_durations.append(elapsed_time)

            print(
                f"[Timing] LLM failed after "
                f"{elapsed_time:.2f} seconds"
            )

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

        # Show structured research inputs during debugging.
        if tool_name.startswith("research_"):
            print(f"\n[Research input] {tool_name}")
            print(input_str)

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


        # Show validation decisions and stored research data.
        if tool_name.startswith("research_"):
            content = getattr(output, "content", output)

            print(f"\n[Research output] {tool_name}")
            print(content)

        if start_time is not None:
            elapsed_time = time.perf_counter() - start_time

            stats = self.tool_stats.setdefault(
                tool_name,
                {
                    "count": 0,
                    "errors": 0,
                    "total_duration": 0.0,
                },
            )

            stats["count"] += 1
            stats["total_duration"] += elapsed_time

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

            stats = self.tool_stats.setdefault(
                tool_name,
                {
                    "count": 0,
                    "errors": 0,
                    "total_duration": 0.0,
                },
            )

            stats["count"] += 1
            stats["errors"] += 1
            stats["total_duration"] += elapsed_time

            print(
                f"[Timing] Tool ({tool_name}) failed after "
                f"{elapsed_time:.2f} seconds"
            )

    def reset_request_stats(self):
        # Reset request-level LLM statistics
        self.llm_success_count = 0
        self.llm_error_count = 0
        self.llm_durations = []

        # Reset request-level token usage
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.token_usage_available = False

        # Reset maximum input size
        self.max_input_messages = 0
        self.max_input_chars = 0

        # Reset request-level tool statistics
        self.tool_stats = {}

    def print_summary(self):
        print("\n========== PERFORMANCE SUMMARY ==========")

        total_llm_duration = sum(self.llm_durations)

        print(
            f"LLM calls: "
            f"success={self.llm_success_count}, "
            f"errors={self.llm_error_count}"
        )

        print(
            f"Total LLM duration: "
            f"{total_llm_duration:.2f} seconds"
        )

        print(
            f"Max LLM input: "
            f"messages={self.max_input_messages}, "
            f"content_chars={self.max_input_chars}"
        )

        if self.token_usage_available:
            print(
                f"Tokens: "
                f"input={self.input_tokens}, "
                f"output={self.output_tokens}, "
                f"cache_read={self.cache_read_tokens}"
            )
        else:
            print("Tokens: unknown")

        print("\nTool usage:")

        if not self.tool_stats:
            print("No tool calls recorded.")
        else:
            for tool_name, stats in sorted(self.tool_stats.items()):
                print(
                    f"- {tool_name}: "
                    f"calls={stats['count']}, "
                    f"errors={stats['errors']}, "
                    f"total={stats['total_duration']:.2f}s"
                )

        print("=========================================\n")