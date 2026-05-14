"""
Tests for POST /api/internal/jobs/sunday-checklist-morning and -evening.

Validates:
- Missing Authorization header → 401
- Wrong CRON_SECRET → 401
- Correct secret → 200, orchestrator called
- Response JSON shape: job, skipped, results fields present
- Dedup: second call within window returns skipped=true
- APScheduler job registrations for sunday jobs are not broken
- send_to_group_topic_strict returning None is treated as failure (502, retryable)
- Multi-chunk partial send failure returns 502
- Concurrent calls send each group exactly once
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import app.bot.checklist_helpers as checklist_helpers  # for GroupName.ALL and _DEDUP assertions

VALID_SECRET = "test-cron-secret-abc123"
MORNING_URL = "/api/internal/jobs/sunday-checklist-morning"
EVENING_URL = "/api/internal/jobs/sunday-checklist-evening"


def _mock_settings(cron_secret: str = VALID_SECRET) -> MagicMock:
    ms = MagicMock()
    ms.cron_secret = cron_secret
    return ms


# ─── Auth: morning endpoint ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_morning_no_auth_returns_401(client):
    response = await client.post(MORNING_URL)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_morning_wrong_secret_returns_401(client):
    with patch("app.routers.internal_jobs.settings", _mock_settings()):
        response = await client.post(
            MORNING_URL, headers={"Authorization": "Bearer wrong-secret"}
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_morning_malformed_auth_returns_401(client):
    with patch("app.routers.internal_jobs.settings", _mock_settings()):
        response = await client.post(
            MORNING_URL, headers={"Authorization": VALID_SECRET}  # missing "Bearer "
        )
    assert response.status_code == 401


# ─── Auth: evening endpoint ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evening_no_auth_returns_401(client):
    response = await client.post(EVENING_URL)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_evening_wrong_secret_returns_401(client):
    with patch("app.routers.internal_jobs.settings", _mock_settings()):
        response = await client.post(
            EVENING_URL, headers={"Authorization": "Bearer wrong-secret"}
        )
    assert response.status_code == 401


# ─── Authorized requests call orchestrators ───────────────────────────────────

@pytest.mark.asyncio
async def test_morning_authorized_calls_orchestrator(client):
    mock_run = AsyncMock(return_value={"GROUP_1": "ok", "GROUP_2": "ok"})
    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.routers.internal_jobs.run_sunday_morning_all_groups", mock_run):
        response = await client.post(
            MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
    assert response.status_code == 200
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_evening_authorized_calls_orchestrator(client):
    mock_run = AsyncMock(return_value=({"GROUP_1": "ok", "GROUP_2": "ok"}, {}))
    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.routers.internal_jobs.run_sunday_evening_all_groups", mock_run):
        response = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
    assert response.status_code == 200
    mock_run.assert_awaited_once()


# ─── Response shape ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_morning_response_has_required_fields(client):
    mock_run = AsyncMock(return_value={"GROUP_1": "ok", "GROUP_2": "ok"})
    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.routers.internal_jobs.run_sunday_morning_all_groups", mock_run):
        response = await client.post(
            MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
    data = response.json()
    assert data["job"] == "sunday-checklist-morning"
    assert "skipped" in data
    assert "results" in data
    assert data["skipped"] is False


@pytest.mark.asyncio
async def test_evening_response_has_required_fields(client):
    mock_run = AsyncMock(return_value=({"GROUP_1": "ok", "GROUP_2": "ok"}, {}))
    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.routers.internal_jobs.run_sunday_evening_all_groups", mock_run):
        response = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
    data = response.json()
    assert data["job"] == "sunday-checklist-evening"
    assert "skipped" in data
    assert "results" in data


# ─── Dedup: second call within window returns skipped ─────────────────────────

@pytest.mark.asyncio
async def test_morning_dedup_prevents_double_send(client):
    """Second authorized call within 30 min returns skipped=true without calling Telegram."""
    mock_send = AsyncMock()
    mock_db = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=mock_cm), \
         patch("app.bot.checklist_helpers.send_sunday_morning_for_group", mock_send):
        # First call — should run and send
        r1 = await client.post(
            MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
        # Second call — within dedup window, should skip
        r2 = await client.post(
            MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert r1.status_code == 200
    assert r1.json()["skipped"] is False

    assert r2.status_code == 200
    assert r2.json()["skipped"] is True

    # Telegram helper was only called during the first run (4 groups × 1)
    assert mock_send.await_count == len(checklist_helpers.GroupName.ALL)


@pytest.mark.asyncio
async def test_evening_dedup_prevents_double_send(client):
    """Second authorized call within 30 min returns skipped=true without calling Telegram."""
    mock_checklist = MagicMock()
    mock_required = AsyncMock(return_value=mock_checklist)
    mock_dms = AsyncMock(return_value=[])

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers._send_sunday_evening_required", mock_required), \
         patch("app.bot.checklist_helpers._send_evening_dms_for_group", mock_dms):
        r1 = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
        r2 = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert r1.status_code == 200
    assert r1.json()["skipped"] is False

    assert r2.status_code == 200
    assert r2.json()["skipped"] is True

    # Required send only called during the first run (once per group)
    assert mock_required.await_count == len(checklist_helpers.GroupName.ALL)


# ─── Partial failure: endpoint returns 502 ────────────────────────────────────

def _make_cm():
    mock_db = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


@pytest.mark.asyncio
async def test_morning_partial_failure_returns_502(client):
    """One failing group yields 502; all other groups are still attempted."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]

    async def side_effect(group_name, db):
        if group_name == fail_group:
            raise RuntimeError("Telegram send failed")

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.send_sunday_morning_for_group",
               AsyncMock(side_effect=side_effect)):
        response = await client.post(
            MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert response.status_code == 502
    data = response.json()
    assert data["job"] == "sunday-checklist-morning"
    assert data["skipped"] is False
    assert fail_group in data["failed_groups"]
    assert data["results"][fail_group] == "error"
    # All groups were attempted (per-group isolation)
    assert set(data["results"].keys()) == set(groups)
    # Non-failing groups recorded as ok
    for g in groups:
        if g != fail_group:
            assert data["results"][g] == "ok"


@pytest.mark.asyncio
async def test_evening_partial_failure_returns_502(client):
    """One failing group yields 502; all other groups are still attempted."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]

    async def required_side_effect(group_name, db):
        if group_name == fail_group:
            raise RuntimeError("Telegram send failed")
        return MagicMock()

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers._send_sunday_evening_required",
               AsyncMock(side_effect=required_side_effect)), \
         patch("app.bot.checklist_helpers._send_evening_dms_for_group", AsyncMock(return_value=[])):
        response = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert response.status_code == 502
    data = response.json()
    assert data["job"] == "sunday-checklist-evening"
    assert data["skipped"] is False
    assert fail_group in data["failed_groups"]
    assert data["results"][fail_group] == "error"
    assert set(data["results"].keys()) == set(groups)
    for g in groups:
        if g != fail_group:
            assert data["results"][g] == "ok"


# ─── Retry: failed groups retried, succeeded groups not duplicated ─────────────

@pytest.mark.asyncio
async def test_morning_retry_retries_failed_group_only(client):
    """Second call within dedup window retries the failed group and skips succeeded ones."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]
    call_tracker: list[str] = []

    async def side_effect(group_name, db):
        call_tracker.append(group_name)
        # Fail only on the first call for fail_group
        if group_name == fail_group and call_tracker.count(group_name) == 1:
            raise RuntimeError("transient failure")

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.send_sunday_morning_for_group",
               AsyncMock(side_effect=side_effect)):
        r1 = await client.post(
            MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
        r2 = await client.post(
            MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    # First call: fail_group errors, others succeed
    assert r1.status_code == 502
    assert r1.json()["results"][fail_group] == "error"

    # Second call: only fail_group retried and succeeds; others skipped (not duplicated)
    assert r2.status_code == 200
    assert r2.json()["results"][fail_group] == "ok"
    for g in groups:
        if g != fail_group:
            assert r2.json()["results"][g] == "skipped"


@pytest.mark.asyncio
async def test_evening_retry_retries_failed_group_only(client):
    """Second call within dedup window retries the failed group and skips succeeded ones."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]
    call_tracker: list[str] = []

    async def required_side_effect(group_name, db):
        call_tracker.append(group_name)
        if group_name == fail_group and call_tracker.count(group_name) == 1:
            raise RuntimeError("transient failure")
        return MagicMock()

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers._send_sunday_evening_required",
               AsyncMock(side_effect=required_side_effect)), \
         patch("app.bot.checklist_helpers._send_evening_dms_for_group", AsyncMock(return_value=[])):
        r1 = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
        r2 = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert r1.status_code == 502
    assert r1.json()["results"][fail_group] == "error"

    assert r2.status_code == 200
    assert r2.json()["results"][fail_group] == "ok"
    for g in groups:
        if g != fail_group:
            assert r2.json()["results"][g] == "skipped"


# ─── APScheduler registrations are not broken ─────────────────────────────────

def test_scheduler_job_ids_registered_in_main():
    """Verify main.py still registers the two Sunday APScheduler jobs by their expected IDs."""
    import inspect
    import app.main as main_module

    src = inspect.getsource(main_module)
    assert 'id="sunday_checklist_morning"' in src
    assert 'id="sunday_checklist_reminder"' in src


def test_scheduler_wrappers_delegate_to_orchestrators():
    """Verify the APScheduler callbacks import from checklist_helpers (not inline Telegram calls)."""
    import inspect
    import app.main as main_module

    morning_src = inspect.getsource(main_module._run_sunday_checklist_morning)
    evening_src = inspect.getsource(main_module._run_sunday_evening_reminder)

    assert "run_sunday_morning_all_groups" in morning_src
    assert "run_sunday_evening_all_groups" in evening_src


# ─── None return from send_to_group_topic_strict is treated as failure ───────────────

def _make_checklist_mock():
    """Minimal checklist mock with one item so format helpers produce non-empty text."""
    item = MagicMock()
    item.is_completed = False
    item.assignee_id = None
    item.id = 1
    item.title = "Test Task"
    item.item_order = 0

    sub = MagicMock()
    sub.id = 1
    sub.title = "Section"
    sub.section_order = 0
    sub.items = [item]

    checklist = MagicMock()
    checklist.group_name = "test_group"
    checklist.week_start = MagicMock()
    checklist.week_start.strftime = MagicMock(return_value="Jan 01")
    checklist.subchecklists = [sub]
    checklist.items = [item]
    checklist.assignments = []
    return checklist


@pytest.mark.asyncio
async def test_morning_none_send_returns_502_and_is_retryable(client):
    """send_to_group_topic_strict returning None on first call → 502; retry with real send → 200."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]
    call_count = {"n": 0}

    async def send_side_effect(group_name, text):
        if group_name == fail_group:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # simulated Telegram failure
        return 12345  # success

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock())), \
         patch("app.bot.checklist_helpers.format_full_checklist", return_value="checklist text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(side_effect=send_side_effect)):
        r1 = await client.post(MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})
        r2 = await client.post(MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})

    assert r1.status_code == 502
    assert r1.json()["results"][fail_group] == "error"
    assert fail_group in r1.json()["failed_groups"]

    assert r2.status_code == 200
    assert r2.json()["results"][fail_group] == "ok"
    for g in groups:
        if g != fail_group:
            assert r2.json()["results"][g] == "skipped"


@pytest.mark.asyncio
async def test_evening_none_send_returns_502_and_is_retryable(client):
    """send_to_group_topic_strict returning None on evening group message → 502; retry → 200."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]
    call_count = {"n": 0}

    async def send_side_effect(group_name, text):
        if group_name == fail_group:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None
        return 12345

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock())), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist", return_value="reminder text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(side_effect=send_side_effect)):
        r1 = await client.post(EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})
        r2 = await client.post(EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})

    assert r1.status_code == 502
    assert r1.json()["results"][fail_group] == "error"
    assert fail_group in r1.json()["failed_groups"]

    assert r2.status_code == 200
    assert r2.json()["results"][fail_group] == "ok"
    for g in groups:
        if g != fail_group:
            assert r2.json()["results"][g] == "skipped"


@pytest.mark.asyncio
async def test_morning_multi_chunk_partial_send_failure_returns_502(client):
    """Second chunk returning None in a multi-chunk message → group reports error."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]
    chunk_call = {"n": 0}

    async def send_side_effect(group_name, text):
        if group_name == fail_group:
            chunk_call["n"] += 1
            if chunk_call["n"] == 2:
                return None  # second chunk fails
        return 12345

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock())), \
         patch("app.bot.checklist_helpers.format_full_checklist", return_value="text"), \
         patch("app.bot.checklist_helpers.split_messages", return_value=["chunk1", "chunk2"]), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(side_effect=send_side_effect)):
        response = await client.post(MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})

    assert response.status_code == 502
    assert response.json()["results"][fail_group] == "error"
    assert fail_group in response.json()["failed_groups"]


# ─── DM failure tests: real send_sunday_evening_for_group path ────────────────

def _make_checklist_mock_with_assignee(assignee_id: int = 42):
    """Checklist with one item in a POST_SABHA section assigned to assignee_id."""
    item = MagicMock()
    item.is_completed = False
    item.assignee_id = assignee_id
    item.id = 1
    item.title = "Assigned Task"
    item.item_order = 0
    item.subchecklist_id = 1

    sub = MagicMock()
    sub.id = 1
    sub.title = "After Sabha Cleanup"
    sub.section_type = "POST_SABHA"
    sub.section_order = 0
    sub.items = [item]

    checklist = MagicMock()
    checklist.group_name = "test_group"
    checklist.week_start = MagicMock()
    checklist.week_start.strftime = MagicMock(return_value="Jan 01")
    checklist.subchecklists = [sub]
    checklist.items = [item]
    checklist.assignments = []
    return checklist


def _make_cm_with_user(telegram_chat_id: str = "555", assignee_id: int = 42):
    """Async context manager whose session returns a mock user on execute()."""
    mock_user = MagicMock()
    mock_user.id = assignee_id
    mock_user.telegram_chat_id = telegram_chat_id

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=mock_user)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


@pytest.mark.asyncio
async def test_evening_dm_false_returns_200_with_warning(client):
    """send_user_dm returning False → 200, dm_warnings in response, group is deduped."""
    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal",
               return_value=_make_cm_with_user()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock_with_assignee())), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist",
               return_value="reminder text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(return_value=12345)), \
         patch("app.services.telegram_service.send_user_dm",
               AsyncMock(return_value=False)):
        response = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert "failed_groups" not in data
    # DM warning included in response
    assert "dm_warnings" in data

    # Group was deduped — second call skips it
    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal",
               return_value=_make_cm_with_user()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock_with_assignee())), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist",
               return_value="reminder text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(return_value=12345)), \
         patch("app.services.telegram_service.send_user_dm",
               AsyncMock(return_value=False)):
        retry = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert retry.status_code == 200
    assert retry.json()["skipped"] is True


@pytest.mark.asyncio
async def test_evening_dm_raises_returns_200_both_dms_attempted(client):
    """send_user_dm raising for one assignee still attempts all and returns 200 with warning."""
    item1 = MagicMock()
    item1.is_completed = False
    item1.assignee_id = 10
    item1.id = 1
    item1.title = "Task A"
    item1.item_order = 0
    item1.subchecklist_id = 1

    item2 = MagicMock()
    item2.is_completed = False
    item2.assignee_id = 20
    item2.id = 2
    item2.title = "Task B"
    item2.item_order = 1
    item2.subchecklist_id = 1

    sub = MagicMock()
    sub.id = 1
    sub.title = "After Sabha Cleanup"
    sub.section_type = "POST_SABHA"
    sub.section_order = 0
    sub.items = [item1, item2]

    checklist = MagicMock()
    checklist.group_name = "test_group"
    checklist.week_start = MagicMock()
    checklist.week_start.strftime = MagicMock(return_value="Jan 01")
    checklist.subchecklists = [sub]
    checklist.items = [item1, item2]
    checklist.assignments = []

    user_10 = MagicMock()
    user_10.id = 10
    user_10.telegram_chat_id = "110"
    user_20 = MagicMock()
    user_20.id = 20
    user_20.telegram_chat_id = "120"

    result_10 = MagicMock()
    result_10.scalar_one_or_none = MagicMock(return_value=user_10)
    result_20 = MagicMock()
    result_20.scalar_one_or_none = MagicMock(return_value=user_20)

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[result_10, result_20])

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    # First DM raises; second succeeds
    dm_mock = AsyncMock(side_effect=[RuntimeError("DM exploded"), True])

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=mock_cm), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=checklist)), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist",
               return_value="reminder text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(return_value=12345)), \
         patch("app.services.telegram_service.send_user_dm", dm_mock):
        response = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    # DM failure does not cause 502
    assert response.status_code == 200
    # Both users were attempted despite the first raising
    assert dm_mock.await_count == 2
    # Warning included in response for the group that processed both DMs
    data = response.json()
    assert "dm_warnings" in data


@pytest.mark.asyncio
async def test_evening_all_dms_succeed_dedupes_group(client):
    """When group-topic and all DMs succeed, group is deduped and 200 returned."""
    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal",
               return_value=_make_cm_with_user()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock_with_assignee())), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist",
               return_value="reminder text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(return_value=12345)), \
         patch("app.services.telegram_service.send_user_dm",
               AsyncMock(return_value=True)):
        r1 = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
        r2 = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert r1.status_code == 200
    assert r1.json()["skipped"] is False
    # All groups deduped on second call
    assert r2.status_code == 200
    assert r2.json()["skipped"] is True


@pytest.mark.asyncio
async def test_evening_missing_assignee_returns_200_with_warning(client):
    """Assignee not found in DB → 200, dm_warnings in response, group deduped."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=None)  # user not found

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=mock_cm), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock_with_assignee(assignee_id=99))), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist",
               return_value="reminder text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(return_value=12345)):
        response = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert "failed_groups" not in data
    assert "dm_warnings" in data


@pytest.mark.asyncio
async def test_evening_no_telegram_chat_id_returns_200_with_warning(client):
    """Assignee with no telegram_chat_id → 200, dm_warnings in response, group deduped."""
    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal",
               return_value=_make_cm_with_user(telegram_chat_id=None)), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock_with_assignee())), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist",
               return_value="reminder text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(return_value=12345)):
        response = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert "failed_groups" not in data
    assert "dm_warnings" in data


# ─── Missing checklist: required-send failure ─────────────────────────────────

@pytest.mark.asyncio
async def test_morning_no_checklist_returns_502_not_deduped(client):
    """load_checklist_for_group returning None → 502; group not deduped; retry re-attempts it."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]
    load_call_count: dict[str, int] = {}

    async def load_side_effect(db, group_name):
        load_call_count[group_name] = load_call_count.get(group_name, 0) + 1
        if group_name == fail_group and load_call_count[group_name] == 1:
            return None
        return _make_checklist_mock()

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(side_effect=load_side_effect)), \
         patch("app.bot.checklist_helpers.format_full_checklist", return_value="text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(return_value=12345)):
        r1 = await client.post(MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})
        r2 = await client.post(MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})

    assert r1.status_code == 502
    assert fail_group in r1.json()["failed_groups"]
    assert r1.json()["results"][fail_group] == "error"
    # All groups were attempted on first call
    assert set(r1.json()["results"].keys()) == set(groups)
    # Non-failing groups succeeded
    for g in groups:
        if g != fail_group:
            assert r1.json()["results"][g] == "ok"

    # Not deduped — fail_group retried and succeeded on second call
    assert r2.status_code == 200
    assert r2.json()["results"][fail_group] == "ok"
    assert load_call_count[fail_group] == 2


@pytest.mark.asyncio
async def test_evening_no_checklist_returns_502_not_deduped(client):
    """load_checklist_for_group returning None → 502; group not deduped; retry re-attempts it."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]
    load_call_count: dict[str, int] = {}

    async def load_side_effect(db, group_name):
        load_call_count[group_name] = load_call_count.get(group_name, 0) + 1
        if group_name == fail_group and load_call_count[group_name] == 1:
            return None
        return _make_checklist_mock()

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(side_effect=load_side_effect)), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist", return_value="text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(return_value=12345)):
        r1 = await client.post(EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})
        r2 = await client.post(EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})

    assert r1.status_code == 502
    assert fail_group in r1.json()["failed_groups"]
    assert r1.json()["results"][fail_group] == "error"
    assert set(r1.json()["results"].keys()) == set(groups)
    for g in groups:
        if g != fail_group:
            assert r1.json()["results"][g] == "ok"

    assert r2.status_code == 200
    assert r2.json()["results"][fail_group] == "ok"
    assert load_call_count[fail_group] == 2


@pytest.mark.asyncio
async def test_morning_no_checklist_other_groups_still_attempted(client):
    """One group with no checklist does not prevent other groups from being sent."""
    groups = checklist_helpers.GroupName.ALL
    assert len(groups) >= 2, "Need at least 2 groups for isolation test"
    fail_group = groups[0]

    async def load_side_effect(db, group_name):
        if group_name == fail_group:
            return None
        return _make_checklist_mock()

    send_count: dict[str, int] = {}

    async def send_side_effect(group_name, text):
        send_count[group_name] = send_count.get(group_name, 0) + 1
        return 12345

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(side_effect=load_side_effect)), \
         patch("app.bot.checklist_helpers.format_full_checklist", return_value="text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(side_effect=send_side_effect)):
        response = await client.post(MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})

    assert response.status_code == 502
    data = response.json()
    # fail_group failed; every other group succeeded
    assert data["results"][fail_group] == "error"
    for g in groups:
        if g != fail_group:
            assert data["results"][g] == "ok"
            assert send_count.get(g, 0) >= 1
    # fail_group never reached send
    assert send_count.get(fail_group, 0) == 0


@pytest.mark.asyncio
async def test_concurrent_morning_calls_send_each_group_exactly_once(client):
    """Two concurrent orchestrator calls must send each group exactly once."""
    send_count = {"n": 0}

    async def send_side_effect(group_name, text):
        send_count["n"] += 1
        return 12345

    with patch("app.bot.checklist_helpers.AsyncSessionLocal", side_effect=_make_cm), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock())), \
         patch("app.bot.checklist_helpers.format_full_checklist", return_value="text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(side_effect=send_side_effect)):
        r1, r2 = await asyncio.gather(
            checklist_helpers.run_sunday_morning_all_groups(),
            checklist_helpers.run_sunday_morning_all_groups(),
        )

    num_groups = len(checklist_helpers.GroupName.ALL)
    assert send_count["n"] == num_groups, (
        f"Expected exactly {num_groups} sends (one per group), got {send_count['n']}"
    )
    for group in checklist_helpers.GroupName.ALL:
        statuses = {r1.get(group), r2.get(group)}
        assert statuses == {"ok", "skipped"}, (
            f"Group {group}: expected one ok and one skipped, got {statuses}"
        )


# ─── Missing topic mapping: required-send failure ─────────────────────────────

@pytest.mark.asyncio
async def test_morning_missing_topic_returns_502_not_deduped(client):
    """send_to_group_topic_strict returning None (missing topic mapping) → 502; group not deduped; retry succeeds."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]
    call_count: dict[str, int] = {}

    async def send_side_effect(group_name, text):
        call_count[group_name] = call_count.get(group_name, 0) + 1
        if group_name == fail_group and call_count[group_name] == 1:
            return None  # simulates missing topic mapping on first attempt
        return 12345

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock())), \
         patch("app.bot.checklist_helpers.format_full_checklist", return_value="text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(side_effect=send_side_effect)):
        r1 = await client.post(MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})
        r2 = await client.post(MORNING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})

    assert r1.status_code == 502
    assert fail_group in r1.json()["failed_groups"]
    assert r1.json()["results"][fail_group] == "error"
    # Not deduped — fail_group retried and succeeded on second call
    assert r2.status_code == 200
    assert r2.json()["results"][fail_group] == "ok"
    assert call_count[fail_group] == 2


@pytest.mark.asyncio
async def test_evening_missing_topic_returns_502_not_deduped(client):
    """send_to_group_topic_strict returning None (missing topic mapping) → 502; group not deduped; retry succeeds."""
    groups = checklist_helpers.GroupName.ALL
    fail_group = groups[0]
    call_count: dict[str, int] = {}

    async def send_side_effect(group_name, text):
        call_count[group_name] = call_count.get(group_name, 0) + 1
        if group_name == fail_group and call_count[group_name] == 1:
            return None
        return 12345

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal", return_value=_make_cm()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock())), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist", return_value="text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(side_effect=send_side_effect)):
        r1 = await client.post(EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})
        r2 = await client.post(EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"})

    assert r1.status_code == 502
    assert fail_group in r1.json()["failed_groups"]
    assert r1.json()["results"][fail_group] == "error"
    # Not deduped — fail_group retried and succeeded on second call
    assert r2.status_code == 200
    assert r2.json()["results"][fail_group] == "ok"
    assert call_count[fail_group] == 2


# ─── DM timeout: best-effort timeout returns 200 with warning, group deduped ──

@pytest.mark.asyncio
async def test_evening_dm_timeout_returns_200_with_warning(client):
    """send_user_dm hanging past _DM_TIMEOUT → 200, dm_warnings in response, group deduped."""
    async def slow_dm(user, text):
        await asyncio.sleep(999)
        return True  # pragma: no cover

    with patch("app.routers.internal_jobs.settings", _mock_settings()), \
         patch("app.bot.checklist_helpers.AsyncSessionLocal",
               return_value=_make_cm_with_user()), \
         patch("app.bot.checklist_helpers.load_checklist_for_group",
               AsyncMock(return_value=_make_checklist_mock_with_assignee())), \
         patch("app.bot.checklist_helpers.format_incomplete_checklist",
               return_value="reminder text"), \
         patch("app.services.telegram_service.send_to_group_topic_strict",
               AsyncMock(return_value=12345)), \
         patch("app.services.telegram_service.send_user_dm", slow_dm), \
         patch("app.bot.checklist_helpers._DM_TIMEOUT", 0.01):
        response = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )

    assert response.status_code == 200
    data = response.json()
    assert "failed_groups" not in data
    assert "dm_warnings" in data

    # Group was deduped despite the DM timeout — retry returns skipped
    with patch("app.routers.internal_jobs.settings", _mock_settings()):
        retry = await client.post(
            EVENING_URL, headers={"Authorization": f"Bearer {VALID_SECRET}"}
        )
    assert retry.status_code == 200
    assert retry.json()["skipped"] is True


# ─── Concurrent evening calls: required send exactly once per group ────────────

@pytest.mark.asyncio
async def test_concurrent_evening_calls_send_required_exactly_once(client):
    """Two concurrent orchestrator calls must send each group's required message exactly once."""
    required_count = {"n": 0}

    async def required_side_effect(group_name, db):
        required_count["n"] += 1
        return MagicMock()

    with patch("app.bot.checklist_helpers.AsyncSessionLocal", side_effect=_make_cm), \
         patch("app.bot.checklist_helpers._send_sunday_evening_required",
               AsyncMock(side_effect=required_side_effect)), \
         patch("app.bot.checklist_helpers._send_evening_dms_for_group",
               AsyncMock(return_value=[])):
        results_pair = await asyncio.gather(
            checklist_helpers.run_sunday_evening_all_groups(),
            checklist_helpers.run_sunday_evening_all_groups(),
        )

    num_groups = len(checklist_helpers.GroupName.ALL)
    results1, _ = results_pair[0]
    results2, _ = results_pair[1]
    assert required_count["n"] == num_groups, (
        f"Expected exactly {num_groups} required sends (one per group), got {required_count['n']}"
    )
    for group in checklist_helpers.GroupName.ALL:
        statuses = {results1.get(group), results2.get(group)}
        assert statuses == {"ok", "skipped"}, (
            f"Group {group}: expected one ok and one skipped, got {statuses}"
        )
