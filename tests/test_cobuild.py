"""Cobuild's small process-local conversation contract."""

import asyncio
import inspect
import json
import threading
from types import SimpleNamespace

import pytest
from dataikuapi.dss.cobuild import DSSCobuildConversation

from dataiku_mcp.tools import cobuild


class Context:
    async def info(self, _message):
        pass


class Response:
    def __init__(self, message="ok", confirmation_id=None):
        self.message = message
        self.type = (
            "delete_confirmation_request" if confirmation_id else "assistant_message"
        )
        self.is_error = False
        self.is_confirmation_request = confirmation_id is not None
        self.objects_to_delete = [{"id": "dataset"}] if confirmation_id else None
        self.deletion_impacts = None
        self.confirmation_id = confirmation_id


class Conversation:
    def __init__(self, conversation_id="conversation-1"):
        self.conversation_id = conversation_id
        self._pending_confirmation_id = None
        self.send_calls = []
        self.answer_calls = []
        self.next_send = Response()
        self.next_answer = Response("confirmed")
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
        self._pending_confirmation_id = self.next_send.confirmation_id
        return self.next_send

    def answer_confirmation(self, choice):
        confirmation_id = self._pending_confirmation_id
        if confirmation_id is None:
            raise ValueError("No pending confirmation")
        self._pending_confirmation_id = self.next_answer.confirmation_id
        self.answer_calls.append((choice, confirmation_id))
        return self.next_answer


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


async def answer(confirmation_id, choice="APPROVE"):
    return json.loads(
        await cobuild.answer_cobuild_confirmation(
            "conversation-1", "PROJECT", confirmation_id, choice, Context()
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


def test_confirmation_uses_the_exact_current_sdk_id(environment):
    client, _ = environment
    client.conversation.next_send = Response("delete?", "proposal-a")
    client.conversation.next_answer = Response("delete next?", "proposal-b")

    async def scenario():
        await start()
        proposal = await send(allow_edit_project=True)
        assert proposal["confirmation_id"] == "proposal-a"
        with pytest.raises(ValueError, match="does not match"):
            await answer("wrong")
        successor = await answer("proposal-a")
        assert successor["confirmation_id"] == "proposal-b"
        with pytest.raises(ValueError, match="does not match"):
            await answer("proposal-a")
        await answer("proposal-b", "CANCEL")

    run(scenario())
    assert client.conversation.answer_calls == [
        ("APPROVE", "proposal-a"),
        ("CANCEL", "proposal-b"),
    ]


def test_pending_or_unidentified_confirmation_fails_closed(environment):
    client, _ = environment
    client.conversation.next_send = Response("delete?", "proposal-a")

    async def scenario():
        await start()
        await send(allow_edit_project=True)
        with pytest.raises(ValueError, match="pending confirmation"):
            await send()

    run(scenario())
    assert len(client.conversation.send_calls) == 1

    client.conversation._pending_confirmation_id = None
    del client.conversation._pending_confirmation_id
    with pytest.raises(RuntimeError, match="does not expose"):
        run(send())


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
        with pytest.raises(ValueError, match="Unknown current"):
            await poll(first["turn_id"])

    run(scenario())
    assert [message for message, _edits in client.conversation.send_calls] == [
        "do work",
        "do work",
    ]


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

    class SDKClient:
        def _perform_json(self, *_args, **_kwargs):
            return {
                "type": "delete_confirmation_request",
                "message": "confirm",
                "confirmationId": "proposal-a",
            }

    sdk_conversation = DSSCobuildConversation(SDKClient(), "PROJECT", "id")
    sdk_conversation.send_message("delete")
    assert cobuild._pending_confirmation_id(sdk_conversation) == "proposal-a"
