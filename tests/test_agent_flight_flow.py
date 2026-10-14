
import asyncio
from unittest.mock import MagicMock, AsyncMock
from langchain_core.messages import AIMessage
from core.research.task_classifier import TaskType

from core.agent import JarvisAgent


def test_agent_airport_conversation(monkeypatch):
    # Create a lightweight agent for testing
    agent = JarvisAgent.__new__(JarvisAgent)

    # Set the required agent state
    agent.pending_flight_request = None
    agent.thread_id = "flight-test"

    # Mock unrelated services
    agent.task_runtime = MagicMock()
    agent.timing_callback = MagicMock()

    
    # Prepare the agent research state
    agent.pending_comparison_prompt = None
    agent.current_comparison_state = None
    agent.research_controller = None

    # Create a fake browser execution
    agent.action_executor = MagicMock()
    agent.action_executor.execute_agent_turn = AsyncMock(
        return_value={
            "messages": [
                AIMessage(content="Flight request received")
            ]
        }
    )

    # Skip real research planning in this test
    monkeypatch.setattr(
        "core.agent.classify_task",
        lambda prompt: TaskType.ACTION
    )


    # Send the first flight request
    first_reply = asyncio.run(
        agent.run("İstanbul'dan Londra'ya uçak bileti bul")
    )

    # Check the first airport question
    assert "İstanbul" in first_reply
    assert "IST" in first_reply
    assert "SAW" in first_reply

    # Check if the request was saved
    assert agent.pending_flight_request is not None

    # Select the departure airport
    second_reply = asyncio.run(agent.run("SAW"))

    # Check the next airport question
    assert "Londra" in second_reply
    assert "LHR" in second_reply

    # Check if SAW was saved
    departure = agent.pending_flight_request["departure"]
    assert departure["airports"][0]["iata_code"] == "SAW"

    print("\nFirst reply:", first_reply)
    print("Second reply:", second_reply)

    
    # Select the arrival airport
    third_reply = asyncio.run(agent.run("LHR"))

    # Check if the pending request was cleared
    assert agent.pending_flight_request is None

    # Check if the agent executor was called
    agent.action_executor.execute_agent_turn.assert_awaited_once()

    # Get the request sent to the executor
    sent_messages = (
        agent.action_executor.execute_agent_turn
        .await_args.kwargs["messages"]
    )

    sent_prompt = sent_messages[0]["content"]

    # Check the original flight request
    assert "İstanbul'dan Londra'ya" in sent_prompt

    # Check the selected airport codes
    assert "Departure: SAW" in sent_prompt
    assert "Arrival: LHR" in sent_prompt

    # Check the fake executor response
    assert third_reply == "Flight request received"

    print("\nFinal flight prompt:", sent_prompt)

