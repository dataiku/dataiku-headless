"""Cobuild's small process-local conversation contract."""

import asyncio
import inspect
import json
import threading
from types import SimpleNamespace

import pytest
from dataiku_mcp.tools import cobuild


class Context:
    async def info(self, _message):
        pass


class Response:
    def __init__(
        self,
        message="ok",
        is_confirmation_request=False,
        is_question_request=False,
        title=None,
        predefined_answers=None,
        allow_custom_answer=None,
        allow_multiple_answers=None,
        default_answer_set=None,
    ):
        self.message = message
        self.type = (
            "delete_confirmation_request"
            if is_confirmation_request
            else "ask_question_to_user_request"
            if is_question_request
            else "assistant_message"
        )
        self.is_error = False
        self.is_confirmation_request = is_confirmation_request
        self.is_question_request = is_question_request
        self.objects_to_delete = [{"id": "dataset"}] if is_confirmation_request else None
        self.deletion_impacts = None
        self.title = title
        self.predefined_answers = predefined_answers
        self.allow_custom_answer = allow_custom_answer
        self.allow_multiple_answers = allow_multiple_answers
        self.default_answer_set = default_answer_set


class Conversation:
    def __init__(self, conversation_id="conversation-1"):
        self.conversation_id = conversation_id
        self.pending_confirmation = False
        self.pending_question = False
        self.send_calls = []
        self.answer_calls = []
        self.question_answer_calls = []
        self.next_send = Response()
        self.next_answer = Response("confirmed")
        self.next_question_answer = Response("question answered")
        self.started = threading.Event()
        self.release = None
        self.error = None

    def send_message(self, message, *, allow_edit_project=False):
        self.send_calls.append((message, allow_edit_project))
        self.started.set()
        if self.release:
            self.release.wait(timeout=5)
        if self.error:
            raise self.error
        self.pending_confirmation = self.next_send.is_confirmation_request
        self.pending_question = self.next_send.is_question_request
        return self.next_send

    def answer_confirmation(self, choice):
        if not self.pending_confirmation:
            raise ValueError("No pending confirmation")
        self.pending_confirmation = self.next_answer.is_confirmation_request
        self.pending_question = self.next_answer.is_question_request
        self.answer_calls.append(choice)
        return self.next_answer

    def answer_question(self, answers, *, rejected=False, used_custom_answer=False):
        if not self.pending_question:
            raise ValueError("No pending question")
        self.pending_confirmation = self.next_question_answer.is_confirmation_request
        self.pending_question = self.next_question_answer.is_question_request
        self.question_answer_calls.append((answers, rejected, used_custom_answer))
        return self.next_question_answer


class Client:
    def __init__(self, conversation=None):
        self.conversation = conversation or Conversation()

    def get_project(self, _project_key):
        return SimpleNamespace(new_cobuild_conversation=lambda: self.conversation)


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    cobuild._conversations.clear()
    active_instance = {"name": "instance-a"}
    client = Client()
    monkeypatch.setattr(cobuild, "get_dss_client", lambda: client)
    monkeypatch.setattr(
        cobuild,
        "get_current_instance_for_tool",
        lambda: SimpleNamespace(name=active_instance["name"]),
    )
    yield client, active_instance
    for entry in cobuild._conversations.values():
        if entry.sdk_conversation.release:
            entry.sdk_conversation.release.set()
    cobuild._conversations.clear()


def run(coroutine):
    return asyncio.run(coroutine)


async def start():
    return json.loads(await cobuild.start_cobuild_conversation("PROJECT", Context()))


async def send(conversation_id="conversation-1", **kwargs):
    return json.loads(
        await cobuild.send_cobuild_message(
            conversation_id, "PROJECT", "do work", Context(), **kwargs
        )
    )


async def answer(turn_id, choice="APPROVE"):
    return json.loads(
        await cobuild.answer_cobuild_confirmation(
            "conversation-1", "PROJECT", turn_id, choice, Context()
        )
    )


async def answer_question(turn_id, answers, **kwargs):
    return json.loads(
        await cobuild.answer_cobuild_question(
            "conversation-1", "PROJECT", turn_id, answers, Context(), **kwargs
        )
    )


async def poll(turn_id, conversation_id="conversation-1"):
    return json.loads(
        await cobuild.get_cobuild_turn_status(
            conversation_id, "PROJECT", turn_id, Context()
        )
    )


async def wait_for_terminal(turn_id, conversation_id="conversation-1"):
    for _ in range(100):
        result = await poll(turn_id, conversation_id)
        if result["status"] not in {"queued", "in_progress"}:
            return result
        await asyncio.sleep(0.01)
    raise AssertionError("turn did not finish")


def test_edits_are_opt_in_and_tool_schema_matches(environment):
    client, _ = environment
    assert (
        inspect.signature(cobuild.send_cobuild_message)
        .parameters["allow_edit_project"]
        .default
        is False
    )

    async def scenario():
        await start()
        assert (await send())["status"] == "completed"
        assert (await send(allow_edit_project=True))["status"] == "completed"
        tool = await cobuild.mcp.get_tool("send_cobuild_message")
        assert tool.parameters["properties"]["allow_edit_project"]["default"] is False
        assert "wait_seconds" not in tool.parameters["properties"]

    run(scenario())
    assert client.conversation.send_calls == [("do work", False), ("do work", True)]


def test_confirmation_uses_the_exact_current_turn(environment):
    client, _ = environment
    client.conversation.next_send = Response("delete?", is_confirmation_request=True)
    client.conversation.next_answer = Response(
        "delete next?", is_confirmation_request=True
    )

    async def scenario():
        await start()
        proposal = await send(allow_edit_project=True)
        assert proposal["is_confirmation_request"]
        assert "confirmation_id" not in proposal
        tool = await cobuild.mcp.get_tool("answer_cobuild_confirmation")
        assert "turn_id" in tool.parameters["properties"]
        assert "confirmation_id" not in tool.parameters["properties"]
        with pytest.raises(ValueError, match="not the current turn_id"):
            await answer("wrong")
        with pytest.raises(ValueError, match="does not request a question answer"):
            await answer_question(proposal["turn_id"], [])
        successor = await answer(proposal["turn_id"])
        assert successor["is_confirmation_request"]
        with pytest.raises(ValueError, match="not the current turn_id"):
            await answer(proposal["turn_id"])
        await answer(successor["turn_id"], "CANCEL")

    run(scenario())
    assert client.conversation.answer_calls == ["APPROVE", "CANCEL"]


def test_pending_confirmation_blocks_new_messages(environment):
    client, _ = environment
    client.conversation.next_send = Response("delete?", is_confirmation_request=True)

    async def scenario():
        await start()
        await send(allow_edit_project=True)
        with pytest.raises(ValueError, match="pending confirmation"):
            await send()

    run(scenario())
    assert len(client.conversation.send_calls) == 1


def test_question_uses_the_exact_current_turn(environment):
    client, _ = environment
    client.conversation.next_send = Response(
        "Which date column?",
        is_question_request=True,
        title="Choose a date column",
        predefined_answers=["order_date", "ship_date"],
        allow_custom_answer=True,
        allow_multiple_answers=False,
        default_answer_set=True,
    )
    client.conversation.next_question_answer = Response(
        "Need another choice?", is_question_request=True
    )

    async def scenario():
        await start()
        question = await send()
        assert question["is_question_request"]
        assert question["question"] == {
            "title": "Choose a date column",
            "predefined_answers": ["order_date", "ship_date"],
            "allow_custom_answer": True,
            "allow_multiple_answers": False,
            "default_answer_set": True,
        }
        tool = await cobuild.mcp.get_tool("answer_cobuild_question")
        assert "turn_id" in tool.parameters["properties"]
        assert "answers" in tool.parameters["required"]
        with pytest.raises(ValueError, match="not the current turn_id"):
            await answer_question("wrong", ["order_date"])
        with pytest.raises(ValueError, match="does not request a confirmation"):
            await answer(question["turn_id"])
        successor = await answer_question(
            question["turn_id"], ["custom_date"], used_custom_answer=True
        )
        assert successor["is_question_request"]
        with pytest.raises(ValueError, match="not the current turn_id"):
            await answer_question(question["turn_id"], [])
        await answer_question(successor["turn_id"], [], rejected=True)

    run(scenario())
    assert client.conversation.question_answer_calls == [
        (["custom_date"], False, True),
        ([], True, False),
    ]


def test_pending_question_blocks_new_messages(environment):
    client, _ = environment
    client.conversation.next_send = Response("Which one?", is_question_request=True)

    async def scenario():
        await start()
        question = await send()
        with pytest.raises(ValueError, match="pending question"):
            await send()
        await answer_question(question["turn_id"], [])

    run(scenario())
    assert len(client.conversation.send_calls) == 1


def test_confirmation_request_does_not_depend_on_an_sdk_confirmation_id(environment):
    client, _ = environment
    response = Response("delete?")
    response.type = "delete_confirmation_request"
    response.is_confirmation_request = True
    response.objects_to_delete = [{"id": "dataset"}]
    client.conversation.next_send = response

    async def scenario():
        await start()
        result = await send(allow_edit_project=True)
        assert result["status"] == "completed"
        assert result["is_confirmation_request"]
        await answer(result["turn_id"], "CANCEL")

    run(scenario())


def test_timeout_retains_one_turn_until_its_result_is_polled(environment, monkeypatch):
    client, _ = environment
    client.conversation.release = threading.Event()
    monkeypatch.setattr(cobuild, "INLINE_WAIT_SECONDS", 0)

    async def scenario():
        await start()
        first = await send()
        assert first["status"] in {"queued", "in_progress"}
        with pytest.raises(ValueError, match=first["turn_id"]) as running:
            await send()
        assert "get_cobuild_turn_status with" in str(running.value)
        assert '"project_key":"PROJECT"' in str(running.value)
        client.conversation.release.set()
        for _ in range(100):
            if cobuild._conversations["conversation-1"].turn.task.done():
                break
            await asyncio.sleep(0.01)
        with pytest.raises(ValueError, match="terminal result") as unobserved:
            await send()
        assert first["turn_id"] in str(unobserved.value)
        assert (await poll(first["turn_id"]))["status"] == "completed"
        replacement = await send()
        assert replacement["status"] in {"queued", "in_progress"}
        assert (await wait_for_terminal(replacement["turn_id"]))["status"] == "completed"
        with pytest.raises(ValueError, match="not the current turn_id"):
            await poll(first["turn_id"])

    run(scenario())
    assert [message for message, _edits in client.conversation.send_calls] == [
        "do work",
        "do work",
    ]


def test_turn_status_waits_for_and_returns_the_terminal_result(environment, monkeypatch):
    client, _ = environment
    client.conversation.release = threading.Event()
    monkeypatch.setattr(cobuild, "INLINE_WAIT_SECONDS", 0)

    async def scenario():
        await start()
        pending = await send()
        monkeypatch.setattr(cobuild, "INLINE_WAIT_SECONDS", 1)
        waiter = asyncio.create_task(poll(pending["turn_id"]))
        await asyncio.sleep(0.01)
        assert not waiter.done()
        client.conversation.release.set()
        assert (await waiter)["status"] == "completed"
        assert cobuild._conversations["conversation-1"].turn.observed

    run(scenario())


def test_cancellation_keeps_the_turn_recoverable_from_listing(environment):
    client, _ = environment
    client.conversation.release = threading.Event()

    async def scenario():
        await start()
        waiter = asyncio.create_task(send())
        while not client.conversation.started.is_set():
            await asyncio.sleep(0.01)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        listing = json.loads(
            await cobuild.list_cobuild_conversations("PROJECT", Context())
        )
        columns = listing["conversations"]["columns"]
        row = dict(zip(columns, listing["conversations"]["rows"][0]))
        assert row["current_turn_status"] == "in_progress"
        client.conversation.release.set()
        assert (await wait_for_terminal(row["current_turn_id"]))["status"] == "completed"

    run(scenario())


def test_queued_cobuild_turns_are_accepted_with_pollable_ids(environment, monkeypatch):
    first = Conversation("conversation-1")
    second = Conversation("conversation-2")
    clients = [Client(first), Client(second)]
    monkeypatch.setattr(
        cobuild,
        "get_dss_client",
        lambda: clients[0] if "conversation-1" not in cobuild._conversations else clients[1],
    )
    monkeypatch.setattr(cobuild, "INLINE_WAIT_SECONDS", 0)

    async def scenario():
        release_queue = asyncio.Event()

        async def delayed_cobuild_call(func, *args, **kwargs):
            await release_queue.wait()
            return func(*args, **kwargs)

        monkeypatch.setattr(cobuild, "run_cobuild_blocking", delayed_cobuild_call)
        await start()
        await start()
        first_turn = await send("conversation-1")
        second_turn = await send("conversation-2")
        assert first_turn["status"] == "queued"
        assert second_turn["status"] == "queued"
        release_queue.set()
        assert (
            await wait_for_terminal(first_turn["turn_id"], "conversation-1")
        )["status"] == "completed"
        assert (
            await wait_for_terminal(second_turn["turn_id"], "conversation-2")
        )["status"] == "completed"

    run(scenario())


def test_ownership_and_sdk_contract(environment):
    _client, active_instance = environment

    async def scenario():
        await start()
        with pytest.raises(ValueError, match="belongs to project"):
            await cobuild.send_cobuild_message(
                "conversation-1", "OTHER", "work", Context()
            )
        active_instance["name"] = "instance-b"
        with pytest.raises(ValueError, match="belongs to instance"):
            await send()

    run(scenario())
