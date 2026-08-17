# Stronghold button fix

## Problem

`creator_tournaments.router` was registered before `stronghold.router`.
Its broad `@router.message(StateFilter(None))` handler received every text message,
including the `🏰 THE STRONGHOLD` reply-keyboard button. Even when no pending
tournament score existed, the message did not continue to later routers.

## Fix

Moved `creator_tournaments.router` to the end of `setup_routers()` after
`menu.router`. Tournament callback handlers remain available, while the broad
manual-score text handler can no longer swallow normal menu buttons.

## Database safety

No database schema, migration, environment variable, Railway volume, or user data
is changed by this patch.
