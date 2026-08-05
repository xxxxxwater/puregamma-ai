# Intimate Secretary Memory

Runtime memory is stored in PostgreSQL and isolated by authenticated `user_id`.
This file documents the policy only; it must never contain user conversations or secrets.

- Recall only messages from the user's secretary conversation.
- Keep external actions behind explicit confirmation.
- Let the user delete their secretary memory at any time.
- Never persist credentials, payment data, or private keys in conversation memory.
