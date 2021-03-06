# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2019 Scille SAS

import pytest
import trio

from parsec.api.data import UserProfile
from parsec.api.protocol import DeviceID, DeviceName, HumanHandle, InvitationType
from parsec.core.backend_connection import (
    backend_invited_cmds_factory,
    backend_authenticated_cmds_factory,
)
from parsec.core.types import BackendInvitationAddr, LocalDevice
from parsec.core.invite import (
    InvitePeerResetError,
    claimer_retrieve_info,
    DeviceClaimInitialCtx,
    UserClaimInitialCtx,
    DeviceGreetInitialCtx,
    UserGreetInitialCtx,
)


@pytest.mark.trio
async def test_good_device_claim(running_backend, alice, alice_backend_cmds):
    invitation = await running_backend.backend.invite.new_for_device(
        organization_id=alice.organization_id, greeter_user_id=alice.user_id
    )
    invitation_addr = BackendInvitationAddr.build(
        backend_addr=alice.organization_addr,
        organization_id=alice.organization_id,
        invitation_type=InvitationType.DEVICE,
        token=invitation.token,
    )

    requested_device_name = DeviceName("Foo")
    requested_device_label = "Foo's label"
    granted_device_name = DeviceName("Bar")
    granted_device_label = "Bar's label"
    new_device = None

    # Simulate out-of-bounds canal
    oob_send, oob_recv = trio.open_memory_channel(0)

    async def _run_claimer():
        async with backend_invited_cmds_factory(addr=invitation_addr) as cmds:
            initial_ctx = await claimer_retrieve_info(cmds)
            assert isinstance(initial_ctx, DeviceClaimInitialCtx)
            assert initial_ctx.greeter_user_id == alice.user_id
            assert initial_ctx.greeter_human_handle == alice.human_handle

            in_progress_ctx = await initial_ctx.do_wait_peer()

            choices = in_progress_ctx.generate_greeter_sas_choices(size=4)
            assert len(choices) == 4
            assert in_progress_ctx.greeter_sas in choices

            greeter_sas = await oob_recv.receive()
            assert greeter_sas == in_progress_ctx.greeter_sas

            in_progress_ctx = await in_progress_ctx.do_signify_trust()
            await oob_send.send(in_progress_ctx.claimer_sas)

            in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()

            nonlocal new_device
            new_device = await in_progress_ctx.do_claim_device(
                requested_device_name=requested_device_name,
                requested_device_label=requested_device_label,
            )
            assert isinstance(new_device, LocalDevice)

    async def _run_greeter():
        initial_ctx = DeviceGreetInitialCtx(cmds=alice_backend_cmds, token=invitation_addr.token)

        in_progress_ctx = await initial_ctx.do_wait_peer()

        await oob_send.send(in_progress_ctx.greeter_sas)

        in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()

        choices = in_progress_ctx.generate_claimer_sas_choices(size=5)
        assert len(choices) == 5
        assert in_progress_ctx.claimer_sas in choices

        claimer_sas = await oob_recv.receive()
        assert claimer_sas == in_progress_ctx.claimer_sas

        in_progress_ctx = await in_progress_ctx.do_signify_trust()

        in_progress_ctx = await in_progress_ctx.do_get_claim_requests()

        assert in_progress_ctx.requested_device_name == requested_device_name
        assert in_progress_ctx.requested_device_label == requested_device_label

        await in_progress_ctx.do_create_new_device(
            author=alice, device_name=granted_device_name, device_label=granted_device_label
        )

    with trio.fail_after(1):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(_run_claimer)
            nursery.start_soon(_run_greeter)

    assert new_device is not None
    assert new_device.user_id == alice.user_id
    assert new_device.device_name == granted_device_name
    assert new_device.device_label == granted_device_label
    assert new_device.human_handle == alice.human_handle
    assert new_device.private_key == alice.private_key
    assert new_device.signing_key != alice.signing_key
    assert new_device.profile == alice.profile

    # Now invitation should have been deleted
    rep = await alice_backend_cmds.invite_list()
    assert rep == {"status": "ok", "invitations": []}

    # Make sure new device can connect to the backend
    async with backend_authenticated_cmds_factory(
        addr=new_device.organization_addr,
        device_id=new_device.device_id,
        signing_key=new_device.signing_key,
    ) as cmds:
        await cmds.ping()


@pytest.mark.trio
async def test_good_user_claim(running_backend, alice, alice_backend_cmds):
    claimer_email = "zack@example.com"

    invitation = await running_backend.backend.invite.new_for_user(
        organization_id=alice.organization_id,
        greeter_user_id=alice.user_id,
        claimer_email=claimer_email,
    )
    invitation_addr = BackendInvitationAddr.build(
        backend_addr=alice.organization_addr,
        organization_id=alice.organization_id,
        invitation_type=InvitationType.USER,
        token=invitation.token,
    )

    # Let's pretent we invited a Fortnite player...
    requested_device_id = DeviceID("xXx_zack_xXx@ultr4_b00st")
    requested_human_handle = HumanHandle(email="ZACK@example.com", label="Z4ck")
    requested_device_label = "Ultr4 B00st's label"
    granted_device_id = DeviceID("zack@pc1")
    granted_human_handle = HumanHandle(email="zack@example.com", label="Zack")
    granted_device_label = "PC1's label"
    granted_profile = UserProfile.OUTSIDER
    new_device = None

    # Simulate out-of-bounds canal
    oob_send, oob_recv = trio.open_memory_channel(0)

    async def _run_claimer():
        async with backend_invited_cmds_factory(addr=invitation_addr) as cmds:
            initial_ctx = await claimer_retrieve_info(cmds)
            assert isinstance(initial_ctx, UserClaimInitialCtx)
            assert initial_ctx.claimer_email == claimer_email
            assert initial_ctx.greeter_user_id == alice.user_id
            assert initial_ctx.greeter_human_handle == alice.human_handle

            in_progress_ctx = await initial_ctx.do_wait_peer()

            choices = in_progress_ctx.generate_greeter_sas_choices(size=4)
            assert len(choices) == 4
            assert in_progress_ctx.greeter_sas in choices

            greeter_sas = await oob_recv.receive()
            assert greeter_sas == in_progress_ctx.greeter_sas

            in_progress_ctx = await in_progress_ctx.do_signify_trust()
            await oob_send.send(in_progress_ctx.claimer_sas)

            in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()

            nonlocal new_device
            new_device = await in_progress_ctx.do_claim_user(
                requested_device_id=requested_device_id,
                requested_device_label=requested_device_label,
                requested_human_handle=requested_human_handle,
            )
            assert isinstance(new_device, LocalDevice)

    async def _run_greeter():
        initial_ctx = UserGreetInitialCtx(cmds=alice_backend_cmds, token=invitation_addr.token)

        in_progress_ctx = await initial_ctx.do_wait_peer()

        await oob_send.send(in_progress_ctx.greeter_sas)

        in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()

        choices = in_progress_ctx.generate_claimer_sas_choices(size=5)
        assert len(choices) == 5
        assert in_progress_ctx.claimer_sas in choices

        claimer_sas = await oob_recv.receive()
        assert claimer_sas == in_progress_ctx.claimer_sas

        in_progress_ctx = await in_progress_ctx.do_signify_trust()

        in_progress_ctx = await in_progress_ctx.do_get_claim_requests()

        assert in_progress_ctx.requested_device_id == requested_device_id
        assert in_progress_ctx.requested_device_label == requested_device_label
        assert in_progress_ctx.requested_human_handle == requested_human_handle

        await in_progress_ctx.do_create_new_user(
            author=alice,
            device_id=granted_device_id,
            device_label=granted_device_label,
            human_handle=granted_human_handle,
            profile=granted_profile,
        )

    with trio.fail_after(1):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(_run_claimer)
            nursery.start_soon(_run_greeter)

    assert new_device is not None
    assert new_device.device_id == granted_device_id
    assert new_device.device_label == granted_device_label
    # Label is normally ignored when comparing HumanLabel
    assert new_device.human_handle.label == granted_human_handle.label
    assert new_device.human_handle.email == granted_human_handle.email
    assert new_device.profile == granted_profile

    # Now invitation should have been deleted
    rep = await alice_backend_cmds.invite_list()
    assert rep == {"status": "ok", "invitations": []}

    # Make sure new device can connect to the backend
    async with backend_authenticated_cmds_factory(
        addr=new_device.organization_addr,
        device_id=new_device.device_id,
        signing_key=new_device.signing_key,
    ) as cmds:
        await cmds.ping()


@pytest.mark.trio
async def test_claimer_handle_reset(backend, running_backend, alice, alice_backend_cmds):
    invitation = await backend.invite.new_for_device(
        organization_id=alice.organization_id, greeter_user_id=alice.user_id
    )
    invitation_addr = BackendInvitationAddr.build(
        backend_addr=alice.organization_addr,
        organization_id=alice.organization_id,
        invitation_type=InvitationType.DEVICE,
        token=invitation.token,
    )

    async with backend_invited_cmds_factory(addr=invitation_addr) as claimer_cmds:
        greeter_initial_ctx = UserGreetInitialCtx(
            cmds=alice_backend_cmds, token=invitation_addr.token
        )
        claimer_initial_ctx = await claimer_retrieve_info(claimer_cmds)

        claimer_in_progress_ctx = None
        greeter_in_progress_ctx = None

        # Step 1
        with trio.fail_after(1):
            async with trio.open_nursery() as nursery:

                async def _do_claimer():
                    nonlocal claimer_in_progress_ctx
                    claimer_in_progress_ctx = await claimer_initial_ctx.do_wait_peer()

                async def _do_greeter():
                    nonlocal greeter_in_progress_ctx
                    greeter_in_progress_ctx = await greeter_initial_ctx.do_wait_peer()

                nursery.start_soon(_do_claimer)
                nursery.start_soon(_do_greeter)

        # Claimer restart the conduit while greeter try to do step 2
        with trio.fail_after(1):
            async with trio.open_nursery() as nursery:

                async def _do_claimer():
                    nonlocal claimer_in_progress_ctx
                    claimer_in_progress_ctx = await claimer_initial_ctx.do_wait_peer()

                nursery.start_soon(_do_claimer)
                with pytest.raises(InvitePeerResetError):
                    await greeter_in_progress_ctx.do_wait_peer_trust()

                # Greeter redo step 1
                greeter_in_progress_ctx = await greeter_initial_ctx.do_wait_peer()

        # Now do the other way around: greeter restart conduit while claimer try step 2
        with trio.fail_after(1):
            async with trio.open_nursery() as nursery:

                async def _do_greeter():
                    nonlocal greeter_in_progress_ctx
                    greeter_in_progress_ctx = await greeter_initial_ctx.do_wait_peer()

                nursery.start_soon(_do_greeter)
                with pytest.raises(InvitePeerResetError):
                    await claimer_in_progress_ctx.do_signify_trust()

                # Claimer redo step 1
                claimer_in_progress_ctx = await claimer_initial_ctx.do_wait_peer()
