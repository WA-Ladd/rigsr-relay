# Intake Smoke Test Checklist

Purpose: provide a repeatable test plan for Intake relay routing without relying on memory or ad hoc chat steps.

## Test Scope

This checklist verifies the GitHub/n8n relay handoff path:

- relay/outbox/<relay_id>.json is detected
- relay is fetched and parsed
- relay is classified/routed by recipient
- relay/inbox/<relay_id>.json is created
- relay/index/<recipient>.json is updated
- invalid/unhandled recipients are routed intentionally, not silently confused with valid agent inboxes

## Required Preconditions

- n8n Intake workflow is active
- GitHub webhook points to the current n8n webhook URL
- ngrok/local tunnel is running if required
- repository is WA-Ladd/rigsr-relay
- relay files use .json extension
- recipient index files exist for active recipients

## Smoke Test A — User to Tech

Create relay/outbox/<new_id>.json with:

- from: 99
- to: 00
- type: relay
- status: pending or complete, depending on current workflow expectation

Expected:

- relay/inbox/<new_id>.json exists
- relay/index/00.json pending includes <new_id>.json
- no relay/index/undefined.json is created
- no dead-letter for valid recipient 00

## Smoke Test B — User to Fives

Create relay/outbox/<new_id>.json with:

- from: 99
- to: 03
- type: relay

Expected:

- relay/inbox/<new_id>.json exists
- relay/index/03.json pending includes <new_id>.json
- no dead-letter for valid recipient 03

## Smoke Test C — User Terminal Recipient

Create or process a relay with:

- to: 99

Expected depends on chosen design:

- either relay/index/99.json updates, or
- relay/user/ or equivalent terminal output receives it, or
- workflow intentionally stops without dead-letter

Current known open item: to: 99 terminal handling is not yet finalized.

## Smoke Test D — Invalid Recipient

Create relay/outbox/<new_id>.json with:

- to: 98

Expected:

- dead-letter path receives the relay
- no agent index is updated

## Regression Checks

After each test confirm:

- no relay/index/undefined.json created
- target inbox file exists exactly once
- target index pending list preserves existing entries unless cleanup is explicitly part of the test
- workflow execution reports success or a clear intentional dead-letter

## Stop Conditions

Stop testing and fix workflow if any of these occur:

- undefined recipient index is created
- valid agent recipient goes to dead-letter
- inbox file is created but index does not update
- index updates but inbox file is missing
- webhook fires but filter rejects a valid .json outbox relay
